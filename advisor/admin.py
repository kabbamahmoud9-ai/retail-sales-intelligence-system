from django.contrib import admin
from .models import Recommendation


@admin.register(Recommendation)
class RecommendationAdmin(admin.ModelAdmin):
    list_display = ('product', 'priority', 'recommended_action', 'is_actioned', 'generated_at')
    list_filter = ('priority', 'is_actioned')
    search_fields = ('product__product_name',)