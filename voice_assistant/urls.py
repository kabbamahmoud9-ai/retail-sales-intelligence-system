"""
voice_assistant/urls.py

Thin voice interaction endpoints. Mounted at /store/voice/ in
core/urls.py, alongside /store/ (ecommerce) and /store/assistant/
(ai_commerce) — these endpoints reuse the same customer session auth.
"""

from django.urls import path
from . import views

app_name = 'voice_assistant'

urlpatterns = [
    path(
        'shopping/<int:session_id>/read-aloud/',
        views.read_recommendations_aloud,
        name='read_recommendations_aloud',
    ),
    path(
        'credit-loyalty/read-aloud/',
        views.read_credit_status_aloud,
        name='read_credit_status_aloud',
    ),
]