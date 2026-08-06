import os
import re
import random
import logging
import requests
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)

def generate_otp() -> str:
    """Generate a random 6-digit OTP code."""
    return str(random.randint(100000, 999999))

def normalize_phone_number(phone: str, default_country_code: str = None) -> str:
    """
    Normalizes a phone number to standard E.164 format with leading '+'
    (e.g., '+918219380285', '+17372508034').
    Handles:
      - 10-digit Indian numbers starting with 6, 7, 8, 9 -> '+91' + digits
      - 10-digit US/North American numbers starting with 2-5 -> '+1' + digits (or configured default)
      - Numbers with leading 0 or 00 (e.g. '08219380285' -> '+918219380285')
      - 12-digit Indian numbers starting with 91 -> '+91...'
      - 11-digit US numbers starting with 1 -> '+1...'
      - Formatted strings with spaces, parentheses, dashes, dots.
    """
    if not phone:
        return ""
    
    phone = str(phone).strip()
    had_plus = phone.startswith('+')
    
    # Extract only digits
    digits = re.sub(r'\D', '', phone)
    if not digits:
        return ""
    
    # If phone started with international prefix '00'
    if digits.startswith('00'):
        digits = digits[2:]
        return '+' + digits

    if had_plus:
        return '+' + digits
    
    # If starting with a single '0' (trunk prefix like in India 098..., UK 07...)
    if digits.startswith('0') and len(digits) >= 11:
        digits = digits[1:]
    
    default_prefix = default_country_code or os.getenv('DEFAULT_COUNTRY_CODE', '+91').strip()
    if not default_prefix.startswith('+'):
        default_prefix = '+' + default_prefix
        
    # Standard 10-digit mobile number
    if len(digits) == 10:
        if digits[0] in ['6', '7', '8', '9']:
            return f"+91{digits}"
        elif default_prefix:
            return f"{default_prefix}{digits}"
        else:
            return f"+1{digits}"
            
    # 12 digits starting with 91 (India)
    if len(digits) == 12 and digits.startswith('91'):
        return f"+{digits}"
        
    # 11 digits starting with 1 (USA/Canada)
    if len(digits) == 11 and digits.startswith('1'):
        return f"+{digits}"
        
    # If other length without '+', prepend '+'
    return f"+{digits}"

def check_twilio_verify_otp(phone_number: str, otp_code: str) -> bool:
    """
    Validates an OTP code using Twilio Verify API.
    Returns True if approved, False otherwise.
    """
    account_sid = (os.getenv('TWILIO_ACCOUNT_SID') or os.getenv('TWILIO_SID') or '').strip()
    auth_token = (os.getenv('TWILIO_AUTH_TOKEN') or os.getenv('TWILIO_TOKEN') or '').strip()
    service_sid = (os.getenv('TWILIO_VERIFY_SERVICE_SID') or '').strip()
    
    if not (account_sid and auth_token and service_sid and phone_number and otp_code):
        return False
        
    normalized_to = normalize_phone_number(phone_number)
    url = f"https://verify.twilio.com/v2/Services/{service_sid}/VerificationCheck"
    
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                url,
                auth=(account_sid, auth_token),
                data={
                    "To": normalized_to,
                    "Code": str(otp_code).strip()
                }
            )
            data = response.json()
            if response.status_code == 200 and (data.get('status') == 'approved' or data.get('valid') is True):
                logger.info(f"Twilio Verify OTP successfully approved for {normalized_to}")
                return True
    except Exception as e:
        logger.exception(f"Twilio Verify check failed for {normalized_to}: {str(e)}")
        
    return False

