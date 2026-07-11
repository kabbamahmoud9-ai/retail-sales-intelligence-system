"""
customer_insights/ml_services.py

Isolated ML layer — the ONLY place scikit-learn is imported/used in this
app. Rule-based logic (segmentation, summaries, recommendations) lives
entirely in services.py; this file is purely predictive modelling.

Models are trained FRESH on every call, in-memory, never persisted as
.pkl files — same philosophy as forecasting.LinearRegression being
retrained per product on every generate_forecasts run. This keeps every
prediction traceable to the exact data that produced it, with no model-
versioning complexity a dissertation doesn't need.

Three models, all cross-customer (trained once on the whole eligible
customer base, then applied per customer):
  1. Next-purchase-date  — LinearRegression
  2. Customer lifetime value (CLV) — LinearRegression
  3. Churn risk — LogisticRegression

Minimum eligibility: customers need >=3 confirmed orders (MIN_ORDERS_FOR_ML)
to contribute training rows AND to receive ML predictions. Below that,
customer_insights.services falls back to rule-based heuristics — see
generate_rule_based_predictions() there.
"""
from datetime import timedelta
from django.utils import timezone
from sklearn.linear_model import LinearRegression, LogisticRegression

from ecommerce.models import OnlineOrder
from .models import CustomerEvent

MODEL_VERSION = "v1-sklearn-linear-logistic"
MIN_ORDERS_FOR_ML = 3
MIN_TRAINING_ROWS = 5  # below this, don't trust the model at all — too few points to fit meaningfully
CHURN_INTERVAL_MULTIPLIER = 2.0  # mirrors services.AT_RISK_INTERVAL_MULTIPLIER


def _eligible_customers():
    """Customers with enough confirmed order history to be part of ML training."""
    from ecommerce.models import OnlineCustomer
    from django.db.models import Count, Q
    return (
        OnlineCustomer.objects
        .annotate(confirmed_count=Count('orders', filter=Q(orders__status='confirmed')))
        .filter(confirmed_count__gte=MIN_ORDERS_FOR_ML)
    )


def _order_history_with_features(customer):
    """
    Returns a chronological list of dicts, one per confirmed order, each
    carrying the customer's aggregate stats AS OF that order (i.e. not
    peeking at future orders) — used to build both training examples and
    live prediction features without leaking future information.
    """
    orders = list(
        OnlineOrder.objects.filter(customer=customer, status='confirmed').order_by('order_date')
    )
    history = []
    cumulative_spend = 0
    for i, order in enumerate(orders):
        cumulative_spend += float(order.total_amount)
        order_count_so_far = i + 1

        if i == 0:
            avg_interval_so_far = 0.0
        else:
            gaps = [
                (orders[j].order_date - orders[j - 1].order_date).total_seconds() / 86400
                for j in range(1, i + 1)
            ]
            avg_interval_so_far = sum(gaps) / len(gaps)

        days_since_first_order = (order.order_date - orders[0].order_date).days

        event_count_so_far = CustomerEvent.objects.filter(
            customer=customer, created_at__lte=order.order_date
        ).count()

        history.append({
            'order_date': order.order_date,
            'order_count_so_far': order_count_so_far,
            'avg_order_value_so_far': cumulative_spend / order_count_so_far,
            'avg_interval_so_far': avg_interval_so_far,
            'days_since_first_order': days_since_first_order,
            'cumulative_spend_so_far': cumulative_spend,
            'event_count_so_far': event_count_so_far,
        })
    return history


def _feature_vector(snapshot):
    """Fixed feature ordering shared by all three models."""
    return [
        snapshot['order_count_so_far'],
        snapshot['avg_order_value_so_far'],
        snapshot['avg_interval_so_far'],
        snapshot['days_since_first_order'],
        snapshot['event_count_so_far'],
    ]


# ---------------------------------------------------------------------------
# Next-purchase-date model
# ---------------------------------------------------------------------------

def _build_next_purchase_training_data():
    """
    For every eligible customer, for every order N (N >= 2nd order) that
    has a following order N+1, one training row: features as of order N,
    label = days until order N+1. Multiple rows per customer are fine —
    this is standard for this kind of "time to next event" regression.
    """
    X, y = [], []
    for customer in _eligible_customers():
        history = _order_history_with_features(customer)
        for i in range(1, len(history) - 1):  # need a "so far" (i>=1) and a "next" (i+1 exists)
            days_to_next = (history[i + 1]['order_date'] - history[i]['order_date']).total_seconds() / 86400
            X.append(_feature_vector(history[i]))
            y.append(days_to_next)
    return X, y


def train_next_purchase_model():
    X, y = _build_next_purchase_training_data()
    if len(X) < MIN_TRAINING_ROWS:
        return None
    model = LinearRegression()
    model.fit(X, y)
    return model


