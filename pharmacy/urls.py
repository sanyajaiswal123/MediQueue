from django.urls import path

from . import views

app_name = 'pharmacy'
urlpatterns = [
    path('', views.dispense_list, name='dispense_list'),
    path('prescriptions/<int:pk>/dispense/', views.dispense, name='dispense'),
    path('prescriptions/<int:pk>/reject/', views.reject, name='reject'),
    path('stock/', views.stock, name='stock'),
    path('stock/write-off/', views.write_off, name='write_off'),
]
