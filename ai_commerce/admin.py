from django.contrib import admin
from .models import ShoppingSession, ShoppingRecommendation, CreditAssessment


class ShoppingRecommendationInline(admin.TabularInline):
    model = ShoppingRecommendation
    extra = 0
    readonly_fields = (
        'product', 'rank', 'reasoning', 'match_score',
        'confidence_score', 'assistant_version', 'added_to_cart', 'was_helpful',
    )
    can_delete = False


@admin.register(ShoppingSession)
class ShoppingSessionAdmin(admin.ModelAdmin):
    list_display = ('customer', 'mode', 'goal', 'quality_preference', 'created_at')
    list_filter = ('mode', 'goal', 'quality_preference')
    readonly_fields = ('created_at',)
    inlines = [ShoppingRecommendationInline]


@admin.register(CreditAssessment)
class CreditAssessmentAdmin(admin.ModelAdmin):
    list_display = (
        'customer', 'eligibility_status', 'recommended_credit_limit',
        'trust_score_snapshot', 'loyalty_tier_snapshot', 'generated_at',
    )
    list_filter = ('eligibility_status',)
    readonly_fields = [f.name for f in CreditAssessment._meta.fields]

    def has_add_permission(self, request):
        # Append-only via the service layer, not the admin.
        return False