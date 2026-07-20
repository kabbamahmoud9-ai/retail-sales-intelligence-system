from django.urls import path
from . import views

urlpatterns = [
    path('', views.advisor_list, name='advisor_list'),
    path('mark-actioned/<int:pk>/', views.mark_actioned, name='advisor_mark_actioned'),
    path('chat/<int:session_id>/message/', views.advisor_message, name='advisor_message'),
]