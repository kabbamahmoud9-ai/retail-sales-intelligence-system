"""
ecommerce/urls.py
All customer-facing store URLs.
"""

from django.urls import path
from . import views

app_name = 'ecommerce'

urlpatterns = [
    # --- Store front ---
    path('', views.store_home, name='store_home'),
    path('product/<int:product_id>/', views.product_detail, name='product_detail'),

    # --- Cart ---
    path('cart/', views.cart_view, name='cart'),
    path('cart/add/<int:product_id>/', views.add_to_cart, name='add_to_cart'),
    path('cart/update/<int:product_id>/', views.update_cart, name='update_cart'),
    path('cart/remove/<int:product_id>/', views.remove_from_cart, name='remove_from_cart'),

    # --- Checkout & orders ---
    path('checkout/', views.checkout, name='checkout'),
    path('order/<int:order_id>/payment/', views.payment_simulation, name='payment'),
    path('order/<int:order_id>/confirm/', views.confirm_order, name='confirm_order'),
    path('orders/', views.order_history, name='order_history'),
    path('orders/<int:order_id>/', views.order_detail, name='order_detail'),
    path('credit/repay/', views.repay_credit, name='repay_credit'),
    path('order/<int:order_id>/repay-credit/', views.checkout_repayment, name='checkout_repayment'),

    # --- Customer auth ---
    path('register/', views.customer_register, name='register'),
    path('login/', views.customer_login, name='login'),
    path('logout/', views.customer_logout, name='logout'),
]