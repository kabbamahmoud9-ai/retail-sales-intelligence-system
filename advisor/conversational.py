"""
advisor/conversational.py

Orchestration layer for the AI Business Consultant (Step 19). Contains
ZERO business logic of its own — every question is routed to a read-only
function in advisor.data_gathering, which in turn reads from existing
services across forecasting, sales, customer_insights, ecommerce,
delivery, expenses, and blockchain. This file's only job: classify staff
questions (rule-based keyword matching), route to the correct
data_gathering function, and phrase a natural, professional,
Sierra-Leonean-toned response.

Language: English only in v1. The handler functions below are the
designed extension seam for Krio — adding a second phrase-template set
keyed by language and a language-detection step is the only work
required later; nothing else in this file would need to change (same
"documented seam" philosophy as ai_commerce/llm_adapter.py's optional
Gemini backend).
"""
import re

from . import data_gathering as dg
from .business_health import generate_business_health_summary
from django.conf import settings

CONVERSATIONAL_VERSION = "v1-rule-based"

_INTENT_PATTERNS = {
    'restock_question':      {'restock', 'reorder', 'order more'},
    'slow_moving_question':  {'slow', 'not selling', 'stagnant', 'unsold'},
    'overstocked_question':  {'overstocked', 'too much stock', 'excess'},
    'top_sellers_question':  {'top selling', 'best selling', 'bestseller', 'sell pass'},
    'todays_sales_question': {'today sales', 'sales today'},
    'forecast_question':     {'forecast', 'demand', 'trend', 'increasing', 'decreasing'},
    'churn_question':        {'churn', 'at risk', 'atrisk', 'leaving', 'stop buying'},
    'vip_question':          {'vip', 'loyal', 'best customer', 'reward'},
    'credit_question':       {'credit limit', 'owe', 'overdue', 'balance'},
    'delivery_question':     {'delivery zone', 'profitable zone', 'delivery profit', 'delivery perform'},
    'expense_question':      {'expense', 'spending', 'cost'},
    'blockchain_question':   {'blockchain', 'ledger', 'audit', 'tamper'},
    'business_summary':      {'summary', 'briefing', 'business health', 'how am i doing', 'overview'},
    'advice_question':       {'suggest', 'advice', 'recommend', 'increase sales', 'boost sales',
                               'grow sales', 'sell more', 'reduce churn', 'improve business', 'what should i do'},
    'greeting':              {'hello', 'hi', 'hey', 'good morning', 'good afternoon'},
    'business_diagnostic': {'why', 'how is business', 'how is the business', 'biggest risk',
                             'concerning', 'improve retention', 'most valuable', 'costing us',
                             'what should management', 'focus on this week'},
}


def _classify_intent(message_text):
    """
    Tokenizes the message into lowercase word tokens, then matches
    keywords via PREFIX matching per token (e.g. keyword "zone" matches
    token "zones", "owe" matches "owes", "suggest" matches "suggestions")
    — this handles plurals and verb inflections without needing an
    explicit variant for every possible word form.

    Multi-word phrases match if ALL component words are present
    somewhere in the message as token prefixes, in ANY order — so
    "selling best" and "best selling" both match the phrase
    "best selling", and "delivery zones" matches "delivery zone".
    """
    raw_tokens = re.findall(r'[a-z]+', message_text.lower())

    def _phrase_matches(phrase):
        words = phrase.split()
        return all(
            any(token.startswith(word) for token in raw_tokens)
            for word in words
        )

    for intent, keywords in _INTENT_PATTERNS.items():
        for kw in keywords:
            if _phrase_matches(kw):
                return intent

    return 'unclear'


# ---------------------------------------------------------------------------
# Personality / tone layer — template-based, English only for v1.
# Professional, warm, encouraging Sierra Leonean business-consultant voice.
# ---------------------------------------------------------------------------

def _handle_restock(staff_user):
    candidates = dg.get_restock_candidates()
    if not candidates:
        return "Good news — every product with a reliable forecast currently has enough stock. No urgent restocking needed right now.", 'restock'
    lines = ["Here's what I'd recommend restocking soon, starting with the most urgent:"]
    for c in candidates[:5]:
        lines.append(
            f"- {c['product'].product_name}: {c['current_stock']} units in stock, "
            f"forecast expects demand of {c['predicted_quantity']:.0f} — "
            f"recommend ordering {c['recommended_restock_quantity']:.0f} more "
            f"(confidence {c['confidence_score']:.0f}%)"
        )
    return "\n".join(lines), 'restock'


def _handle_slow_moving(staff_user):
    products = dg.get_slow_moving_products()
    lines = ["These products haven't been moving well over the past 30 days — worth considering a promotion or a closer look at pricing:"]
    for p in products[:5]:
        lines.append(f"- {p['product'].product_name}: only {p['quantity_sold']} units sold")
    return "\n".join(lines), 'slow_moving'