def predict_next_purchase_date(model, customer):
    if model is None:
        return None
    history = _order_history_with_features(customer)
    if not history:
        return None
    latest = history[-1]
    predicted_days = model.predict([_feature_vector(latest)])[0]
    predicted_days = max(predicted_days, 1)  # never predict "in the past" or same-day
    return (timezone.now() + timedelta(days=predicted_days)).date()


# ---------------------------------------------------------------------------
# Customer lifetime value model
# ---------------------------------------------------------------------------

def _build_clv_training_data():
    """
    One row per eligible customer: features as of their MIN_ORDERS_FOR_ML-th
    order (an early checkpoint, not their full history) predicting their
    eventual total spend across ALL confirmed orders to date. This avoids
    the trivial-leakage version of "predict total spend from total spend."
    A simplified academic proxy for CLV — documented as such, not a true
    discounted-future-value model.
    """
    X, y = [], []
    for customer in _eligible_customers():
        history = _order_history_with_features(customer)
        if len(history) < MIN_ORDERS_FOR_ML:
            continue
        checkpoint = history[MIN_ORDERS_FOR_ML - 1]  # e.g. as of their 3rd order
        eventual_total_spend = history[-1]['cumulative_spend_so_far']
        X.append(_feature_vector(checkpoint))
        y.append(eventual_total_spend)
    return X, y


def train_clv_model():
    X, y = _build_clv_training_data()
    if len(X) < MIN_TRAINING_ROWS:
        return None
    model = LinearRegression()
    model.fit(X, y)
    return model


def predict_clv(model, customer):
    if model is None:
        return None
    history = _order_history_with_features(customer)
    if not history:
        return None
    latest = history[-1]
    predicted = model.predict([_feature_vector(latest)])[0]
    return max(predicted, latest['cumulative_spend_so_far'])  # never predict below what they've already spent


# ---------------------------------------------------------------------------
# Churn risk model
# ---------------------------------------------------------------------------

def _build_churn_training_data():
    """
    One row per eligible customer, using their current full-history
    features. Label is rule-derived (not manually annotated): 1 if their
    actual gap since last order exceeds CHURN_INTERVAL_MULTIPLIER x their
    own average interval, else 0 — same rule already used for the
    rule-based 'at_risk' segment in services.py, just repurposed here as
    a supervised label so the model learns to approximate that judgment
    from RFM-style features alone.
    """
    X, y = [], []
    for customer in _eligible_customers():
        history = _order_history_with_features(customer)
        if len(history) < MIN_ORDERS_FOR_ML:
            continue
        latest = history[-1]
        days_since_last = (timezone.now() - latest['order_date']).days
        threshold = latest['avg_interval_so_far'] * CHURN_INTERVAL_MULTIPLIER if latest['avg_interval_so_far'] else 60
        label = 1 if days_since_last > threshold else 0
        X.append(_feature_vector(latest))
        y.append(label)
    return X, y


def train_churn_model():
    X, y = _build_churn_training_data()
    if len(X) < MIN_TRAINING_ROWS:
        return None
    if len(set(y)) < 2:
        # LogisticRegression needs both classes present — if every eligible
        # customer is currently churned or currently active, there's
        # nothing to learn a boundary from yet.
        return None
    model = LogisticRegression()
    model.fit(X, y)
    return model


def predict_churn_risk(model, customer):
    if model is None:
        return None
    history = _order_history_with_features(customer)
    if not history:
        return None
    latest = history[-1]
    probability = model.predict_proba([_feature_vector(latest)])[0][1]  # P(class=1, i.e. churned)
    return round(float(probability), 4)


# ---------------------------------------------------------------------------
# Single entry point — trains all three models fresh, applies to one customer
# ---------------------------------------------------------------------------

def generate_ml_predictions(customer):
    """
    Public API. Trains all three models fresh against the current full
    eligible customer base, then applies them to this one customer.
    Returns None if the customer doesn't meet MIN_ORDERS_FOR_ML, or a
    dict of predictions (individual fields may still be None if a given
    model couldn't be trained due to insufficient/uniform data).
    """
    from ecommerce.models import OnlineOrder as _OO
    confirmed_count = _OO.objects.filter(customer=customer, status='confirmed').count()
    if confirmed_count < MIN_ORDERS_FOR_ML:
        return None

    next_purchase_model = train_next_purchase_model()
    clv_model = train_clv_model()
    churn_model = train_churn_model()

    return {
        'predicted_next_purchase_date': predict_next_purchase_date(next_purchase_model, customer),
        'estimated_lifetime_value': predict_clv(clv_model, customer),
        'churn_risk_score': predict_churn_risk(churn_model, customer),
        'model_version': MODEL_VERSION,
    }