def send_sms_otp(phone_number: str, otp_code: str = None) -> tuple[bool, str]:
    """
    Sends an OTP via Twilio Verify API or standard Twilio Messages API.
    Returns (success: bool, message: str)
    """
    account_sid = (os.getenv('TWILIO_ACCOUNT_SID') or os.getenv('TWILIO_SID') or '').strip()
    api_key = (os.getenv('TWILIO_API_KEY') or '').strip()
    api_secret = (os.getenv('TWILIO_API_SECRET') or '').strip()
    auth_token = (os.getenv('TWILIO_AUTH_TOKEN') or os.getenv('TWILIO_TOKEN') or '').strip()
    from_number = (os.getenv('TWILIO_PHONE_NUMBER') or os.getenv('TWILIO_NUMBER') or '').strip()
    service_sid = (os.getenv('TWILIO_VERIFY_SERVICE_SID') or '').strip()
    
    normalized_to = normalize_phone_number(phone_number)
    
    # Always log OTP in terminal with clear banner for easy local testing
    print(f"\n{'='*60}\n[OTP DISPATCH] Destination: {normalized_to} | OTP Code: {otp_code or '(Twilio Verify Code)'}\n{'='*60}\n")
    
    if not account_sid:
        err_msg = (
            "Twilio Account SID is missing in .env (TWILIO_ACCOUNT_SID). "
            "Please add your Twilio Account SID (starts with 'AC...') to your .env file."
        )
        logger.error(err_msg)
        return False, err_msg

    # Determine authentication method
    if auth_token:
        auth = (account_sid, auth_token)
    elif api_key and api_secret:
        auth = (api_key, api_secret)
    else:
        err_msg = (
            "Twilio authentication credentials missing. "
            "Please provide TWILIO_AUTH_TOKEN or (TWILIO_API_KEY and TWILIO_API_SECRET) in .env."
        )
        logger.error(err_msg)
        return False, err_msg

    # 1. Primary: Use Twilio Verify API if configured (Supported on all accounts including Trial)
    if service_sid:
        verify_url = f"https://verify.twilio.com/v2/Services/{service_sid}/Verifications"
        try:
            with httpx.Client(timeout=12.0) as client:
                res = client.post(
                    verify_url,
                    auth=auth,
                    data={
                        "To": normalized_to,
                        "Channel": "sms"
                    }
                )
                data = res.json()
                if res.status_code in [200, 201]:
                    logger.info(f"Twilio Verify SMS successfully dispatched to {normalized_to} (SID: {data.get('sid')})")
                    return True, f"OTP SMS sent to {normalized_to} successfully."
                else:
                    err_code = data.get('code')
                    raw_msg = data.get('message') or f"Twilio Verify error {res.status_code}"
                    if err_code in [572002, 21608] or "verified recipient" in raw_msg.lower():
                        return False, f"Twilio Trial Restriction: The phone number {normalized_to} is not verified in Twilio Console. Add it at https://console.twilio.com/us1/develop/phone-numbers/manage/verified-caller-ids"
                    return False, f"Twilio Verify failed: {raw_msg}"
        except Exception as e:
            logger.exception(f"Twilio Verify service error: {str(e)}")

    # 2. Fallback: Use standard Twilio Messages API
    if not from_number:
        err_msg = "Twilio Phone Number is missing in .env (TWILIO_PHONE_NUMBER)."
        logger.error(err_msg)
        return False, err_msg

    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    body_text = f"Your verification OTP is: {otp_code}. Valid for 10 minutes."
    
    try:
        with httpx.Client(timeout=12.0) as client:
            response = client.post(
                url,
                auth=auth,
                data={
                    "From": from_number,
                    "To": normalized_to,
                    "Body": body_text,
                }
            )
            
            try:
                data = response.json()
            except Exception:
                data = {}

            if response.status_code in [200, 201]:
                logger.info(f"SMS OTP successfully sent to {normalized_to} (SID: {data.get('sid')})")
                return True, "OTP sent via SMS successfully."
            else:
                error_code = data.get('code')
                raw_msg = data.get('message') or data.get('error_message') or f"Twilio HTTP {response.status_code}"
                
                if error_code in [572002, 21608] or "verified recipient" in raw_msg.lower() or "policy evaluation" in raw_msg.lower() or "unverified" in raw_msg.lower():
                    error_msg = (
                        f"Twilio Trial Restriction: The phone number {normalized_to} is not a Verified Caller ID in your Twilio account. "
                        f"Please add {normalized_to} to 'Verified Caller IDs' at https://console.twilio.com/us1/develop/phone-numbers/manage/verified-caller-ids or upgrade your Twilio account."
                    )
                elif error_code == 21408 or "geo" in raw_msg.lower() or "region" in raw_msg.lower():
                    error_msg = (
                        f"Twilio Geo-Permission Error: SMS sending to the region for {normalized_to} is disabled in your Twilio account. "
                        f"Enable Geo Permissions for India/your country at https://console.twilio.com/us1/develop/sms/settings/geo-permissions."
                    )
                elif error_code == 20003 or response.status_code == 401:
                    error_msg = (
                        "Twilio Authentication Failed: Invalid Account SID or Auth Token / API Key. "
                        "Please verify your TWILIO_ACCOUNT_SID and credentials in .env."
                    )
                elif error_code == 21211:
                    error_msg = f"Invalid Phone Number: The number {normalized_to} is not a valid international mobile number."
                elif error_code == 21606:
                    error_msg = f"Invalid 'From' Number: The Twilio number {from_number} is not a valid SMS-capable Twilio number on your account."
                else:
                    error_msg = raw_msg
                    
                logger.error(f"Failed to send SMS to {normalized_to} (Code {error_code}): {raw_msg}")
                return False, error_msg
    except Exception as e:
        logger.exception(f"Exception while sending SMS to {normalized_to}: {str(e)}")
        return False, f"SMS service error: {str(e)}"

def send_email_otp(email: str, otp_code: str, is_password_reset: bool = False) -> tuple[bool, str]:
    """
    Sends an OTP via Django configured email backend.
    Returns (success: bool, message: str)
    """
    subject = 'Password Reset OTP' if is_password_reset else 'Your Verification OTP'
    message = f'Your {"password reset " if is_password_reset else "verification "}OTP is: {otp_code}. It expires in 10 minutes.'
    email_from = settings.EMAIL_HOST_USER
    recipient_list = [email.strip().lower()]
    
    # Always log OTP in terminal for easy local testing
    print(f"\n{'='*60}\n[OTP DISPATCH] Destination: {email} | OTP Code: {otp_code}\n{'='*60}\n")
    
    try:
        send_mail(subject, message, email_from, recipient_list, fail_silently=False)
        logger.info(f"Email OTP sent successfully to {email}")
        return True, "OTP sent via Email successfully."
    except Exception as e:
        logger.exception(f"Failed to send email OTP to {email}: {str(e)}")
        return False, f"Email delivery error: {str(e)}"
