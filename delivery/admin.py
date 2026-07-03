from django.contrib import admin
from .models import DeliveryZone


@admin.register(DeliveryZone)
class DeliveryZoneAdmin(admin.ModelAdmin):
    list_display = (
        'zone_name', 'base_fee', 'per_km_rate', 'average_distance_km',
        'estimated_operational_cost', 'estimated_delivery_time_minutes', 'is_active',
    )
    list_filter = ('is_active',)
    search_fields = ('zone_name',)
    readonly_fields = ('created_at', 'updated_at')