from rest_framework import serializers
from django.contrib.auth import get_user_model, authenticate
from django.db.models import Q
from .models import OTP, Notice, CalendarEvent, MediaPost
from .utils import normalize_phone_number

User = get_user_model()

class SignupSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    phone_number = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    password = serializers.CharField(write_only=True, min_length=6)

    def validate(self, data):
        email = data.get('email')
        phone = data.get('phone_number')

        if email:
            email = email.strip().lower()
            data['email'] = email
        else:
            data['email'] = None

        if phone:
            phone = normalize_phone_number(phone)
            data['phone_number'] = phone
        else:
            data['phone_number'] = None

        if not data['email'] and not data['phone_number']:
            raise serializers.ValidationError("Either Email or Phone Number must be provided.")

        if data['email'] and User.objects.filter(email__iexact=data['email'], is_verified=True).exists():
            raise serializers.ValidationError({"email": "User with this email already exists."})

        if data['phone_number'] and User.objects.filter(phone_number=data['phone_number'], is_verified=True).exists():
            raise serializers.ValidationError({"phone_number": "User with this phone number already exists."})

        return data

    def create(self, validated_data):
        email = validated_data.get('email')
        phone_number = validated_data.get('phone_number')
        password = validated_data['password']

        user = None
        if email:
            user = User.objects.filter(email__iexact=email).first()
        elif phone_number:
            user = User.objects.filter(phone_number=phone_number).first()

        if user:
            user.set_password(password)
            if email:
                user.email = email
            if phone_number:
                user.phone_number = phone_number
            user.save()
        else:
            user = User.objects.create_user(email=email, phone_number=phone_number, password=password)
        return user

class VerifyOTPSerializer(serializers.Serializer):
    otp = serializers.CharField(max_length=6)
    identifier = serializers.CharField(required=False, allow_blank=True)

class ResendOTPSerializer(serializers.Serializer):
    identifier = serializers.CharField(required=False, allow_blank=True)

class LoginSerializer(serializers.Serializer):
    identifier = serializers.CharField(required=False, allow_blank=True)
    email = serializers.CharField(required=False, allow_blank=True)
    phone_number = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        login_ident = data.get('identifier') or data.get('email') or data.get('phone_number')
        password = data.get('password')

        if not login_ident or not password:
            raise serializers.ValidationError('Must include email/phone number and password.')

        user = authenticate(request=self.context.get('request'), identifier=login_ident, password=password)
        if not user:
            raise serializers.ValidationError({'non_field_errors': ['Invalid email/phone number or password.']})
        if not user.is_verified:
            raise serializers.ValidationError({
                'non_field_errors': ['Account is not verified. Please verify your OTP.'],
                'is_unverified': True,
                'email': user.email,
                'phone_number': user.phone_number,
                'user_id': user.id
            })
        
        data['user'] = user
        return data

class ForgotPasswordSerializer(serializers.Serializer):
    identifier = serializers.CharField(required=False, allow_blank=True)
    email = serializers.CharField(required=False, allow_blank=True)
    phone_number = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        ident = data.get('identifier') or data.get('email') or data.get('phone_number')
        if not ident:
            raise serializers.ValidationError('Please provide your registered Email or Phone Number.')
        data['identifier'] = ident.strip()
        return data

class ResetPasswordSerializer(serializers.Serializer):
    otp = serializers.CharField(max_length=6)
    new_password = serializers.CharField(write_only=True, min_length=6)
    identifier = serializers.CharField(required=False, allow_blank=True)

class ProfileSerializer(serializers.ModelSerializer):
    friends_count = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'phone_number', 'age', 'bio', 'profile_image', 'pronouns', 'website', 'gender', 'friends_count']
        
    def validate_username(self, value):
        if not value:
            return None
        return value
        
    def get_friends_count(self, obj):
        return obj.friends.count()

class NoticeSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = Notice
        fields = ['id', 'title', 'description', 'image', 'created_at', 'user_name']
        read_only_fields = ['id', 'created_at', 'user_name']

    def get_user_name(self, obj):
        if obj.user.username:
            return obj.user.username
        name = f"{obj.user.first_name} {obj.user.last_name}".strip()
        if name:
            return name
        if obj.user.email:
            return obj.user.email.split('@')[0]
        return obj.user.phone_number or f"User {obj.user.id}"

class CalendarEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = CalendarEvent
        fields = ['id', 'date', 'details']
        read_only_fields = ['id']

class MediaPostSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()
    author_avatar = serializers.SerializerMethodField()
    likes_count = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()
    is_owner = serializers.SerializerMethodField()

    class Meta:
        model = MediaPost
        fields = ['id', 'image', 'title', 'subtitle', 'author_name', 'author_avatar', 'likes_count', 'is_liked', 'is_owner', 'created_at']
        read_only_fields = ['id', 'author_name', 'author_avatar', 'likes_count', 'is_liked', 'is_owner', 'created_at']

    def get_author_name(self, obj):
        if obj.user.username:
            return obj.user.username
        name = f"{obj.user.first_name} {obj.user.last_name}".strip()
        if name:
            return name
        if obj.user.email:
            return obj.user.email.split('@')[0]
        return obj.user.phone_number or f"User {obj.user.id}"

    def get_author_avatar(self, obj):
        request = self.context.get('request')
        if obj.user.profile_image:
            if request:
                return request.build_absolute_uri(obj.user.profile_image.url)
            return obj.user.profile_image.url
        name = self.get_author_name(obj)
        return f"https://ui-avatars.com/api/?name={name}&background=random"

    def get_likes_count(self, obj):
        return obj.likes.count()

    def get_is_liked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.likes.filter(id=request.user.id).exists()
        return False

    def get_is_owner(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.user == request.user
        return False