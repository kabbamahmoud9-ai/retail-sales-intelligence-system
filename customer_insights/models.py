from django.db import models
from django.utils import timezone

from ecommerce.models import OnlineCustomer
from products.models import Product, Category


# ---------------------------------------------------------------------------
# CustomerEvent — lightweight, append-only browsing signal
# ---------------------------------------------------------------------------

class CustomerEvent(models.Model):
    """
    Append-only log of lightweight browsing events, captured server-side
    from existing ecommerce views (store_home, product_detail) — no new
    JS, no new endpoints. Guests are tracked via session_key; customer
    is nullable and only set when the browsing session is logged in.

    Never read from or written to outside this app except for the two
    small instrumentation points added to ecommerce views in Step 16b.
    """

    EVENT_TYPE_CHOICES = [
        ('product_view',  'Product View'),
        ('category_view', 'Category View'),
        ('search_query',  'Search Query'),
    ]

    customer     = models.ForeignKey(
        OnlineCustomer, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='events'
    )
    session_key  = models.CharField(max_length=40, blank=True)
    event_type   = models.CharField(max_length=20, choices=EVENT_TYPE_CHOICES)

    product      = models.ForeignKey(
        Product, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='view_events'
    )
    category     = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='view_events'
    )
    search_term  = models.CharField(max_length=200, blank=True)

    created_at   = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Customer Event"
        verbose_name_plural = "Customer Events"

    def __str__(self):
        who = self.customer.full_name if self.customer else f"Guest ({self.session_key[:8]})"
        return f"{who} — {self.event_type} @ {self.created_at:%Y-%m-%d %H:%M}"


# ---------------------------------------------------------------------------
# CustomerInsightSnapshot — append-only, one row per generation run
# ---------------------------------------------------------------------------

class CustomerInsightSnapshot(models.Model):
    """
    Append-only, never overwritten — mirrors DemandForecast's philosophy
    of retaining full history so a customer's segment/churn-risk/etc. can
    be tracked over time. Consumers always read the latest row per
    customer (highest generated_at).

    Only ever created via customer_insights.services.generate_customer_insight() —
    never constructed directly elsewhere, same discipline as
    blockchain.LedgerEntry / forecasting.DemandForecast.
    """

    SEGMENT_CHOICES = [
        ('vip',              'VIP'),
        ('loyal',            'Loyal'),
        ('new',               'New'),
        ('at_risk',          'At-Risk'),
        ('price_sensitive',  'Price-Sensitive'),
        ('premium_shopper',  'Premium Shopper'),
        ('frequent_buyer',   'Frequent Buyer'),
    ]

    PREDICTION_METHOD_CHOICES = [
        ('ml',          'Machine Learning'),
        ('rule_based',  'Rule-Based Heuristic'),
    ]

    customer    = models.ForeignKey(
        OnlineCustomer, on_delete=models.CASCADE,
        related_name='insight_snapshots'
    )
    generated_at = models.DateTimeField(default=timezone.now)

    segment     = models.CharField(max_length=20, choices=SEGMENT_CHOICES)

    # --- Behaviour metrics, snapshotted at generation time ---------------
    avg_order_value          = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    order_frequency_days     = models.FloatField(null=True, blank=True)
    favorite_category        = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='top_customer_snapshots'
    )
    preferred_payment_method = models.CharField(max_length=20, blank=True)
    preferred_shopping_time  = models.CharField(max_length=20, blank=True, help_text="e.g. morning/afternoon/evening/night")

    # --- Predictive insights ----------------------------------------------
    has_sufficient_data          = models.BooleanField(default=False)
    prediction_method            = models.CharField(max_length=20, choices=PREDICTION_METHOD_CHOICES, default='rule_based')
    churn_risk_score              = models.FloatField(null=True, blank=True, help_text="0.0-1.0 probability")
    predicted_next_purchase_date  = models.DateField(null=True, blank=True)
    estimated_lifetime_value      = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    # --- Personalized intelligence -----------------------------------------
    ai_summary_text        = models.TextField(blank=True)
    recommended_product_ids = models.JSONField(default=list, blank=True)

    model_version = models.CharField(max_length=50, default='v1')

    class Meta:
        ordering = ['-generated_at']
        verbose_name = "Customer Insight Snapshot"
        verbose_name_plural = "Customer Insight Snapshots"

    def __str__(self):
        return f"{self.customer.full_name} — {self.get_segment_display()} @ {self.generated_at:%Y-%m-%d}"