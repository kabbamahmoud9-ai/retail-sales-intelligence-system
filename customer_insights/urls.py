from django.urls import path
from . import views

app_name = 'customer_insights'

urlpatterns = [
    path('', views.customer_insights_dashboard, name='insights_dashboard'),
    path('customer/<int:customer_id>/', views.customer_insight_detail, name='detail'),
    path('customer/<int:customer_id>/regenerate/', views.regenerate_insight, name='regenerate'),
]