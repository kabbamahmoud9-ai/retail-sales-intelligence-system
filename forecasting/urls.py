from django.urls import path
from . import views

urlpatterns = [
    path('', views.forecast_list, name='forecast_list'),
]