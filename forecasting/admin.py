from django.contrib import admin
from .models import DemandForecast


@admin.register(DemandForecast)
class DemandForecastAdmin(admin.ModelAdmin):
    list_display = (
        'product', 'forecast_period_start', 'forecast_period_end',
        'predicted_quantity', 'trend', 'confidence_score',
        'has_sufficient_data', 'generated_at',
    )
    list_filter = ('trend', 'has_sufficient_data', 'model_version')
    search_fields = ('product__product_name',)
    readonly_fields = ('generated_at',)