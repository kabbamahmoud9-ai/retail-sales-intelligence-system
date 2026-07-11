from django.contrib import admin
from .models import CustomerEvent, CustomerInsightSnapshot


@admin.register(CustomerEvent)
class CustomerEventAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'event_type', 'product', 'category', 'search_term', 'created_at')
    list_filter = ('event_type', 'created_at')
    search_fields = ('customer__full_name', 'search_term', 'session_key')
    readonly_fields = ('customer', 'session_key', 'event_type', 'product', 'category', 'search_term', 'created_at')

    def has_add_permission(self, request):
        return False


@admin.register(CustomerInsightSnapshot)
class CustomerInsightSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        'customer', 'segment', 'prediction_method', 'has_sufficient_data',
        'churn_risk_score', 'estimated_lifetime_value', 'generated_at'
    )
    list_filter = ('segment', 'prediction_method', 'has_sufficient_data')
    search_fields = ('customer__full_name',)
    readonly_fields = [f.name for f in CustomerInsightSnapshot._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False