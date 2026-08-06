from django.contrib import admin
from .models import User,Notice,CalendarEvent

# Register your models here.
admin.site.register(User)
admin.site.register(Notice)
admin.site.register(CalendarEvent)
