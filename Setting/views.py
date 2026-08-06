from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
from rest_framework_simplejwt.tokens import RefreshToken

from .models import OTP
from .serializers import (
    SignupSerializer, 
    VerifyOTPSerializer, 
    ResendOTPSerializer,
    LoginSerializer, 
    ForgotPasswordSerializer, 
    ResetPasswordSerializer
)
from .utils import (
    generate_otp, 
    send_sms_otp, 
    send_email_otp, 
    normalize_phone_number,
    check_twilio_verify_otp
)

User = get_user_model()

class SignupView(APIView):
    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            
            otp_code = generate_otp()
            OTP.objects.filter(user=user).delete()
            OTP.objects.create(user=user, otp_code=otp_code)
            
            sent_to = ""
            delivery_type = ""
            if user.phone_number:
                success, msg = send_sms_otp(user.phone_number, otp_code)
                delivery_type = "phone"
                sent_to = user.phone_number
            elif user.email:
                success, msg = send_email_otp(user.email, otp_code)
                delivery_type = "email"
                sent_to = user.email
            else:
                success = False
                msg = "No contact details provided."

            refresh = RefreshToken.for_user(user)
            
            if success:
                return Response({
                    'message': f'OTP code sent to {sent_to} successfully.',
                    'delivery_success': True,
                    'delivery_type': delivery_type,
                    'sent_to': sent_to,
                    'access': str(refresh.access_token)
                }, status=status.HTTP_201_CREATED)
            else:
                return Response({
                    'message': f'Account created, but SMS sending failed: {msg}',
                    'delivery_success': False,
                    'delivery_type': delivery_type,
                    'sent_to': sent_to,
                    'access': str(refresh.access_token),
                    'error': msg
                }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class VerifyOTPView(APIView):
    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        if serializer.is_valid():
            otp_code = serializer.validated_data['otp'].strip()
            identifier = serializer.validated_data.get('identifier', '').strip()
            
            user = None
            if request.user and request.user.is_authenticated:
                user = request.user
            elif identifier:
                norm_phone = normalize_phone_number(identifier)
                query = Q(email__iexact=identifier) | Q(username__iexact=identifier) | Q(phone_number=identifier)
                if norm_phone:
                    query |= Q(phone_number=norm_phone)
                user = User.objects.filter(query).first()
                
            if not user:
                return Response({'error': 'User not found. Please provide valid authorization or identifier.'}, status=status.HTTP_400_BAD_REQUEST)
                
            is_valid = False
            
            # 1. Verify via Twilio Verify API if user has phone number
            if user.phone_number and check_twilio_verify_otp(user.phone_number, otp_code):
                is_valid = True
            
            # 2. Verify via Database OTP record
            if not is_valid:
                try:
                    otp_record = OTP.objects.get(user=user)
                    if timezone.now() <= otp_record.created_at + timedelta(minutes=10) and otp_record.otp_code == otp_code:
                        is_valid = True
                except OTP.DoesNotExist:
                    pass

            if is_valid:
                user.is_verified = True
                user.save()
                OTP.objects.filter(user=user).delete()
                
                # Generate fresh JWT Tokens
                refresh = RefreshToken.for_user(user)
                
                return Response({
                    'message': 'Account verified successfully.',
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                    'user_id': user.id,
                    'email': user.email,
                    'phone_number': user.phone_number,
                    'username': user.username
                }, status=status.HTTP_200_OK)
            else:
                return Response({'error': 'Invalid or expired OTP code.'}, status=status.HTTP_400_BAD_REQUEST)
                
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ResendOTPView(APIView):
    def post(self, request):
        serializer = ResendOTPSerializer(data=request.data)
        if serializer.is_valid():
            identifier = serializer.validated_data.get('identifier', '').strip()
            user = None
            if request.user and request.user.is_authenticated:
                user = request.user
            elif identifier:
                norm_phone = normalize_phone_number(identifier)
                query = Q(email__iexact=identifier) | Q(username__iexact=identifier) | Q(phone_number=identifier)
                if norm_phone:
                    query |= Q(phone_number=norm_phone)
                user = User.objects.filter(query).first()

            if not user:
                return Response({'error': 'User not found.'}, status=status.HTTP_400_BAD_REQUEST)

            otp_code = generate_otp()
            OTP.objects.filter(user=user).delete()
            OTP.objects.create(user=user, otp_code=otp_code)

            sent_to = ""
            delivery_type = ""
            if user.phone_number:
                success, msg = send_sms_otp(user.phone_number, otp_code)
                delivery_type = "phone"
                sent_to = user.phone_number
            elif user.email:
                success, msg = send_email_otp(user.email, otp_code)
                delivery_type = "email"
                sent_to = user.email
            else:
                success = False
                msg = "No contact method found."

            refresh = RefreshToken.for_user(user)
            if success:
                return Response({
                    'message': f'New OTP sent to {sent_to}.',
                    'sent_to': sent_to,
                    'delivery_type': delivery_type,
                    'access': str(refresh.access_token)
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'error': f'Failed to send OTP: {msg}',
                    'access': str(refresh.access_token)
                }, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class LoginView(APIView):
    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            user = serializer.validated_data['user']
            refresh = RefreshToken.for_user(user)
            
            return Response({
                'message': 'Login successful.',
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'user_id': user.id, 
                'email': user.email,
                'phone_number': user.phone_number,
                'username': user.username
            }, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
            return Response({'message': 'Logged out successfully.'}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': 'Invalid token.'}, status=status.HTTP_400_BAD_REQUEST)

class ForgotPasswordView(APIView):
    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        if serializer.is_valid():
            identifier = serializer.validated_data['identifier']
            norm_phone = normalize_phone_number(identifier)
            query = Q(email__iexact=identifier) | Q(username__iexact=identifier) | Q(phone_number=identifier)
            if norm_phone:
                query |= Q(phone_number=norm_phone)
            user = User.objects.filter(query).first()
            if not user:
                return Response({'error': 'No account found with this email or phone number.'}, status=status.HTTP_400_BAD_REQUEST)
            
            otp_code = generate_otp()
            OTP.objects.filter(user=user).delete()
            OTP.objects.create(user=user, otp_code=otp_code)
            
            sent_to = ""
            delivery_type = ""
            if user.phone_number and (identifier.startswith('+') or identifier.replace('+', '').isdigit()):
                success, msg = send_sms_otp(user.phone_number, otp_code)
                delivery_type = "phone"
                sent_to = user.phone_number
            elif user.email:
                success, msg = send_email_otp(user.email, otp_code, is_password_reset=True)
                delivery_type = "email"
                sent_to = user.email
            elif user.phone_number:
                success, msg = send_sms_otp(user.phone_number, otp_code)
                delivery_type = "phone"
                sent_to = user.phone_number
            else:
                success = False
                msg = "No contact method found on account."
                
            refresh = RefreshToken.for_user(user)
            if success:
                return Response({
                    'message': f'Password reset OTP sent to {sent_to}.',
                    'delivery_type': delivery_type,
                    'sent_to': sent_to,
                    'access': str(refresh.access_token)
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'error': f'Failed to send OTP: {msg}',
                    'access': str(refresh.access_token)
                }, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ResetPasswordView(APIView):
    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        if serializer.is_valid():
            otp_code = serializer.validated_data['otp'].strip()
            new_password = serializer.validated_data['new_password']
            identifier = serializer.validated_data.get('identifier', '').strip()
            
            user = None
            if request.user and request.user.is_authenticated:
                user = request.user
            elif identifier:
                norm_phone = normalize_phone_number(identifier)
                query = Q(email__iexact=identifier) | Q(username__iexact=identifier) | Q(phone_number=identifier)
                if norm_phone:
                    query |= Q(phone_number=norm_phone)
                user = User.objects.filter(query).first()
                
            if not user:
                return Response({'error': 'User not identified. Please provide token or identifier.'}, status=status.HTTP_400_BAD_REQUEST)
            
            is_valid = False
            
            # 1. Verify via Twilio Verify API if user has phone number
            if user.phone_number and check_twilio_verify_otp(user.phone_number, otp_code):
                is_valid = True
                
            # 2. Verify via Database OTP record
            if not is_valid:
                try:
                    otp_record = OTP.objects.get(user=user)
                    if timezone.now() <= otp_record.created_at + timedelta(minutes=10) and otp_record.otp_code == otp_code:
                        is_valid = True
                except OTP.DoesNotExist:
                    pass
                    
            if is_valid:
                user.set_password(new_password)
                user.is_verified = True
                user.save()
                OTP.objects.filter(user=user).delete()
                
                return Response({
                    'message': 'Password reset successfully. You can now login.'
                }, status=status.HTTP_200_OK)
            else:
                return Response({'error': 'Invalid or expired OTP code.'}, status=status.HTTP_400_BAD_REQUEST)
                
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

from .serializers import ProfileSerializer, NoticeSerializer, CalendarEventSerializer
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from .models import Notice, CalendarEvent

class ProfileView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def get(self, request):
        serializer = ProfileSerializer(request.user)
        return Response(serializer.data)

    def put(self, request):
        serializer = ProfileSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    def delete(self, request):
        user = request.user
        user.delete()
        return Response({'message': 'Profile deleted successfully'}, status=status.HTTP_204_NO_CONTENT)

class NoticeListView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def get(self, request):
        notices = Notice.objects.all().order_by('-created_at')
        serializer = NoticeSerializer(notices, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = NoticeSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class CalendarEventView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Allow filtering by month/year (optional)
        events = CalendarEvent.objects.filter(user=request.user)
        serializer = CalendarEventSerializer(events, many=True)
        return Response(serializer.data)

    def post(self, request):
        date = request.data.get('date')
        if not date:
            return Response({'error': 'Date is required.'}, status=status.HTTP_400_BAD_REQUEST)

        event, created = CalendarEvent.objects.update_or_create(
            user=request.user,
            date=date,
            defaults={'details': request.data.get('details', '')}
        )
        serializer = CalendarEventSerializer(event)
        return Response(serializer.data)

from .models import MediaPost
from .serializers import MediaPostSerializer

class MediaPostListView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def get(self, request):
        user_id = request.query_params.get('user_id')
        if user_id == 'me':
            posts = MediaPost.objects.filter(user=request.user).order_by('-created_at')
        else:
            # Only show posts from friends (connections) and the user themselves
            friends = request.user.friends.all()
            posts = (MediaPost.objects.filter(user__in=friends) | MediaPost.objects.filter(user=request.user)).distinct().order_by('-created_at')
            
        serializer = MediaPostSerializer(posts, many=True, context={'request': request})
        return Response(serializer.data)

    def post(self, request):
        serializer = MediaPostSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save(user=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class MediaPostLikeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            post = MediaPost.objects.get(pk=pk)
            
            # Check if user is allowed to interact with the post (must be friend or owner)
            if post.user != request.user and request.user not in post.user.friends.all():
                return Response({'error': 'You do not have permission to view or interact with this post.'}, status=status.HTTP_403_FORBIDDEN)
                
            if post.likes.filter(id=request.user.id).exists():
                post.likes.remove(request.user)
                liked = False
            else:
                post.likes.add(request.user)
                liked = True
            return Response({'liked': liked, 'likes_count': post.likes.count()})
        except MediaPost.DoesNotExist:
            return Response({'error': 'Post not found'}, status=status.HTTP_404_NOT_FOUND)

class MediaPostDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        try:
            post = MediaPost.objects.get(pk=pk)
            if post.user != request.user:
                return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
            post.delete()
            return Response({'success': True}, status=status.HTTP_204_NO_CONTENT)
        except MediaPost.DoesNotExist:
            return Response({'error': 'Post not found'}, status=status.HTTP_404_NOT_FOUND)
