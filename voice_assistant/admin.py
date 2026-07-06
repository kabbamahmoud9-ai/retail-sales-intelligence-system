from django.contrib import admin

from .models import VoiceInteraction


@admin.register(VoiceInteraction)
class VoiceInteractionAdmin(admin.ModelAdmin):
    list_display = (
        'interaction_type', 'customer', 'staff_user', 'routed_to',
        'was_successful', 'created_at',
    )
    list_filter = ('interaction_type', 'was_successful', 'recognition_language')
    search_fields = ('raw_transcript', 'response_summary', 'routed_to')
    readonly_fields = (
        'interaction_type', 'customer', 'staff_user', 'raw_transcript',
        'recognition_language', 'response_language', 'routed_to',
        'response_summary', 'created_at',
    )
    list_editable = ('was_successful',)

    def has_add_permission(self, request):
        # Interactions are only ever created by the application, never manually.
        return False