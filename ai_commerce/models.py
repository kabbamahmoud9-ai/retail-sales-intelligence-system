"""
Models for the ai_commerce app.

This app houses all customer-facing AI features: the AI Shopping Assistant
(natural language / guided planner / shop-by-goal modes) and the Smart
Credit & Loyalty Assistant. It is deliberately separate from `ecommerce`
(which owns products, carts, checkout, and orders) so that AI-driven
customer intelligence can evolve independently — and so future modules
(e.g. the Step 13 Krio Voice Assistant) have a single, obvious place to
read AI-generated recommendations and assessments from.
"""

from django.db import models


class ShoppingSession(models.Model):
    """
    A single AI Shopping Assistant interaction, in any of the 3 supported modes.

    Only the fields relevant to the session's mode are populated; the others
    stay null. Budget is always a soft preference for ranking, never a hard
    filter — this is enforced in the recommendation service, not here.
    """

    MODE_CHOICES = [
        ('natural_language', 'Natural Language'),
        ('guided_planner', 'Guided Shopping Planner'),
        ('shop_by_goal', 'Shop by Goal'),
    ]

    QUALITY_CHOICES = [
        ('budget', 'Budget'),
        ('standard', 'Standard'),
        ('premium', 'Premium'),
    ]

    GOAL_CHOICES = [
        ('save_money', 'Save Money'),
        ('premium_quality', 'Premium Quality'),
        ('healthy_living', 'Healthy Living'),
        ('party_shopping', 'Party Shopping'),
        ('weekly_groceries', 'Weekly Groceries'),
    ]

    customer = models.ForeignKey(
        'ecommerce.OnlineCustomer',
        on_delete=models.CASCADE,
        related_name='shopping_sessions',
    )
    mode = models.CharField(max_length=20, choices=MODE_CHOICES)

    # Mode 1: Natural Language
    raw_query = models.TextField(blank=True, null=True)
    parsed_intent = models.JSONField(
        blank=True, null=True,
        help_text="Structured intent extracted from raw_query before candidate filtering."
    )

    # Shared / Mode 2
    budget = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True,
        help_text="Soft preference for ranking, never a hard filter."
    )
    family_size = models.PositiveIntegerField(blank=True, null=True)
    shopping_purpose = models.CharField(max_length=100, blank=True, null=True)
    quality_preference = models.CharField(
        max_length=20, choices=QUALITY_CHOICES, blank=True, null=True
    )

    # Mode 3: Shop by Goal
    goal = models.CharField(max_length=30, choices=GOAL_CHOICES, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Shopping Session'
        verbose_name_plural = 'Shopping Sessions'

    def __str__(self):
        return f"{self.customer} - {self.get_mode_display()} ({self.created_at:%Y-%m-%d %H:%M})"


class ShoppingRecommendation(models.Model):
    """
    A single product recommended to a customer within a ShoppingSession.

    Rows are append-only (never overwritten), the same philosophy as
    DemandForecast — this preserves a full history for future accuracy
    analysis and dissertation evaluation of recommendation quality.

    `confidence_score` and `assistant_version` support reproducibility
    and future prompt evolution: as the Claude prompt used in
    generate_shopping_recommendations() changes, `assistant_version` lets
    us tell which version of the assistant produced any given row.
    """

    session = models.ForeignKey(
        ShoppingSession, on_delete=models.CASCADE, related_name='recommendations'
    )
    product = models.ForeignKey(
        'products.Product', on_delete=models.CASCADE, related_name='ai_recommendations'
    )
    rank = models.PositiveIntegerField(help_text="Display order within the session's basket.")
    reasoning = models.TextField(help_text="Claude's human-readable explanation for this pick.")
    match_score = models.FloatField(
        default=0.0, help_text="Internal ranking score from the candidate-filtering stage."
    )
    confidence_score = models.FloatField(
        default=0.0, help_text="AI's confidence in this recommendation, 0.0-1.0."
    )
    assistant_version = models.CharField(
        max_length=20, default='v1',
        help_text="Identifies which prompt/assistant version generated this row."
    )
    added_to_cart = models.BooleanField(default=False)
    was_helpful = models.BooleanField(
        blank=True, null=True,
        help_text="Customer feedback. Null means no feedback was given."
    )
    feedback_notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['session', 'rank']
        verbose_name = 'Shopping Recommendation'
        verbose_name_plural = 'Shopping Recommendations'
        indexes = [models.Index(fields=['session', 'rank'])]

    def __str__(self):
        return f"{self.product} (rank {self.rank}) - session #{self.session_id}"


class CreditAssessment(models.Model):
    """
    A single run of the Smart Credit Assistant's rule-based eligibility formula.

    Append-only, same pattern as DemandForecast/ShoppingRecommendation — always
    read the latest row per customer, keep full history. This model only ever
    RECOMMENDS a limit; OnlineCustomer.credit_limit remains the actual
    staff-approved limit and is never written to by this app.

    The calculation itself lives in ai_commerce/services.py so it can be
    swapped for an ML model later without touching this model or any caller.
    """

    ELIGIBILITY_CHOICES = [
        ('eligible_increase', 'Eligible for Increase'),
        ('maintain', 'Maintain Current Limit'),
        ('review_needed', 'Review Needed'),
    ]

    customer = models.ForeignKey(
        'ecommerce.OnlineCustomer', on_delete=models.CASCADE, related_name='credit_assessments'
    )
    trust_score_snapshot = models.PositiveIntegerField()
    loyalty_tier_snapshot = models.CharField(max_length=20)
    lifetime_spending_snapshot = models.DecimalField(max_digits=12, decimal_places=2)
    outstanding_balance_snapshot = models.DecimalField(max_digits=12, decimal_places=2)
    recommended_credit_limit = models.DecimalField(max_digits=12, decimal_places=2)
    eligibility_status = models.CharField(max_length=20, choices=ELIGIBILITY_CHOICES)
    reasoning = models.TextField()
    assistant_version = models.CharField(max_length=20, default='v1')
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-generated_at']
        verbose_name = 'Credit Assessment'
        verbose_name_plural = 'Credit Assessments'

    def __str__(self):
        return (
            f"{self.customer} - {self.get_eligibility_status_display()} "
            f"(Le {self.recommended_credit_limit}) @ {self.generated_at:%Y-%m-%d}"
        )
class ConversationSession(models.Model):
    """
    A single multi-turn Conversational Shopping AI session (Mode 4).

    Unlike ShoppingSession (one row per single request/response), a
    ConversationSession spans an entire back-and-forth conversation.
    context_state accumulates slot-filled information across turns
    (e.g. budget, occasion, dietary preference) so later turns in the
    same conversation can reference earlier ones without re-asking.

    This model holds NO business logic itself — it is purely state.
    All actual intelligence (intent classification, routing to the
    Shopping Assistant / Credit Assistant / Visual Search / Customer
    Insights / Delivery services) lives in ai_commerce/conversational.py.
    """

    customer = models.ForeignKey(
        'ecommerce.OnlineCustomer',
        on_delete=models.CASCADE,
        related_name='conversation_sessions',
        null=True, blank=True,
        help_text="Nullable — guest conversations are supported, same as CustomerEvent."
    )
    context_state = models.JSONField(
        default=dict, blank=True,
        help_text="Accumulated slot-filled context across turns, e.g. "
                   "{'budget': 15000, 'occasion': 'party', 'dietary': 'no pork'}"
    )
    started_at = models.DateTimeField(auto_now_add=True)
    last_message_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-last_message_at']
        verbose_name = 'Conversation Session'
        verbose_name_plural = 'Conversation Sessions'

    def __str__(self):
        who = self.customer.full_name if self.customer else f"Guest session #{self.pk}"
        return f"{who} — started {self.started_at:%Y-%m-%d %H:%M}"


class ConversationTurn(models.Model):
    """
    A single message within a ConversationSession — either the customer's
    message or the assistant's reply. Append-only, same philosophy as
    ShoppingRecommendation/CreditAssessment — full conversation history
    is retained for dissertation evaluation of multi-turn coherence.

    routed_to records which existing service actually handled this turn
    (e.g. 'shopping_assistant', 'credit_assistant', 'visual_search',
    'customer_insights', 'delivery', 'llm_adapter') — useful both for
    debugging and as evidence the orchestration layer is genuinely
    routing to existing services rather than reimplementing logic.
    """

    ROLE_CHOICES = [
        ('user', 'Customer'),
        ('assistant', 'Assistant'),
    ]

    session = models.ForeignKey(
        ConversationSession, on_delete=models.CASCADE, related_name='turns'
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    message_text = models.TextField()
    intent_detected = models.CharField(max_length=50, blank=True)
    routed_to = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['session', 'created_at']
        verbose_name = 'Conversation Turn'
        verbose_name_plural = 'Conversation Turns'
        indexes = [models.Index(fields=['session', 'created_at'])]

    def __str__(self):
        preview = self.message_text[:50] + ('...' if len(self.message_text) > 50 else '')
        return f"[{self.get_role_display()}] {preview}"