import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import ChatRoom, Message
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

User = get_user_model()

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_id = self.scope['url_route']['kwargs']['room_id']
        self.room_group_name = f'chat_{self.room_id}'

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # Receive message from WebSocket
    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        action = text_data_json.get('action', 'send')
        sender_id = text_data_json.get('sender_id')

        if action == 'send':
            message = text_data_json['message']
            saved_msg = await self.save_message(self.room_id, sender_id, message)
            if saved_msg:
                sender_name = f"{saved_msg.sender.first_name} {saved_msg.sender.last_name}".strip() or saved_msg.sender.username or saved_msg.sender.email.split('@')[0]
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'chat_message',
                        'message': message,
                        'sender': saved_msg.sender.email,
                        'sender_name': sender_name,
                        'id': str(saved_msg.id),
                        'timestamp': saved_msg.timestamp.isoformat(),
                        'is_edited': saved_msg.is_edited
                    }
                )
        elif action == 'edit':
            message_id = text_data_json.get('message_id')
            new_content = text_data_json.get('content')
            success = await self.edit_message(message_id, sender_id, new_content)
            if success:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'edit_message',
                        'message_id': message_id,
                        'content': new_content
                    }
                )
        elif action == 'delete':
            message_id = text_data_json.get('message_id')
            deleted_for_everyone = await self.delete_message(message_id, sender_id)
            if deleted_for_everyone:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'delete_message',
                        'message_id': message_id
                    }
                )
        elif action == 'read_all':
            await self.mark_all_read(self.room_id, sender_id)
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'read_all_receipt',
                    'reader_id': sender_id
                }
            )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'action': 'send',
            'message': event['message'],
            'sender': event['sender'],
            'sender_name': event['sender_name'],
            'id': event['id'],
            'timestamp': event['timestamp'],
            'is_edited': event.get('is_edited', False)
        }))

    async def edit_message(self, event):
        await self.send(text_data=json.dumps({
            'action': 'edit',
            'message_id': event['message_id'],
            'content': event['content']
        }))

    async def delete_message(self, event):
        await self.send(text_data=json.dumps({
            'action': 'delete',
            'message_id': event['message_id']
        }))

    async def read_all_receipt(self, event):
        await self.send(text_data=json.dumps({
            'action': 'read_all',
            'reader_id': event['reader_id']
        }))

    @database_sync_to_async
    def save_message(self, room_id, sender_id, content):
        try:
            room = ChatRoom.objects.get(id=room_id)
            sender = User.objects.get(id=sender_id)
            return Message.objects.create(room=room, sender=sender, content=content)
        except (ChatRoom.DoesNotExist, User.DoesNotExist):
            return None

    @database_sync_to_async
    def edit_message(self, message_id, sender_id, new_content):
        try:
            msg = Message.objects.get(id=message_id, sender_id=sender_id)
            if timezone.now() - msg.timestamp <= timedelta(minutes=30):
                msg.content = new_content
                msg.is_edited = True
                msg.save()
                return True
            return False
        except Message.DoesNotExist:
            return False

    @database_sync_to_async
    def delete_message(self, message_id, sender_id):
        try:
            msg = Message.objects.get(id=message_id, sender_id=sender_id)
            if timezone.now() - msg.timestamp <= timedelta(hours=1):
                msg.delete()
                return True
            else:
                msg.deleted_by.add(sender_id)
                return False # Not deleted for everyone
        except Message.DoesNotExist:
            return False

    @database_sync_to_async
    def mark_all_read(self, room_id, user_id):
        Message.objects.filter(room_id=room_id).exclude(sender_id=user_id).filter(is_read=False).update(is_read=True)
