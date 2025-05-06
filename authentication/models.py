from django.contrib.auth.models import AbstractUser
from django.db import models
from django.contrib.auth.models import User
from datetime import datetime
from django.utils import timezone

try:
    from django.db.models import JSONField
except ImportError:
    from django.contrib.postgres.fields import JSONField

# Create your models here.

class User(AbstractUser):
    """
    Custom User model that only stores authentication data
    All other user data is stored in MongoDB
    """
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    role = models.CharField(max_length=255, null=True, blank=True)
    def __str__(self):
        return self.username

class UserActivity(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    login_time = models.DateTimeField(auto_now_add=True)
    logout_time = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField()
    session_id = models.CharField(max_length=100)
    # Add new fields with null=True to make them optional for existing records
    user_agent = models.TextField(null=True, blank=True)
    is_active = models.BooleanField(null=True, default=False)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)
    role = models.CharField(max_length=255, null=True, blank=True)
    class Meta:
        db_table = 'authentication_useractivity'
        verbose_name = 'User Activity'
        verbose_name_plural = 'User Activities'
        ordering = ['-login_time']

    def __str__(self):
        return f"{self.user.username} - {self.login_time}"

class EmployeeTextNow(models.Model):
    email = models.EmailField(unique=True)
    password_email = models.CharField(max_length=255)
    password = models.CharField(max_length=255)  # password TextNow
    password_TF = models.CharField(max_length=255, blank=True, null=True)  # password TextFree
    supplier = models.CharField(max_length=50, blank=True, null=True)
    status_account_TN = models.CharField(max_length=50, default='chưa tạo acc')
    status_account_TF = models.CharField(max_length=50, blank=True, null=True)
    refresh_token = models.TextField(blank=True, null=True)
    client_id = models.CharField(max_length=255, blank=True, null=True)
    full_information = models.TextField(blank=True, null=True)
    created_by = models.CharField(max_length=255)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    sold_status_TN = models.BooleanField(default=False)
    sold_status_TF = models.BooleanField(default=False)

    class Meta:
        db_table = 'employee_textnow'
        ordering = ['-created_at']

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        # Tự động tạo full_information khi lưu
        if not self.full_information and self.refresh_token and self.client_id:
            self.full_information = f"{self.email}|{self.password_email}|{self.refresh_token}|{self.client_id}"
        super().save(*args, **kwargs)
