"""
customer_insights/services.py

Rule-based intelligence layer: behaviour metrics, segmentation, and
natural-language summary generation. No ML here — see ml_services.py
for the LinearRegression/LogisticRegression predictive layer (16d).

This file never duplicates business logic from ecommerce or ai_commerce —
it only reads their data and, for recommendations, calls their existing
functions directly (see get_personalized_recommendations, wired in 16d
once ai_commerce's real service functions are confirmed).
"""
from collections import Counter
from datetime import timedelta
from django.utils import timezone
from django.db.models import Avg

from ecommerce.models import OnlineOrder
from .models import CustomerEvent
from ai_commerce.services import get_reorder_suggestions

# ---------------------------------------------------------------------------
# Segmentation thresholds — v1 heuristics, documented and adjustable
# ---------------------------------------------------------------------------

VIP_MIN_LIFETIME_SPENDING = 2_000_000  # Le
VIP_MIN_TRUST_SCORE = 75

FREQUENT_BUYER_MIN_ORDERS = 5
FREQUENT_BUYER_MAX_INTERVAL_DAYS = 21

PREMIUM_SHOPPER_MIN_AVG_ORDER_VALUE = 300_000  # Le

AT_RISK_INTERVAL_MULTIPLIER = 2.0   # no order in > 2x their own average interval
AT_RISK_DEFAULT_DAYS = 60           # fallback if no interval history yet

PRICE_SENSITIVE_MIN_VIEW_TO_PURCHASE_RATIO = 5  # 5+ views per completed order

NEW_CUSTOMER_MAX_ORDERS = 1


# ---------------------------------------------------------------------------
# Behaviour metrics
# ---------------------------------------------------------------------------

def calculate_behaviour_metrics(customer):
    """
    Pure ORM aggregation over OnlineOrder/OnlineOrderItem/CustomerEvent.
    Returns a plain dict — never persisted directly, only used to build
    a CustomerInsightSnapshot by the orchestrator in 16d.
    """
    confirmed_orders = OnlineOrder.objects.filter(
        customer=customer, status='confirmed'
    ).order_by('order_date')

    order_count = confirmed_orders.count()

    avg_order_value = confirmed_orders.aggregate(avg=Avg('total_amount'))['avg']

    # Average interval between consecutive confirmed orders
    order_frequency_days = None
    if order_count >= 2:
        dates = list(confirmed_orders.values_list('order_date', flat=True))
        gaps = [
            (dates[i] - dates[i - 1]).total_seconds() / 86400
            for i in range(1, len(dates))
        ]
        order_frequency_days = sum(gaps) / len(gaps)

    # Preferred payment method — mode across confirmed orders
    payment_methods = list(confirmed_orders.values_list('payment_method', flat=True))
    preferred_payment_method = Counter(payment_methods).most_common(1)[0][0] if payment_methods else ''

    # Preferred shopping time — bucket order_date hours into morning/afternoon/evening/night
    def _time_bucket(dt):
        hour = timezone.localtime(dt).hour
        if 5 <= hour < 12:
            return 'morning'
        elif 12 <= hour < 17:
            return 'afternoon'
        elif 17 <= hour < 21:
            return 'evening'
        return 'night'

    time_buckets = [_time_bucket(d) for d in confirmed_orders.values_list('order_date', flat=True)]
    preferred_shopping_time = Counter(time_buckets).most_common(1)[0][0] if time_buckets else ''

    # Favorite category — combine purchase history + browsing events
    purchased_category_ids = list(
        confirmed_orders.values_list('items__product__category_id', flat=True)
    )
    viewed_category_ids = list(
        CustomerEvent.objects.filter(
            customer=customer, event_type__in=['category_view', 'product_view']
        ).exclude(category__isnull=True).values_list('category_id', flat=True)
    )
    product_viewed_category_ids = list(
        CustomerEvent.objects.filter(
            customer=customer, event_type='product_view'
        ).exclude(product__category__isnull=True).values_list('product__category_id', flat=True)
    )
    combined_category_ids = (
        purchased_category_ids * 2  # weight purchases more heavily than browsing
        + viewed_category_ids
        + product_viewed_category_ids
    )
    combined_category_ids = [c for c in combined_category_ids if c]
    favorite_category_id = Counter(combined_category_ids).most_common(1)[0][0] if combined_category_ids else None

    # View-to-purchase ratio (for price-sensitivity signal)
    total_views = CustomerEvent.objects.filter(
        customer=customer, event_type='product_view'
    ).count()
    view_to_purchase_ratio = (total_views / order_count) if order_count > 0 else total_views

    return {
        'order_count': order_count,
        'avg_order_value': avg_order_value,
        'order_frequency_days': order_frequency_days,
        'preferred_payment_method': preferred_payment_method,
        'preferred_shopping_time': preferred_shopping_time,
        'favorite_category_id': favorite_category_id,
        'view_to_purchase_ratio': view_to_purchase_ratio,
        'last_order_date': confirmed_orders.last().order_date if order_count else None,
    }


# ---------------------------------------------------------------------------
# Segmentation
# ---------------------------------------------------------------------------

