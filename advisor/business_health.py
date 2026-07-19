"""
advisor/business_health.py

Pure aggregation — computes a single business health summary from
existing data_gathering functions. No new model, no persistence;
recomputed fresh every time the Advisor page loads, same pattern as
the dashboard app's read-only aggregation views.
"""
from . import data_gathering as dg


def _inventory_health():
    restock_needed = len(dg.get_restock_candidates())
    overstocked = len(dg.get_overstocked_products())
    if restock_needed == 0 and overstocked == 0:
        return "Healthy"
    if restock_needed > 5 or overstocked > 5:
        return "Needs Attention"
    return "Fair"


def _sales_trend_health():
    trend = dg.get_forecast_trend_summary()
    increasing = len(trend['increasing_products'])
    decreasing = len(trend['decreasing_products'])
    if increasing > decreasing:
        return "Increasing"
    if decreasing > increasing:
        return "Decreasing"
    return "Stable"


def _customer_activity_health():
    at_risk = len(dg.get_customers_by_segment('at_risk'))
    vip = len(dg.get_customers_by_segment('vip'))
    if at_risk > vip:
        return "Needs Attention"
    return "Healthy"


def _forecast_confidence():
    trend = dg.get_forecast_trend_summary()
    return trend['average_confidence']


def _credit_risk_health():
    near_limit = len(dg.get_customers_near_credit_limit())
    if near_limit == 0:
        return "Low"
    if near_limit <= 3:
        return "Moderate"
    return "High"


def _expenses_health():
    summary = dg.get_expense_summary(days=30)
    # v1 heuristic: no budget model exists yet, so this simply reports
    # the raw 30-day figure rather than judging it against a threshold
    # that doesn't exist in the system yet — avoids inventing a fake
    # "within budget" judgment with no real basis.
    return f"Le {summary['total']:,.2f} (last 30 days)"


def _blockchain_health():
    status = dg.get_blockchain_status()
    return "Intact" if status['is_valid'] else "COMPROMISED"


def generate_business_health_summary():
    """
    Returns an ordered dict-like summary suitable for display on the
    Advisor page and for the conversational 'business_summary' intent.
    """
    confidence = _forecast_confidence()
    confidence_display = f"{confidence:.0f}%" if confidence is not None else "N/A"

    return {
        "Inventory": _inventory_health(),
        "Sales Trend": _sales_trend_health(),
        "Customer Activity": _customer_activity_health(),
        "Forecast Confidence": confidence_display,
        "Credit Risk": _credit_risk_health(),
        "Expenses": _expenses_health(),
        "Blockchain Ledger": _blockchain_health(),
    }