import random
from django.core.mail import send_mail
import datetime
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient
import os
from django.conf import settings
import logging
from django.utils.timezone import now, is_aware, make_aware

logger = logging.getLogger(__name__)

def connectionDB():
    try:
        client = MongoClient(settings.MONGODB_URI)
        db = client[settings.MONGODB_DATABASE]
        users_collection = db["users"]
        return users_collection
    except Exception as e:
        logger.error(f"Error connecting to MongoDB: {str(e)}")
        return None

def generate_otp():
    return str(random.randint(100000, 999999))

def send_otp_email(username):
    try:
        # Generate OTP
        otp_code = generate_otp()
        # now = datetime.now(timezone.utc)
        # expires_at = now + timedelta(minutes=5)  # OTP hết hạn sau 5 phút
        
        # Prepare email content
        subject = "Mã OTP xác thực đăng nhập"
        message = f"Mã OTP của tài khoản {username} là: {otp_code}. Mã này có hiệu lực trong 5 phút."
        from_email = settings.EMAIL_HOST_USER
        recipient_email = [settings.EMAIL_HOST_USER]  # Gửi OTP đến email của admin
        
        
        # Send email
        send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=recipient_email,
            fail_silently=False
        )
        
        logger.info(f"OTP sent successfully to {username}")
        return otp_code
        
    except Exception as e:
        logger.error(f"Error sending OTP: {str(e)}")
        return None