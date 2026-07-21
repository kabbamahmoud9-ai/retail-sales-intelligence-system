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
    path('customers/<int:pk>/approve-credit/', staff_views.approve_credit_recommendation, name='approve_credit_recommendation'),
    path('delivery-orders/', staff_views.delivery_order_list, name='delivery_order_list'),
    path('delivery-orders/<int:pk>/update/', staff_views.delivery_order_update, name='delivery_order_update'),
    path('customers/<int:pk>/record-repayment/', staff_views.record_credit_repayment, name='record_credit_repayment'),
]