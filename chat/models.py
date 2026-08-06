from django.db import models
from django.conf import settings
import uuid

class ChatRoom(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True, blank=True, null=True)
    users = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='chat_rooms')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"ChatRoom {self.id} - {self.name}"

class Message(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='messages')
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_edited = models.BooleanField(default=False)
    is_read = models.BooleanField(default=False)
    deleted_by = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='deleted_messages', blank=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.sender.email} at {self.timestamp}: {self.content[:20]}"
