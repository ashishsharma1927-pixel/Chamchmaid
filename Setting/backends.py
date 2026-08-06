from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q
from .utils import normalize_phone_number

User = get_user_model()

class EmailOrPhoneModelBackend(ModelBackend):
    """
    Custom Authentication Backend that allows users to authenticate
    using their Email, Phone Number, or Username.
    """
    def authenticate(self, request, username=None, password=None, identifier=None, **kwargs):
        login_ident = identifier or username or kwargs.get('email') or kwargs.get('phone_number')
        if not login_ident or not password:
            return None

        login_ident = str(login_ident).strip()
        normalized_phone = normalize_phone_number(login_ident)

        query = Q(email__iexact=login_ident) | Q(username__iexact=login_ident) | Q(phone_number=login_ident)
        if normalized_phone:
            query |= Q(phone_number=normalized_phone)

        user = User.objects.filter(query).first()

        if user and user.check_password(password):
            return user
        return None
