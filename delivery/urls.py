from django.urls import path
from . import views

urlpatterns = [
    path('', views.zone_list, name='zone_list'),
    path('add/', views.zone_add, name='zone_add'),
    path('<int:pk>/edit/', views.zone_edit, name='zone_edit'),
    path('<int:pk>/delete/', views.zone_delete, name='zone_delete'),
    path('performance/', views.zone_performance, name='zone_performance'),
]