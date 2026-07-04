"""
ecommerce/staff_urls.py

Staff-facing URLs (Django auth) — deliberately separate from urls.py,
which is the namespaced ('ecommerce:') customer-facing store. Mounted
at top level (not under /store/) in core/urls.py.
"""

from django.urls import path
from . import staff_views

urlpatterns = [
    path('customers/', staff_views.customer_intelligence_list, name='customer_intelligence_list'),
    path('customers/<int:pk>/', staff_views.customer_intelligence_detail, name='customer_intelligence_detail'),
    path('delivery-orders/', staff_views.delivery_order_list, name='delivery_order_list'),
    path('delivery-orders/<int:pk>/update/', staff_views.delivery_order_update, name='delivery_order_update'),
]