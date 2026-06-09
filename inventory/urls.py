from django.urls import path
from . import views

urlpatterns = [
    path('', views.inventory_list, name='inventory_list'),
    path('receive/', views.stock_receive, name='stock_receive'),
    path('adjust/', views.stock_adjust, name='stock_adjust'),
    path('low-stock/', views.low_stock, name='low_stock'),
]