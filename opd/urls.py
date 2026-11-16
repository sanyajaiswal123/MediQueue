from django.urls import path

from . import views

app_name = 'opd'
urlpatterns = [
    path('book/', views.book, name='book'),
    path('my-token/', views.my_token, name='my_token'),
    path('my-visits/', views.history, name='history'),
    path('tokens/<int:pk>/', views.track, name='track'),
    path('reception/', views.reception, name='reception'),
    path('console/', views.console, name='console'),
    path('tokens/<int:pk>/<slug:action>/', views.token_action, name='token_action'),
]
