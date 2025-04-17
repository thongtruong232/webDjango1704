from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('login/', views.login_view, name='login'),
    path('home/', views.verify_otp_view, name='verify_otp'),
    path('verify_otp_view_register/', views.verify_otp_view_register, name='verify_otp_view_register'),
    path('register_otp/', views.register_otp, name='register_otp'),
    path('logout/', views.logout_view, name='logout'),
    path('update-status/', views.update_status, name='update_status'),
    path('manage-users/', views.manage_users, name='manage_users'),
    path('update-user-role/', views.update_user_role, name='update_user_role'),
    path('create-sample-users/', views.create_sample_users, name='create_sample_users'),
    path('create-user/', views.create_user, name='create_user'),
    path('export-emails/', views.export_emails, name='export_emails'),
    path('work-management/', views.work_management, name='work_management'),
    path('change-user-password/', views.change_user_password, name='change_user_password'),
    path('delete-user/', views.delete_user, name='delete_user'),
    path('work-time-stats/', views.work_time_stats, name='work_time_stats'),
    path('check-username/', views.check_username, name='check_username'),
    path('check-user-status/', views.check_user_status, name='check_user_status'),
    path('update-activity/', views.update_activity, name='update_activity'),
    path('user-activity-stream/', views.user_activity_stream, name='user_activity_stream'),
    path('handle-browser-close/', views.handle_browser_close, name='handle_browser_close'),
]