def classify_segment(customer, metrics):
    """
    Rule-based, priority-ordered classification. Returns one of
    CustomerInsightSnapshot.SEGMENT_CHOICES. Evaluated in a fixed
    precedence so every customer gets exactly one segment, even when
    multiple criteria technically apply.
    """
    order_count = metrics['order_count']

    # 1. New — very little or no order history yet
    if order_count <= NEW_CUSTOMER_MAX_ORDERS:
        return 'new'

    # 2. At-Risk — hasn't ordered recently relative to their own pattern
    last_order_date = metrics['last_order_date']
    if last_order_date:
        days_since_last_order = (timezone.now() - last_order_date).days
        interval = metrics['order_frequency_days']
        threshold = (interval * AT_RISK_INTERVAL_MULTIPLIER) if interval else AT_RISK_DEFAULT_DAYS
        if days_since_last_order > threshold:
            return 'at_risk'

    # 3. VIP — high lifetime spend + high trust
    if customer.lifetime_spending >= VIP_MIN_LIFETIME_SPENDING and customer.trust_score >= VIP_MIN_TRUST_SCORE:
        return 'vip'

    # 4. Frequent Buyer — many orders, short intervals
    interval = metrics['order_frequency_days']
    if order_count >= FREQUENT_BUYER_MIN_ORDERS and interval and interval <= FREQUENT_BUYER_MAX_INTERVAL_DAYS:
        return 'frequent_buyer'

    # 5. Premium Shopper — consistently high order value
    avg_value = metrics['avg_order_value']
    if avg_value and avg_value >= PREMIUM_SHOPPER_MIN_AVG_ORDER_VALUE:
        return 'premium_shopper'

    # 6. Price-Sensitive — browses a lot relative to how much they buy
    if metrics['view_to_purchase_ratio'] >= PRICE_SENSITIVE_MIN_VIEW_TO_PURCHASE_RATIO:
        return 'price_sensitive'

    # 7. Loyal — fallback for steady repeat customers meeting no extreme criteria
    return 'loyal'


# ---------------------------------------------------------------------------
# Natural-language summary — template-based, NOT a live LLM call (Decision 28)
# ---------------------------------------------------------------------------

SEGMENT_DESCRIPTIONS = {
    'vip':              "one of our highest-value customers",
    'loyal':             "a steady, reliable repeat customer",
    'new':               "a new customer just getting started with us",
    'at_risk':           "a previously active customer who may be drifting away",
    'price_sensitive':   "a value-conscious shopper who compares before buying",
    'premium_shopper':   "a shopper who consistently favours higher-value purchases",
    'frequent_buyer':    "a frequent, high-engagement shopper",
}


def generate_summary_text(customer, metrics, segment, prediction_data=None):
    """
    Builds a short natural-language paragraph from templates driven by
    persisted data — same pattern as advisor's reasoning strings and
    voice_assistant/narration.py's recap builder. This is the documented
    future-Gemini seam (Decision 77/78): swapping this function's body
    for a live LLM call later would change nothing else in the system.
    """
    parts = []
    parts.append(f"{customer.full_name} is {SEGMENT_DESCRIPTIONS.get(segment, 'a customer')}.")

    if metrics['order_count'] > 0:
        parts.append(f"They have placed {metrics['order_count']} confirmed order(s)")
        if metrics['avg_order_value']:
            parts.append(f"averaging Le {metrics['avg_order_value']:,.2f} per order.")
        else:
            parts.append(".")
    else:
        parts.append("They have not yet completed a confirmed order.")

    if metrics['order_frequency_days']:
        parts.append(f"On average, they order roughly every {metrics['order_frequency_days']:.0f} days.")

    if metrics['preferred_payment_method']:
        parts.append(f"Their preferred payment method is {metrics['preferred_payment_method'].replace('_', ' ')}.")

    if prediction_data and prediction_data.get('churn_risk_score') is not None:
        risk_pct = prediction_data['churn_risk_score'] * 100
        if risk_pct >= 60:
            parts.append(f"Churn risk is elevated at {risk_pct:.0f}%, worth proactive outreach.")
        elif risk_pct >= 30:
            parts.append(f"Churn risk is moderate at {risk_pct:.0f}%.")
        else:
            parts.append(f"Churn risk is low at {risk_pct:.0f}%.")

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Personalized recommendations — THIN WRAPPER over ai_commerce (Decision 76 style)
# ---------------------------------------------------------------------------

def get_personalized_recommendations(customer):
    """
    Placeholder — to be wired in 16d once ai_commerce/services.py's real
    function signatures are confirmed. Must call into ai_commerce's
    existing candidate/ranking functions directly; must NEVER reimplement
    scoring or recommendation logic here.
    """
def get_personalized_recommendations(customer, limit=5):
    """
    Thin wrapper over ai_commerce.services.get_reorder_suggestions() —
    reuses the existing purchase-history-based ranking rather than
    reimplementing any scoring logic here (Decision 76 principle,
    extended to this module).

    Returns a list of product IDs, suitable for
    CustomerInsightSnapshot.recommended_product_ids (JSONField).
    """
    suggestions = get_reorder_suggestions(customer, limit=limit)
    return [s['product'].id for s in suggestions]