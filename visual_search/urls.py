from django.urls import path
from . import views

app_name = 'visual_search'

urlpatterns = [
    path('', views.visual_search_results, name='results'),
]