from django.urls import path

from . import views

app_name = 'wards'
urlpatterns = [
    path('', views.board, name='board'),
    path('admissions/', views.admissions, name='admissions'),
    path('discharges/', views.discharges, name='discharges'),
    path('admissions/<int:pk>/discharge/', views.discharge, name='discharge'),
    path('admissions/<int:pk>/withdraw/', views.cancel_waiting, name='cancel_waiting'),
    path('beds/<int:pk>/clean/', views.mark_clean, name='mark_clean'),
]
