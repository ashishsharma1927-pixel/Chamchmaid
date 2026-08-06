from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='chat_index'),
    path('search/', views.search_users, name='chat_search_users'),
    path('request/send/', views.send_request, name='chat_send_request'),
    path('request/manage/', views.manage_request, name='chat_manage_request'),
    path('start/<int:user_id>/', views.start_chat_api, name='chat_start_api'),
    path('<uuid:room_id>/', views.room, name='chat_room'),
    path('api/room/<uuid:room_id>/', views.room_data_api, name='chat_room_data_api'),
    path('api/recent/', views.recent_conversations_api, name='chat_api_recent'),
    path('api/messages_data/', views.messages_data_api, name='chat_api_messages_data'),
]
