from django.urls import path
from .views import (
    SignupView, 
    VerifyOTPView, 
    ResendOTPView,
    LoginView, 
    LogoutView, 
    ForgotPasswordView, 
    ResetPasswordView, 
    ProfileView, 
    NoticeListView, 
    CalendarEventView, 
    MediaPostListView, 
    MediaPostLikeView, 
    MediaPostDeleteView
)

urlpatterns = [
    path('signup/', SignupView.as_view(), name='signup'),
    path('verify/', VerifyOTPView.as_view(), name='verify-otp'),
    path('resend-otp/', ResendOTPView.as_view(), name='resend-otp'),
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('forgot-password/', ForgotPasswordView.as_view(), name='forgot-password'),
    path('reset-password/', ResetPasswordView.as_view(), name='reset-password'),
    path('profile/', ProfileView.as_view(), name='profile'),
    path('notices/', NoticeListView.as_view(), name='notices'),
    path('events/', CalendarEventView.as_view(), name='events'),
    path('media/', MediaPostListView.as_view(), name='media'),
    path('media/<int:pk>/like/', MediaPostLikeView.as_view(), name='media_like'),
    path('media/<int:pk>/delete/', MediaPostDeleteView.as_view(), name='media_delete'),
]
