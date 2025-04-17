from django.contrib.auth.models import AbstractUser
from django.db import models
from django.contrib.auth.models import User
from datetime import datetime
import pytz
import uuid
from django.utils import timezone
from django.core.serializers.json import DjangoJSONEncoder
import json
import logging

# Use JSONField from django.db.models if Django >= 3.1
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

    class Meta:
        db_table = 'authentication_useractivity'
        verbose_name = 'User Activity'
        verbose_name_plural = 'User Activities'
        ordering = ['-login_time']

    def __str__(self):
        return f"{self.user.username} - {self.login_time}"
