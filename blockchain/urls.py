from django.urls import path
from . import views

app_name = 'blockchain'

urlpatterns = [
    path('verify/', views.verify_ledger, name='verify_ledger'),
]