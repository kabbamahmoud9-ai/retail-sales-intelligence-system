"""
forecasting/services.py

Core AI demand forecasting logic.

Pipeline:
    1. For each active product, build a weekly sales time series
       (zero-sale weeks included) spanning from the product's first
       completed sale to today.
    2. If fewer than 30 calendar days of history exist, save a
       DemandForecast row flagged as insufficient data.
    3. Otherwise, fit a scikit-learn LinearRegression model on
       (week_index -> quantity_sold) and predict next week's demand.
    4. Derive trend direction, a confidence score, and a recommended
       restock quantity, then persist a new DemandForecast row.

Design notes / assumptions (documented per project convention):
    - Only Sale records with status='completed' count as real demand.
    - Weeks are simple 7-day buckets starting from the first sale date
      (not calendar/ISO weeks) — keeps the math simple and reproducible,
      which matters for the dissertation methodology section.
    - Trend classification uses a slope-vs-historical-average threshold
      (10%) rather than a fixed unit threshold, so it scales sensibly
      across low-volume and high-volume products alike.
    - Confidence score is derived from the model's R² score, scaled to
      0-100, and capped when the data window is short (<8 weeks) since
      a regression fit to very few points is inherently less reliable.
"""

from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.utils import timezone
from django.db.models import Sum

import numpy as np
from sklearn.linear_model import LinearRegression

from products.models import Product
from sales.models import SaleItem
from .models import DemandForecast

MIN_HISTORY_DAYS = 30
MODEL_VERSION = "v1.0-linreg"
TREND_THRESHOLD_RATIO = 0.10  # slope must move >10% of historical avg per week to count as trending
LOW_DATA_WEEK_COUNT = 8       # fewer weeks than this caps confidence score
LOW_DATA_CONFIDENCE_CAP = 60  # max confidence allowed with a short data window


def _to_decimal(value, places="0.01"):
    """Round a float/np value to 2 decimal places as a Decimal, safe for DecimalField."""
    return Decimal(str(round(float(value), 2))).quantize(Decimal(places), rounding=ROUND_HALF_UP)


def get_first_completed_sale_date(product):
    """Returns the date of the product's earliest completed sale, or None if it has never sold."""
    result = (
        SaleItem.objects
        .filter(product=product, sale__status='completed')
        .order_by('sale__sale_date')
        .values_list('sale__sale_date', flat=True)
        .first()
    )
    return result.date() if result else None


def build_weekly_series(product, start_date, end_date):
    """
    Builds a weekly quantity-sold time series for a product between start_date
    and end_date (inclusive), in simple 7-day buckets starting at start_date.
    Weeks with no sales are included as 0 — required so the regression sees
    true demand patterns rather than only transaction days.

    Returns a list of (week_index, quantity_sold) tuples.
    """
    sale_items = (
        SaleItem.objects
        .filter(
            product=product,
            sale__status='completed',
            sale__sale_date__date__gte=start_date,
            sale__sale_date__date__lte=end_date,
        )
        .values_list('sale__sale_date', 'quantity')
    )

    total_days = (end_date - start_date).days + 1
    num_weeks = max(1, -(-total_days // 7))  # ceiling division

    weekly_totals = [0] * num_weeks
    for sale_datetime, quantity in sale_items:
        day_offset = (sale_datetime.date() - start_date).days
        week_index = min(day_offset // 7, num_weeks - 1)
        weekly_totals[week_index] += quantity

    return list(enumerate(weekly_totals))


def fit_forecast_model(weekly_series):
    """
    Fits a LinearRegression model to (week_index -> quantity_sold) and
    predicts the following week's demand.

    Returns a dict with predicted_quantity, historical_average, trend,
    confidence_score — all as plain floats (caller handles Decimal conversion).
    """
    week_indices = np.array([w for w, _ in weekly_series]).reshape(-1, 1)
    quantities = np.array([q for _, q in weekly_series], dtype=float)

    historical_average = float(quantities.mean())

    model = LinearRegression()
    model.fit(week_indices, quantities)

    next_week_index = np.array([[week_indices[-1][0] + 1]])
    predicted_quantity = max(0.0, float(model.predict(next_week_index)[0]))

    slope = float(model.coef_[0])
    r_squared = model.score(week_indices, quantities)

    # Trend classification: slope relative to historical average, guarding div-by-zero
    if historical_average > 0:
        slope_ratio = slope / historical_average
    else:
        slope_ratio = 0.0

    if slope_ratio > TREND_THRESHOLD_RATIO:
        trend = DemandForecast.TREND_INCREASING
    elif slope_ratio < -TREND_THRESHOLD_RATIO:
        trend = DemandForecast.TREND_DECREASING
    else:
        trend = DemandForecast.TREND_STABLE

    confidence_score = max(0.0, min(100.0, r_squared * 100))
    if len(weekly_series) < LOW_DATA_WEEK_COUNT:
        confidence_score = min(confidence_score, LOW_DATA_CONFIDENCE_CAP)

    return {
        "predicted_quantity": predicted_quantity,
        "historical_average": historical_average,
        "trend": trend,
        "confidence_score": confidence_score,
    }


def generate_forecast_for_product(product, today=None):
    """
    Generates and saves a single DemandForecast row for one product.
    Always creates a row — either a full prediction or an insufficient-data record.
    """
    today = today or timezone.localdate()
    first_sale_date = get_first_completed_sale_date(product)

    forecast_period_start = today
    forecast_period_end = today + timedelta(days=6)

    if first_sale_date is None or (today - first_sale_date).days < MIN_HISTORY_DAYS:
        return DemandForecast.objects.create(
            product=product,
            forecast_period_start=forecast_period_start,
            forecast_period_end=forecast_period_end,
            has_sufficient_data=False,
            insufficient_data_message=(
                "Needs at least 30 days of completed sales history to generate a forecast."
                if first_sale_date is None
                else f"Only {(today - first_sale_date).days} of {MIN_HISTORY_DAYS} required days of sales history available."
            ),
            model_version=MODEL_VERSION,
        )

    weekly_series = build_weekly_series(product, first_sale_date, today)
    result = fit_forecast_model(weekly_series)

    predicted_quantity = _to_decimal(result["predicted_quantity"])
    recommended_restock_quantity = _to_decimal(
        max(0, float(predicted_quantity) - product.quantity_in_stock)
    )

    return DemandForecast.objects.create(
        product=product,
        forecast_period_start=forecast_period_start,
        forecast_period_end=forecast_period_end,
        predicted_quantity=predicted_quantity,
        historical_average=_to_decimal(result["historical_average"]),
        trend=result["trend"],
        confidence_score=_to_decimal(result["confidence_score"]),
        recommended_restock_quantity=recommended_restock_quantity,
        has_sufficient_data=True,
        model_version=MODEL_VERSION,
    )


def generate_forecasts_for_all(today=None):
    """
    Generates forecasts for every active product.
    Returns a summary dict: {"generated": int, "insufficient_data": int, "total": int}.
    """
    today = today or timezone.localdate()
    active_products = Product.objects.filter(is_active=True)

    generated = 0
    insufficient = 0

    for product in active_products:
        forecast = generate_forecast_for_product(product, today=today)
        if forecast.has_sufficient_data:
            generated += 1
        else:
            insufficient += 1

    return {
        "generated": generated,
        "insufficient_data": insufficient,
        "total": active_products.count(),
    }