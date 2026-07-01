from django.urls import path
from . import views

urlpatterns = [
    path('', views.notification_list, name='notification_list'),
    path('mark-read/<int:pk>/', views.mark_read, name='mark_read'),
    path('mark-all-read/', views.mark_all_read, name='mark_all_read'),
    path('api/count/', views.get_unread_count, name='notif_count'),
    path('api/recent/', views.get_recent_notifications, name='notif_recent'),
]