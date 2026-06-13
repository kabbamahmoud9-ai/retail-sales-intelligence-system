from django.urls import path
from . import views

urlpatterns = [
    path('', views.request_list, name='request_list'),
    path('add/', views.request_add, name='request_add'),
    path('<int:pk>/edit/', views.request_edit, name='request_edit'),
    path('<int:pk>/delete/', views.request_delete, name='request_delete'),
]