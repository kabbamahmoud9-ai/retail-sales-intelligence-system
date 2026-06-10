from django.urls import path
from . import views

urlpatterns = [
    path('', views.sale_list, name='sale_list'),
    path('new/', views.sale_new, name='sale_new'),
    path('<int:pk>/', views.sale_detail, name='sale_detail'),
    path('<int:pk>/delete/', views.sale_delete, name='sale_delete'),
]