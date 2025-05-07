from django.urls import path
from . import views
from .views.manger_admin_sale_views import manager_textnow_view, delete_employee, export_employee_textnow_excel

urlpatterns = [
    path('', views.home_view, name='home'),
    path('login/', views.login_view, name='login'),
    path('home/', views.verify_otp_view, name='verify_otp'),
    path('verify_otp_view_register/', views.verify_otp_view_register, name='verify_otp_view_register'),
    path('register_otp/', views.register_otp, name='register_otp'),
    path('logout/', views.logout_view, name='logout'),
    path('update-status/', views.update_status, name='update_status'),
    path('update-checkbox-status/', views.update_checkbox_status, name='update_checkbox_status'),
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

    # Employee urls
    path('create-mail/', views.create_email_view, name='create_email'),
    path('verified/', views.employee_verified_view, name='employee_verified'),
    path('employee/dashboard/', views.employee_dashboard_view, name='employee_dashboard'),
    path('employee/work/', views.employee_work_view, name='employee_work'),
    path('create-password/', views.create_password_view, name='create_password'),
    path('available-emails/', views.email_info_view, name='available_emails'),
    path('api/available-emails/', views.get_available_emails_api, name='get_available_emails_api'),
    path('api/create-textnow/', views.create_textnow_api, name='create_textnow_api'),
    path('api/save-worksession/', views.save_worksession_api, name='save_worksession'),
    path('api/verified-textnow-update/', views.update_textnow_status_api, name='verified_textnow_api'),
    path('api/search-textnow/', views.search_textnow_api, name='search_textnow_api'),
    # admin manager
    path('manager-admin-sale/', manager_textnow_view, name='manager_textnow_view'),
    path('delete-employee/', delete_employee, name='delete_employee'),
    path('export-employee-textnow-excel/', export_employee_textnow_excel, name='export_employee_textnow_excel'),
]

