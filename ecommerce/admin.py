"""
ecommerce/admin.py
Registers e-commerce models in Django admin so staff can
view orders, manage customers, and update order statuses.
"""

from django.contrib import admin
from .models import OnlineCustomer, OnlineOrder, OnlineOrderItem


class OnlineOrderItemInline(admin.TabularInline):
    model = OnlineOrderItem
    extra = 0
    readonly_fields = ('subtotal',)


@admin.register(OnlineCustomer)
class OnlineCustomerAdmin(admin.ModelAdmin):
    list_display  = (
        'full_name', 'email', 'phone', 'loyalty_tier', 'trust_score',
        'lifetime_spending', 'total_orders', 'credit_limit', 'credit_balance',
        'is_active', 'created_at',
    )
    search_fields = ('full_name', 'email', 'phone')
    list_filter   = ('is_active',)
    readonly_fields = ('created_at', 'loyalty_tier')


@admin.register(OnlineOrder)
class OnlineOrderAdmin(admin.ModelAdmin):
    list_display  = (
        'order_reference', 'customer', 'status', 'payment_method', 'total_amount',
        'delivery_zone', 'delivery_fee', 'delivery_status', 'order_date',
    )
    list_filter   = ('status', 'payment_method', 'delivery_zone', 'delivery_status')
    search_fields = ('order_reference', 'customer__full_name', 'customer__email')
    readonly_fields = ('order_reference', 'transaction_hash', 'linked_sale', 'created_at', 'updated_at')
    inlines       = [OnlineOrderItemInline]