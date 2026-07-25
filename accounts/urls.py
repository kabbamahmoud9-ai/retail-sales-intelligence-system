from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    path('profile/', views.staff_profile, name='staff_profile'),
    path('profile/change-password/', views.staff_change_password, name='staff_change_password'),
    path('profile/remove-picture/', views.staff_remove_profile_picture, name='staff_remove_profile_picture'),
]