def _handle_overstocked(staff_user):
    products = dg.get_overstocked_products()
    if not products:
        return "Stock levels look well-balanced against demand right now — nothing significantly overstocked.", 'overstocked'
    lines = ["These products are carrying more stock than forecasted demand suggests you need:"]
    for p in products[:5]:
        lines.append(f"- {p['product'].product_name}: {p['current_stock']} in stock vs. {p['predicted_quantity']:.0f} predicted demand")
    return "\n".join(lines), 'overstocked'


def _handle_top_sellers(staff_user):
    rows = dg.get_top_selling_products()
    if not rows:
        return "No completed sales in the last 7 days yet to rank.", 'top_sellers'
    lines = ["Here's what's selling best this week:"]
    for r in rows:
        lines.append(f"- {r['product__product_name']}: {r['total_quantity']} units")
    return "\n".join(lines), 'top_sellers'


def _handle_todays_sales(staff_user):
    summary = dg.get_todays_sales_summary()
    if summary['total_sales'] == 0:
        return "No completed sales recorded yet today.", 'todays_sales'
    return (
        f"Today so far: {summary['total_sales']} completed sale(s), "
        f"totaling Le {summary['total_revenue']:,.2f} in revenue."
    ), 'todays_sales'


def _handle_forecast(staff_user):
    trend = dg.get_forecast_trend_summary()
    conf = f"{trend['average_confidence']:.0f}%" if trend['average_confidence'] is not None else "not available"
    lines = [
        f"I currently have reliable forecasts for {trend['total_forecasted']} products, "
        f"with an average confidence of {conf}."
    ]
    if trend['increasing_products']:
        names = ", ".join(p.product_name for p in trend['increasing_products'][:5])
        lines.append(f"Demand is trending up for: {names}.")
    if trend['decreasing_products']:
        names = ", ".join(p.product_name for p in trend['decreasing_products'][:5])
        lines.append(f"Demand is trending down for: {names}.")
    return " ".join(lines), 'forecast'


def _handle_churn(staff_user):
    customers = dg.get_highest_churn_risk_customers()
    if not customers:
        return "No customers currently show a meaningful churn risk signal.", 'churn'
    lines = ["These customers show the highest risk of not returning — might be worth a personal follow-up:"]
    for s in customers:
        lines.append(f"- {s.customer.full_name}: {s.churn_risk_score * 100:.0f}% churn risk")
    return "\n".join(lines), 'churn'


def _handle_vip(staff_user):
    customers = dg.get_customers_by_segment('vip')
    if not customers:
        return "No customers currently qualify as VIP under the current segmentation.", 'vip'
    lines = ["Your VIP customers — worth prioritizing for loyalty rewards:"]
    for s in customers:
        lines.append(f"- {s.customer.full_name}")
    return "\n".join(lines), 'vip'


def _handle_credit(staff_user):
    customers = dg.get_customers_near_credit_limit()
    if not customers:
        return "No customers are currently near their credit limit.", 'credit'
    lines = ["These customers are close to their credit limit:"]
    for c in customers:
        lines.append(f"- {c.full_name}: Le {c.credit_balance} of Le {c.credit_limit} used")
    return "\n".join(lines), 'credit'


def _handle_delivery(staff_user):
    zones = dg.get_delivery_zone_profitability()
    if not zones:
        return "No active delivery zones to report on.", 'delivery'
    lines = ["Here's how your delivery zones compare on estimated profitability:"]
    for z in zones[:5]:
        lines.append(
            f"- {z['zone'].zone_name}: ~Le {z['estimated_profit_per_delivery']:.2f} estimated profit per delivery, "
            f"{z['order_count']} orders delivered"
        )
    return "\n".join(lines), 'delivery'


def _handle_expenses(staff_user):
    summary = dg.get_expense_summary()
    lines = [f"Over the last {summary['days']} days, total expenses were Le {summary['total']:,.2f}."]
    if summary['by_category']:
        top = summary['by_category'][0]
        lines.append(f"The largest category was {top['category__name']} at Le {top['total']:,.2f}.")
    return " ".join(lines), 'expenses'


def _handle_blockchain(staff_user):
    status = dg.get_blockchain_status()
    if status['is_valid']:
        return f"The audit ledger is fully intact — all {status['total_entries']} entries verified, no tampering detected.", 'blockchain'
    return f"Warning: the audit ledger shows {len(status['broken_entries'])} broken entr(y/ies) out of {status['total_entries']}. This needs immediate attention.", 'blockchain'


