from django.urls import path

from . import views

app_name = 'api'
urlpatterns = [
    path('city/hospitals/', views.CityHospitalsView.as_view(), name='city-hospitals'),
    path('hospitals/<int:pk>/departments/', views.HospitalDepartmentsView.as_view(), name='hospital-departments'),
    path('hospitals/<int:pk>/beds/', views.HospitalBedsView.as_view(), name='hospital-beds'),
    path('tokens/', views.TokenCreateView.as_view(), name='token-create'),
    path('tokens/<int:pk>/', views.TokenDetailView.as_view(), name='token-detail'),
    path('tokens/<int:pk>/cancel/', views.TokenCancelView.as_view(), name='token-cancel'),
]
