from django.shortcuts import render, redirect, get_object_or_404
from .models import ChatRoom, Message
from Setting.models import User, FriendRequest
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Q
import json
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

@login_required
def index(request):
    friends = request.user.friends.all()
    pending_requests = FriendRequest.objects.filter(receiver=request.user, status='pending')
    return render(request, 'chat/index.html', {
        'friends': friends,
        'pending_requests': pending_requests
    })

def get_user_display_name(u):
    if not u:
        return "User"
    full_name = f"{u.first_name} {u.last_name}".strip()
    if full_name:
        return full_name
    if u.username:
        return u.username
    if u.email:
        return u.email.split('@')[0]
    return u.phone_number or f"User {u.id}"

def get_user_avatar(u):
    if not u:
        return "https://ui-avatars.com/api/?name=User&background=random"
    if u.profile_image:
        return u.profile_image.url
    name = get_user_display_name(u)
    return f"https://ui-avatars.com/api/?name={name}&background=random"

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def search_users(request):
    query = request.GET.get('q', '')
    if len(query) < 2:
        return Response({'users': []})
    
    friends = request.user.friends.all()
    sent_requests = FriendRequest.objects.filter(sender=request.user, status='pending').values_list('receiver_id', flat=True)
    
    users = User.objects.filter(
        Q(email__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(username__icontains=query) | Q(phone_number__icontains=query)
    ).exclude(id=request.user.id).exclude(id__in=friends).distinct()[:10]
    
    user_list = []
    for u in users:
        user_list.append({
            'id': u.id,
            'email': u.email or u.phone_number or "",
            'phone_number': u.phone_number or "",
            'name': get_user_display_name(u),
            'request_sent': u.id in sent_requests
        })
    return Response({'users': user_list})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def send_request(request):
    if request.method == 'POST':
        data = request.data
        receiver_id = data.get('receiver_id')
        receiver = get_object_or_404(User, id=receiver_id)
        
        # Check if already friends or request pending
        if receiver in request.user.friends.all():
            return Response({'error': 'Already friends'}, status=400)
            
        freq, created = FriendRequest.objects.get_or_create(
            sender=request.user, 
            receiver=receiver,
            defaults={'status': 'pending'}
        )
        
        if not created and freq.status in ['rejected', 'accepted']:
            freq.status = 'pending'
            freq.save()
            
        return Response({'success': True})
    return Response({'error': 'Invalid method'}, status=400)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def manage_request(request):
    if request.method == 'POST':
        data = request.data
        request_id = data.get('request_id')
        action = data.get('action') # 'accept' or 'reject'
        
        freq = get_object_or_404(FriendRequest, id=request_id, receiver=request.user)
        
        if action == 'accept':
            freq.status = 'accepted'
            freq.save()
            request.user.friends.add(freq.sender)
            freq.sender.friends.add(request.user)
            return Response({'success': True})
        elif action == 'reject':
            freq.status = 'rejected'
            freq.save()
            return Response({'success': True})
            
    return Response({'error': 'Invalid method'}, status=400)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def start_chat_api(request, user_id):
    friend = get_object_or_404(User, id=user_id)
    if friend not in request.user.friends.all():
        return Response({'error': 'Not friends'}, status=403)
        
    # Create deterministic room name
    ids = sorted([request.user.id, friend.id])
    room_name = f"private_{ids[0]}_{ids[1]}"
    
    room, created = ChatRoom.objects.get_or_create(name=room_name)
    if created:
        room.users.add(request.user, friend)
        
    return Response({'room_id': room.id})

def room(request, room_id):
    # Unprotected SPA view that fetches data via API using JWT
    return render(request, 'chat/room.html', {'room_id': room_id})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def room_data_api(request, room_id):
    room = get_object_or_404(ChatRoom, id=room_id)
    if request.user not in room.users.all():
        return Response({'error': 'Not in room'}, status=403)
        
    messages = room.messages.exclude(deleted_by=request.user).order_by('timestamp')
    other_user = room.users.exclude(id=request.user.id).first()
    
    messages_data = [{
        'id': str(msg.id),
        'sender': msg.sender.email or msg.sender.phone_number or f"User {msg.sender.id}",
        'sender_name': get_user_display_name(msg.sender),
        'sender_id': msg.sender.id,
        'content': msg.content,
        'timestamp': msg.timestamp.isoformat(),
        'is_edited': msg.is_edited,
        'is_read': msg.is_read
    } for msg in messages]
    
    other_user_data = None
    if other_user:
        other_user_data = {
            'name': get_user_display_name(other_user),
        }
        
    return Response({
        'room_name': room.name,
        'other_user': other_user_data,
        'messages': messages_data,
        'current_user_id': request.user.id,
        'current_user_email': request.user.email or request.user.phone_number or ""
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def recent_conversations_api(request):
    rooms = request.user.chat_rooms.all()
    conversations = []
    
    for room in rooms:
        other_user = room.users.exclude(id=request.user.id).first()
        last_message = room.messages.order_by('-timestamp').first()
        
        if other_user and last_message:
            conversations.append({
                'room_id': room.id,
                'name': get_user_display_name(other_user),
                'avatar': get_user_avatar(other_user),
                'last_message': last_message.content,
                'timestamp': last_message.timestamp.isoformat(),
            })
            
    # Sort by most recent message
    conversations.sort(key=lambda x: x['timestamp'], reverse=True)
    return Response({'conversations': conversations[:10]})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def messages_data_api(request):
    # Pending requests
    pending = FriendRequest.objects.filter(receiver=request.user, status='pending')
    pending_list = []
    for p in pending:
        sender = p.sender
        pending_list.append({
            'request_id': p.id,
            'sender_id': sender.id,
            'name': get_user_display_name(sender),
            'email': sender.email or sender.phone_number or "",
            'avatar': get_user_avatar(sender),
        })
        
    # Active Friends
    friends = request.user.friends.all()
    friends_list = []
    for f in friends:
        friends_list.append({
            'id': f.id,
            'name': get_user_display_name(f),
            'email': f.email or f.phone_number or "",
            'avatar': get_user_avatar(f),
        })
        
    return Response({
        'pending_requests': pending_list,
        'friends': friends_list
    })
