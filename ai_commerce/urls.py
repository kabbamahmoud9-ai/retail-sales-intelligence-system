"""
ai_commerce/urls.py

Customer-facing URLs for the AI Shopping Assistant (3 modes) and the
Smart Credit & Loyalty Assistant. Mounted at /store/assistant/ in
core/urls.py, alongside the existing /store/ ecommerce routes, since
this app shares the same customer session auth.
"""

from django.urls import path
from . import views

app_name = 'ai_commerce'

urlpatterns = [
    path('', views.assistant_home, name='home'),
    path('natural-language/', views.natural_language_search, name='natural_language'),
    path('guided-planner/', views.guided_planner, name='guided_planner'),
    path('shop-by-goal/', views.shop_by_goal, name='shop_by_goal'),
    path('session/<int:session_id>/add-all/', views.add_all_to_cart_view, name='add_all_to_cart'),
    path('recommendation/<int:rec_id>/feedback/', views.recommendation_feedback, name='recommendation_feedback'),
    path('credit-loyalty/', views.credit_loyalty_assistant, name='credit_loyalty'),
    path('chat/', views.conversational_chat, name='chat'),
    path('chat/<int:session_id>/message/', views.conversational_message, name='chat_message'),
]