def _handle_advice(staff_user):
    """
    Synthesizes a few existing signals into general business advice.
    Still zero new logic — purely combines already-built data_gathering
    functions (top sellers, slow movers, churn risk, restock candidates)
    into one cohesive response.
    """
    lines = ["Here's what I'd focus on right now:"]

    top = dg.get_top_selling_products(limit=2)
    if top:
        names = ", ".join(r['product__product_name'] for r in top)
        lines.append(f"- Keep {names} well-stocked — they're your strongest sellers this week.")

    slow = dg.get_slow_moving_products(limit=2)
    if slow and slow[0]['quantity_sold'] == 0:
        lines.append(f"- {slow[0]['product'].product_name} hasn't moved in 30 days — a small promotion or price review could help.")

    churn = dg.get_highest_churn_risk_customers(limit=2)
    if churn and churn[0].churn_risk_score and churn[0].churn_risk_score >= 0.5:
        names = ", ".join(s.customer.full_name for s in churn if s.churn_risk_score and s.churn_risk_score >= 0.5)
        lines.append(f"- Reach out personally to {names} — they show high churn risk and a check-in could win back their loyalty.")

    restock = dg.get_restock_candidates(limit=1)
    if restock:
        lines.append(f"- Don't let {restock[0]['product'].product_name} run out — restock it soon based on current demand.")

    if len(lines) == 1:
        lines.append("Everything looks steady right now — no urgent action needed, but keep an eye on trends.")

    return "\n".join(lines), 'advice'


def _handle_greeting(staff_user):
    name = staff_user.get_full_name() or staff_user.username
    return f"Hello {name}! I'm your AI Business Consultant — ask me about restocking, sales, forecasts, customers, credit, delivery, expenses, or the audit ledger, and I'll pull the real numbers for you.", 'greeting'


def _handle_unclear(staff_user):
    return (
        "I'm not sure I understood that. Try asking things like: "
        "\"Which products should I restock?\", \"What's today's sales summary?\", "
        "\"Which customers are at risk of churning?\", or \"Is the blockchain ledger intact?\""
    ), 'unclear'
def _handle_business_diagnostic(staff_user):
    """
    Cross-module synthesis for open-ended business questions. Rule-based
    reply lists the raw facts plainly; the LLM (when active) does the
    actual synthesis/explanation over this same structured data — see
    llm_explainer.explain_diagnostic().
    """
    context = dg.get_business_diagnostic_context()
    lines = [
        f"Today's sales: {context['todays_sales']['total_sales']} sale(s), Le {context['todays_sales']['total_revenue']:,.2f}.",
        f"Expenses (30 days): Le {context['expenses_30d']['total']:,.2f}.",
        f"Forecast confidence: {context['forecast_trend']['average_confidence'] or 'N/A'}.",
        f"Highest churn risk customers: {len(context['highest_churn_risk_customers'])} flagged.",
        f"Blockchain ledger: {'intact' if context['blockchain_status']['is_valid'] else 'COMPROMISED'}.",
    ]
    return "\n".join(lines), 'business_diagnostic', context

_INTENT_HANDLERS = {
    'restock_question':      _handle_restock,
    'slow_moving_question':  _handle_slow_moving,
    'overstocked_question':  _handle_overstocked,
    'top_sellers_question':  _handle_top_sellers,
    'todays_sales_question': _handle_todays_sales,
    'forecast_question':     _handle_forecast,
    'churn_question':        _handle_churn,
    'vip_question':          _handle_vip,
    'credit_question':       _handle_credit,
    'delivery_question':     _handle_delivery,
    'expense_question':      _handle_expenses,
    'blockchain_question':   _handle_blockchain,
    'advice_question':       _handle_advice,
    'greeting':              _handle_greeting,
    'unclear':               _handle_unclear,
    'business_diagnostic':   _handle_business_diagnostic,
}


def process_message(session, staff_user, message_text):
    from .models import AdvisorConversationTurn

    AdvisorConversationTurn.objects.create(session=session, role='staff', message_text=message_text)

    intent = _classify_intent(message_text)

    if intent == 'business_summary':
        summary = generate_business_health_summary()
        reply_text = "\n".join(f"{k}: {v}" for k, v in summary.items())
        routed_to = 'business_health'
    else:
        handler = _INTENT_HANDLERS.get(intent, _handle_unclear)
        result = handler(staff_user)
        if len(result) == 3:
            reply_text, routed_to, diagnostic_context = result
        else:
            reply_text, routed_to = result
            diagnostic_context = None

    provider = getattr(settings, 'AI_PROVIDER', 'rule_based')
    if provider != 'rule_based' and intent != 'unclear':
        from .llm_explainer import explain
        if diagnostic_context:
            explained = explain(reply_text, message_text, structured_context=diagnostic_context)
        else:
            explained = explain(reply_text, message_text)
        if explained:
            reply_text = explained
            routed_to = f"{routed_to}+{provider}"

    session.save(update_fields=['context_state', 'last_message_at'])

    AdvisorConversationTurn.objects.create(
        session=session, role='assistant', message_text=reply_text,
        intent_detected=intent, routed_to=routed_to,
    )

    return reply_text