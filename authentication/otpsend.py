import random
from django.core.mail import send_mail
import datetime
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient

def connectionDB():
    client = MongoClient("mongodb://localhost:27017/")
    db = client["mongodbCloud"]
    users_collection = db["users"]
    return users_collection
def generate_otp():
    return str(random.randint(100000, 999999))

def send_otp_email(subject):
    users_collection = connectionDB()
    otp_code = generate_otp()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=5)  # OTP hết hạn sau 5 phút
    subject = "Mã OTP xác thực đăng nhập"
    message = f"Mã OTP của tài khoản {subject} là: {otp_code}. Mã này có hiệu lực trong 5 phút."
    from_email = 'elivibes0124@gmail.com'
    recipient_email = ['thongtruong232@gmail.com']
    users_collection.update_one(
            {"username": "admin_user"},
            {
                "$set": {
                    "temp_otp": "123456",
                    "otp_expiry": expires_at
                }
            }
        )
    send_mail(subject, message, from_email, recipient_email)
    return otp_code