from django.contrib import admin
from django.templatetags.static import static
from django.urls import include, path
from django.views.generic import RedirectView

from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('staff/', views.staff_home, name='staff_home'),
    path('city/', views.city, name='city'),
    path('favicon.ico', RedirectView.as_view(url=static('favicon.svg'), permanent=True)),
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('opd/', include('opd.urls')),
    path('wards/', include('wards.urls')),
    path('pharmacy/', include('pharmacy.urls')),
    path('api/', include('api.urls')),
]
