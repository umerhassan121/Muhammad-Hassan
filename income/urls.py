from django.urls import path

from . import views

app_name = 'income'

urlpatterns = [
    path('', views.source_list, name='source_list'),
    path('add/', views.source_add, name='source_add'),
]
