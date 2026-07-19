from django.contrib import admin
from .models import Recommendation, AdvisorConversationSession, AdvisorConversationTurn


@admin.register(Recommendation)
class RecommendationAdmin(admin.ModelAdmin):
    list_display = ('product', 'priority', 'recommended_action', 'confidence_score', 'is_actioned', 'generated_at')
    list_filter = ('priority', 'is_actioned')
    search_fields = ('product__product_name',)


class AdvisorConversationTurnInline(admin.TabularInline):
    model = AdvisorConversationTurn
    extra = 0
    readonly_fields = ('role', 'message_text', 'intent_detected', 'routed_to', 'created_at')
    can_delete = False


@admin.register(AdvisorConversationSession)
class AdvisorConversationSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'staff_user', 'started_at', 'last_message_at')
    list_filter = ('started_at',)
    search_fields = ('staff_user__username',)
    readonly_fields = ('staff_user', 'context_state', 'started_at', 'last_message_at')
    inlines = [AdvisorConversationTurnInline]

    def has_add_permission(self, request):
        return False


@admin.register(AdvisorConversationTurn)
class AdvisorConversationTurnAdmin(admin.ModelAdmin):
    list_display = ('id', 'session', 'role', 'intent_detected', 'routed_to', 'created_at')
    list_filter = ('role', 'routed_to')
    search_fields = ('message_text',)
    readonly_fields = ('session', 'role', 'message_text', 'intent_detected', 'routed_to', 'created_at')

    def has_add_permission(self, request):
        return False