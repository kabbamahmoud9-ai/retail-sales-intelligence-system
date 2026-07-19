"""
advisor/briefing.py

Generates a short, curated "Today's Priorities" list by pulling the
most actionable single item from each relevant data_gathering function.
Computed fresh on every page load — no persistence, no new model.
"""
from . import data_gathering as dg


def generate_daily_briefing(max_items=5):
    """
    Returns a list of short, human-readable priority strings, most
    actionable first. Silently skips any category with nothing
    noteworthy to report — an empty list is a valid, honest result
    (e.g. genuinely nothing urgent today), not a failure.
    """
    items = []

    restock = dg.get_restock_candidates(limit=1)
    if restock:
        r = restock[0]
        items.append(f"Restock {r['product'].product_name} — only {r['current_stock']} units left against {r['predicted_quantity']:.0f} predicted demand.")

    trend = dg.get_forecast_trend_summary()
    if trend['increasing_products']:
        name = trend['increasing_products'][0].product_name
        items.append(f"{name} demand is trending upward — worth watching stock levels closely.")

    slow = dg.get_slow_moving_products(limit=1)
    if slow and slow[0]['quantity_sold'] == 0:
        items.append(f"{slow[0]['product'].product_name} hasn't sold at all in the past 30 days — consider a promotion.")

    churn = dg.get_highest_churn_risk_customers(limit=1)
    if churn and churn[0].churn_risk_score and churn[0].churn_risk_score >= 0.5:
        c = churn[0]
        items.append(f"{c.customer.full_name} shows {c.churn_risk_score * 100:.0f}% churn risk — consider reaching out.")

    delivery = dg.get_delivery_zone_profitability()
    if delivery:
        best = delivery[0]
        items.append(f"{best['zone'].zone_name} is your most profitable delivery zone right now (~Le {best['estimated_profit_per_delivery']:.2f} per delivery).")

    credit = dg.get_customers_near_credit_limit(limit=1)
    if credit:
        c = credit[0]
        items.append(f"{c.full_name} is close to their credit limit (Le {c.credit_balance} of Le {c.credit_limit}).")

    blockchain = dg.get_blockchain_status()
    if not blockchain['is_valid']:
        items.insert(0, f"URGENT: audit ledger integrity check failed — {len(blockchain['broken_entries'])} broken entries detected.")

    return items[:max_items]