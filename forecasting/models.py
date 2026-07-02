from django.db import models
from products.models import Product


class DemandForecast(models.Model):
    """
    Stores a single AI-generated weekly demand forecast for one product.
    Every forecasting run creates NEW rows (history is never overwritten),
    so predicted-vs-actual accuracy can be analyzed later.
    """

    TREND_INCREASING = 'increasing'
    TREND_STABLE = 'stable'
    TREND_DECREASING = 'decreasing'

    TREND_CHOICES = [
        (TREND_INCREASING, 'Increasing'),
        (TREND_STABLE, 'Stable'),
        (TREND_DECREASING, 'Decreasing'),
    ]

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='forecasts',
    )

    forecast_period_start = models.DateField()
    forecast_period_end = models.DateField()

    predicted_quantity = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    historical_average = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    trend = models.CharField(
        max_length=10, choices=TREND_CHOICES, null=True, blank=True
    )
    confidence_score = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="0-100 confidence score derived from model fit (R²)."
    )
    recommended_restock_quantity = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="max(0, predicted_quantity - current_stock) at time of generation."
    )

    has_sufficient_data = models.BooleanField(default=True)
    insufficient_data_message = models.CharField(max_length=255, blank=True)

    generated_at = models.DateTimeField(auto_now_add=True)
    model_version = models.CharField(max_length=20, default='v1.0-linreg')

    class Meta:
        ordering = ['-generated_at']
        indexes = [
            models.Index(fields=['product', '-generated_at']),
        ]
        verbose_name = 'Demand Forecast'
        verbose_name_plural = 'Demand Forecasts'

    def __str__(self):
        if self.has_sufficient_data:
            return f"{self.product.product_name} — {self.forecast_period_start} to {self.forecast_period_end} — {self.predicted_quantity} units"
        return f"{self.product.product_name} — insufficient data ({self.generated_at.date()})"