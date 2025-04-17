from django.db import models
from django.utils import timezone
from datetime import datetime
import pytz
import json
# from authentication.models import User

EMAIL_SUPPLIER_CHOICES = {
    'f1mail': [],
    'đồng văn': []
}
EMAIL_STATUS_CHOICES = {
    'chưa sử dụng': ['live 1h-3h', 'live 1h-5h', 'xả láng kích hoạt 7 day die'],
    'đã sử dụng': ['Đã đăng ký', 'Đã đăng ký mail phụ', 'Email lỗi'],
}

TN_SUPPLIER = {
    'VIỆT': [],
    'QUÂN': [],
    'HOÀ' : []
}
TN_STATUS = {
    'VERIFED': ['ĐÃ QUAY SỐ, CHƯA QUAY SỐ'],
    'MAIL LỖI': [],
    'REG ACC LỖI' : [],
    'SAI MẬT KHẨU' : []
}

# Tạo timezone cho Việt Nam
vietnam_tz = pytz.timezone('Asia/Ho_Chi_Minh')

# Hàm lấy thời gian hiện tại theo múi giờ Việt Nam
def get_vietnam_time():
    return datetime.now(vietnam_tz)

def get_email_status_choices():
    return [(k, k) for k in EMAIL_STATUS_CHOICES.keys()]

def get_email_supplier_choices():
    return [(k, k) for k in EMAIL_SUPPLIER_CHOICES.keys()]
def get_textNow_supplier_choices():
    return [(k, k) for k in TN_SUPPLIER.keys()]
def get_textNow_status_choices():
    return [(k, k) for k in TN_STATUS.keys()]
class Email(models.Model):
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=255)
    refresh_token = models.CharField(max_length=255, blank=True, null=True)
    client_id = models.CharField(max_length=255, blank=True, null=True)

    status = models.CharField(max_length=50, choices=get_email_status_choices(),null=True)
    sub_status = models.CharField(max_length=100, blank=True, null=True)
    supplier = models.CharField(max_length=50, choices=get_email_supplier_choices())

    is_active = models.BooleanField(default=True)
    # created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="emails_created")
    is_provided = models.BooleanField(default=False,null=True)  # Đánh dấu đã cấp phát hay chưa

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.email
    
class TextNow(models.Model):
    email  = models.EmailField(unique=True)
    password_email  = models.CharField(max_length=255)
    password  = models.CharField(max_length=255)
    created_by  =  models.CharField(max_length=255,null=True,blank=True)
    status_account  = models.CharField(max_length=50, choices=get_textNow_status_choices())
    check_detail  = models.DateTimeField(null=True)
    sold_status  = models.BooleanField(default=False)
    update_phone_day  = models.DateTimeField(null=True)
    supplier  = models.CharField(max_length=50, choices=get_textNow_supplier_choices())
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    refresh_token = models.CharField(max_length=1000, null=True, blank=True)
    client_id = models.CharField(max_length=255, null=True, blank=True)
    def __str__(self):
        return self.email
class TextFree(models.Model):
    email  = models.EmailField(unique=True)
    password_email  = models.CharField(max_length=255)
    password  = models.CharField(max_length=255)
    created_by  =  models.CharField(max_length=255,null=True,blank=True)
    status_account  = models.CharField(max_length=50, choices=get_textNow_status_choices())
    sold_status  = models.BooleanField(default=False)
    supplier  = models.CharField(max_length=50, choices=get_textNow_supplier_choices())
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    refresh_token = models.CharField(max_length=1000, null=True, blank=True)
    client_id = models.CharField(max_length=255, null=True, blank=True)
    def __str__(self):
        return self.email

class WorkSession(models.Model):
    code = models.CharField(max_length=50, unique=True)
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    employee = models.CharField(max_length=100,null=True)  # Tên nhân viên
    total_accounts = models.IntegerField(default=0)  # Tổng số acc reg được
    created_textnow_emails = models.TextField(default=list)  # Danh sách email đã tạo TextNow


    def set_data(self, value):
        self.data = json.dumps(value)

    def get_data(self):
        return json.loads(self.data)
    def __str__(self):
        return f"{self.code} - {self.employee} ({self.start_time})"
    
    def end_session(self):
        self.end_time = timezone.now()
        self.save()
        
    def add_created_textnow(self, email):
        if email not in self.created_textnow_emails:
            self.created_textnow_emails.append(email)
            self.total_accounts = len(self.created_textnow_emails)
            self.save()
            
    def get_duration(self):
        if self.end_time:
            return self.end_time - self.start_time
        return timezone.now() - self.start_time
class PasswordRegProduct(models.Model):
    password = models.CharField(max_length=255)
    type = models.CharField(max_length=255)
    create_by = models.CharField(max_length=255)
    use_at = models.CharField(max_length=10)  # Lưu dưới dạng string theo format dd/mm/yyyy
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.password

    def save(self, *args, **kwargs):
        # Cập nhật updated_at trước khi lưu
        self.updated_at = datetime.now()
        super().save(*args, **kwargs)