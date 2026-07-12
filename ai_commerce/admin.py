from django.contrib import admin
from .models import (
    ShoppingSession, ShoppingRecommendation, CreditAssessment,
    ConversationSession, ConversationTurn,
)


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


class ConversationTurnInline(admin.TabularInline):
    model = ConversationTurn
    extra = 0
    readonly_fields = ('role', 'message_text', 'intent_detected', 'routed_to', 'created_at')
    can_delete = False


@admin.register(ConversationSession)
class ConversationSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'started_at', 'last_message_at')
    list_filter = ('started_at',)
    search_fields = ('customer__full_name',)
    readonly_fields = ('customer', 'context_state', 'started_at', 'last_message_at')
    inlines = [ConversationTurnInline]

    def has_add_permission(self, request):
        return False


@admin.register(ConversationTurn)
class ConversationTurnAdmin(admin.ModelAdmin):
    list_display = ('id', 'session', 'role', 'intent_detected', 'routed_to', 'created_at')
    list_filter = ('role', 'routed_to')
    search_fields = ('message_text',)
    readonly_fields = ('session', 'role', 'message_text', 'intent_detected', 'routed_to', 'created_at')

    def has_add_permission(self, request):
        return False