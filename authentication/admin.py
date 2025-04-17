from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, UserActivity

# Register User model with Admin site
admin.site.register(User, UserAdmin)

# Register UserActivity model
@admin.register(UserActivity)
class UserActivityAdmin(admin.ModelAdmin):
    list_display = ('user', 'login_time', 'logout_time', 'ip_address')
    list_filter = ('user', 'login_time')
    search_fields = ('user__username', 'ip_address', 'session_id')
    ordering = ('-login_time',)
