"""
ecommerce/services.py

Customer intelligence services: loyalty tier and trust score calculation.

Both are deliberately kept OUT of the OnlineCustomer model and instead
live here as standalone functions. This is intentional:

  - loyalty_tier: currently a simple threshold lookup on lifetime_spending,
    but may later factor in purchase frequency, trust score, or
    promotional campaigns. Keeping it a service function (not a model
    method) means richer logic can be swapped in later without touching
    the model.

  - trust_score: a rule-based v1 implementation today. Deliberately
    encapsulated in calculate_trust_score() so it can be replaced by a
    machine-learning model later without changing anything that calls it
    (OnlineCustomer.record_confirmed_order() just calls this function and
    stores whatever it returns).
"""

from decimal import Decimal


# ---------------------------------------------------------------------------
# Loyalty tiers
# ---------------------------------------------------------------------------

# Stored as configuration constants (not scattered magic numbers) so
# thresholds can be adjusted in one place. Values are lifetime spending
# in Leones (Le). Ordered highest-to-lowest so the first match wins.
LOYALTY_TIER_THRESHOLDS = [
    ('Platinum', Decimal('10000.00')),
    ('Gold',     Decimal('5000.00')),
    ('Silver',   Decimal('1000.00')),
    ('Bronze',   Decimal('0.00')),
]


def calculate_loyalty_tier(customer):
    """
    Return the loyalty tier name for a customer based on lifetime_spending.

    Kept as a service function (not a model property) so future versions
    can factor in purchase frequency, trust_score, or promotional
    campaigns without changing the model or any code that calls this.
    """
    spending = customer.lifetime_spending or Decimal('0.00')
    for tier_name, minimum in LOYALTY_TIER_THRESHOLDS:
        if spending >= minimum:
            return tier_name
    return 'Bronze'


# ---------------------------------------------------------------------------
# Trust score
# ---------------------------------------------------------------------------

def calculate_trust_score(customer):
    """
    Rule-based trust score (0-100) for a customer, based on:
      - Order completion rate  (confirmed/delivered vs cancelled orders)
      - Credit utilization      (proxy for payment history — we don't yet
                                  track individual repayments, so we use
                                  current outstanding balance vs credit
                                  limit as the v1 signal)
      - Purchase frequency      (orders per month since account creation)

    New customers with no order history start at a neutral 50.

    This function is the ONLY place trust-score logic lives. It is called
    from OnlineCustomer.record_confirmed_order() and can be swapped for a
    machine-learning model later without changing any caller.
    """
    orders = customer.orders.all()
    total_orders = orders.count()

    if total_orders == 0:
        return 50  # neutral starting point for customers with no history

    # --- Order completion rate (40 points max) ---------------------------
    cancelled = orders.filter(status='cancelled').count()
    completion_rate = (total_orders - cancelled) / total_orders
    completion_score = completion_rate * 40

    # --- Credit utilization (30 points max) -------------------------------
    if customer.credit_limit and customer.credit_limit > 0:
        utilization = float(customer.credit_balance) / float(customer.credit_limit)
        utilization = min(utilization, 1.0)
        credit_score = (1 - utilization) * 30
    else:
        credit_score = 15  # neutral — customer has never used credit

    # --- Purchase frequency (30 points max) --------------------------------
    from django.utils import timezone
    account_age_days = max((timezone.now() - customer.created_at).days, 1)
    months_active = max(account_age_days / 30, 1)
    orders_per_month = total_orders / months_active
    frequency_score = min(orders_per_month, 1.0) * 30

    total_score = completion_score + credit_score + frequency_score
    return round(min(max(total_score, 0), 100))