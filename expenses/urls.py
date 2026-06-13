from django.urls import path
from . import views

urlpatterns = [
    path('', views.expense_list, name='expense_list'),
    path('add/', views.expense_add, name='expense_add'),
    path('<int:pk>/delete/', views.expense_delete, name='expense_delete'),
    path('categories/', views.expense_category_list, name='expense_category_list'),
    path('categories/add/', views.expense_category_add, name='expense_category_add'),
]