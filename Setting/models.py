import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager

class CustomUserManager(BaseUserManager):
    def create_user(self, email=None, phone_number=None, password=None, **extra_fields):
        if not email and not phone_number and not extra_fields.get('username'):
            raise ValueError('Either Email or Phone Number must be provided')
        if email:
            email = self.normalize_email(email)
        else:
            email = None
        user = self.model(email=email, phone_number=phone_number, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        if not email:
            email = extra_fields.get('username') or 'admin@example.com'

        return self.create_user(email=email, password=password, **extra_fields)

class User(AbstractUser):
    username = models.CharField(max_length=50, unique=True, blank=True, null=True)
    email = models.EmailField(unique=True, blank=True, null=True)
    phone_number = models.CharField(max_length=15, unique=True, blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    age = models.CharField(blank=True, null=True, max_length=2)
    bio = models.CharField(blank=True, null=True, max_length=100)
    profile_image = models.ImageField(upload_to='profiles/', blank=True, null=True)
    pronouns = models.CharField(blank=True, null=True, max_length=50)
    website = models.URLField(blank=True, null=True)
    gender = models.CharField(blank=True, null=True, max_length=50)
    friends = models.ManyToManyField('self', blank=True)
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    def __str__(self):
        return self.email or self.phone_number or self.username or f"User {self.id}"

class OTP(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='otp')
    otp_code = models.CharField(max_length=6)
    token = models.UUIDField(default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        ident = self.user.email or self.user.phone_number or self.user.username or f"User {self.user.id}"
        return f"{ident} - {self.otp_code}"

class Notice(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notices')
    title = models.CharField(max_length=200)
    description = models.TextField()
    image = models.ImageField(upload_to='notices/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class CalendarEvent(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='events')
    date = models.DateField()
    details = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'date')

    def __str__(self):
        ident = self.user.email or self.user.phone_number or self.user.username or f"User {self.user.id}"
        return f"{ident} - {self.date}"

class FriendRequest(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
    )
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_requests')
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_requests')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('sender', 'receiver')

    def __str__(self):
        return f"{self.sender} -> {self.receiver} ({self.status})"

class MediaPost(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='media_posts')
    image = models.ImageField(upload_to='media_posts/')
    title = models.CharField(max_length=200)
    subtitle = models.CharField(max_length=200, blank=True, null=True)
    likes = models.ManyToManyField(User, related_name='liked_media', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title