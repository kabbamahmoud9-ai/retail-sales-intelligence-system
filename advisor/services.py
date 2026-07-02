"""
advisor/services.py
(corrected to match actual CustomerRequest.status and
Notification.notification_type field names)
"""
from products.models import Product
from forecasting.models import DemandForecast
from demand.models import CustomerRequest
from notifications.models import Notification
from .models import Recommendation


def _open_customer_request_count(product):
    """Counts unmet CustomerRequest entries (status='pending') for a product."""
    return CustomerRequest.objects.filter(product=product, status='pending').count()


def _latest_forecast(product):
    return DemandForecast.objects.filter(product=product).order_by('-generated_at').first()


def _build_recommendation(product, forecast, open_requests):
    predicted = float(forecast.predicted_quantity)
    current_stock = product.quantity_in_stock
    restock_qty = float(forecast.recommended_restock_quantity)
    stockout_risk = predicted > current_stock
    trending_up = forecast.trend == DemandForecast.TREND_INCREASING

    if stockout_risk and trending_up and open_requests > 0:
        priority = Recommendation.PRIORITY_CRITICAL
        message = (
            f"{product.product_name}: demand is trending up and predicted to exceed current stock "
            f"({current_stock} units on hand vs {predicted:.0f} predicted). "
            f"{open_requests} unmet customer request(s) logged for this product."
        )
    elif stockout_risk:
        priority = Recommendation.PRIORITY_HIGH
        message = (
            f"{product.product_name}: predicted demand ({predicted:.0f}) exceeds current stock "
            f"({current_stock} units) — stockout risk next week."
        )
    elif trending_up or open_requests > 0:
        priority = Recommendation.PRIORITY_MEDIUM
        message = (
            f"{product.product_name}: demand is trending up or customers are requesting it "
            f"({open_requests} open request(s)), though stock currently covers predicted demand."
        )
    else:
        priority = Recommendation.PRIORITY_LOW
        message = (
            f"{product.product_name}: demand is stable/decreasing and stock is sufficient "
            f"— no urgent action needed."
        )

    recommended_action = (
        f"Restock approximately {restock_qty:.0f} units" if restock_qty > 0
        else "No restock needed at this time"
    )
    return priority, message, recommended_action


def generate_recommendations():
    summary = {"created": 0, "critical": 0, "high": 0, "medium": 0, "low": 0}

    for product in Product.objects.filter(is_active=True):
        forecast = _latest_forecast(product)
        if forecast is None or not forecast.has_sufficient_data:
            continue

        open_requests = _open_customer_request_count(product)
        priority, message, recommended_action = _build_recommendation(product, forecast, open_requests)

        Recommendation.objects.create(
            product=product,
            forecast=forecast,
            priority=priority,
            message=message,
            recommended_action=recommended_action,
        )
        summary["created"] += 1
        summary[priority] += 1

        if priority in (Recommendation.PRIORITY_CRITICAL, Recommendation.PRIORITY_HIGH):
            Notification.objects.get_or_create(
                notification_type='ai',
                title=f"AI Advisor: {product.product_name} needs attention",
                message=message,
                defaults={
                    'action_url': f'/products/{product.id}/',
                    'action_label': 'View Product',
                },
            )

    return summary
# Add to advisor/services.py

from django.db.models import Max, Case, When, Value, IntegerField

_PRIORITY_ORDER = Case(
    When(priority=Recommendation.PRIORITY_CRITICAL, then=Value(0)),
    When(priority=Recommendation.PRIORITY_HIGH, then=Value(1)),
    When(priority=Recommendation.PRIORITY_MEDIUM, then=Value(2)),
    When(priority=Recommendation.PRIORITY_LOW, then=Value(3)),
    output_field=IntegerField(),
)


def get_latest_recommendations(limit=None, exclude_actioned=True):
    """
    Returns the most recent Recommendation per product (deduplicated across
    forecast runs), ordered by priority (Critical first) then recency.
    Used by the dashboard and, later, the Krio voice briefing.
    """
    latest_ids = (
        Recommendation.objects.values('product')
        .annotate(latest_id=Max('id'))
        .values_list('latest_id', flat=True)
    )
    qs = (
        Recommendation.objects.filter(id__in=latest_ids)
        .select_related('product', 'forecast')
        .annotate(priority_order=_PRIORITY_ORDER)
        .order_by('priority_order', '-generated_at')
    )
    if exclude_actioned:
        qs = qs.filter(is_actioned=False)
    return qs[:limit] if limit else qs