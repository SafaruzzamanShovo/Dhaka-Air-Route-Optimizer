from django.urls import path
from . import views

app_name = 'route_optimizer'

urlpatterns = [
    path('', views.index, name='index'),
    path('api/find-route/', views.find_route, name='find_route'),
    path('api/compare-routes/', views.compare_routes, name='compare_routes'),
    path('api/history/', views.get_history, name='get_history'),
    path('api/get-aqi/', views.get_aqi, name='get_aqi'),
]

