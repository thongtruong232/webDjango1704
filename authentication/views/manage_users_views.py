from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .mongodb import get_collection_handle
from django.utils import timezone
from django.views.decorators.http import require_POST
from authentication.permissions import (
    role_required, can_manage_users, can_update_status, 
    ROLES, get_allowed_status_updates
)
from authentication.models import User, UserActivity
import xlsxwriter
from io import BytesIO
import pytz
from datetime import datetime, timedelta
from django.db.models import Count
from django.db.models.functions import TruncDate, ExtractWeek
from authentication.otpsend import send_otp_email
from django.contrib.auth import get_user_model, login
from pymongo import MongoClient
from django.conf import settings
import logging
from django.db import transaction
from django.core.cache import cache
from django.core.exceptions import ValidationError
import time
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import json
import re

# Định nghĩa múi giờ GMT+7
TIMEZONE = pytz.timezone('Asia/Bangkok')

logger = logging.getLogger(__name__)

def get_current_time():
    """Lấy thời gian hiện tại theo múi giờ GMT+7"""
    return timezone.now().astimezone(TIMEZONE)

@login_required
@role_required('admin')
def manage_users(request):
    users_collection, client = get_collection_handle('users')
    users = list(users_collection.find())
    client.close()
    # Get user data from MongoDB
    user_data = users_collection.find_one({'user_id': str(request.user.id)})
    context = {
        'user_data': user_data,
        'users': users,
        'roles': ROLES.keys(),
    }

    return render(request, 'authentication/manage_users.html', context)

@login_required
@role_required('admin')
def create_sample_users(request):
    try:
        users_collection, client = get_collection_handle('users')
        if users_collection is None:
            messages.error(request, 'Không thể kết nối đến MongoDB')
            return redirect('manage_users')
        
        # Define sample users
        sample_users = [
            {
                'username': 'admin_user',
                'password': '123123',
                'email': 'admin@example.com',
                'role': 'admin'
            },
            {
                'username': 'quanly_user',
                'password': '123123',
                'email': 'quanly@example.com',
                'role': 'quanly'
            },
            {
                'username': 'kiemtra_user',
                'password': '123123',
                'email': 'kiemtra@example.com',
                'role': 'kiemtra'
            },
            {
                'username': 'nhanvien_user',
                'password': '123123',
                'email': 'nhanvien@example.com',
                'role': 'nhanvien'
            }
        ]
        
        created_users = []
        existing_users = []
        
        for user_data in sample_users:
            # Check if user exists in Django
            if User.objects.filter(username=user_data['username']).exists():
                # Check if user exists in MongoDB
                mongo_user = users_collection.find_one({'username': user_data['username']})
                if mongo_user is None:
                    # User exists in Django but not in MongoDB, create in MongoDB
                    user = User.objects.get(username=user_data['username'])
                    mongo_user_data = {
                        'user_id': str(user.id),
                        'username': user.username,
                        'email': user.email,
                        'password': user_data['password'],
                        'role': user_data['role'],
                        'created_at': timezone.now().isoformat()
                    }
                    users_collection.update_one(
                        {'user_id': str(user.id)},
                        {'$set': mongo_user_data},
                        upsert=True
                    )
                    created_users.append(user_data['username'])
                else:
                    existing_users.append(user_data['username'])
                continue
                
            try:
                # Create Django user
                user = User.objects.create_user(
                    username=user_data['username'],
                    email=user_data['email'],
                    password=user_data['password']
                )
                
                # Store additional user data in MongoDB
                mongo_user_data = {
                    'user_id': str(user.id),
                    'username': user.username,
                    'email': user.email,
                    'password': user_data['password'],
                    'role': user_data['role'],
                    'created_at': timezone.now().isoformat()
                }
                
                users_collection.update_one(
                    {'user_id': str(user.id)},
                    {'$set': mongo_user_data},
                    upsert=True
                )
                
                created_users.append(user_data['username'])
            except Exception as e:
                messages.error(request, f'Error creating user {user_data["username"]}: {str(e)}')
        
        if created_users:
            messages.success(request, f'Đã tạo thành công các user: {", ".join(created_users)}')
        if existing_users:
            messages.warning(request, f'Các user đã tồn tại: {", ".join(existing_users)}')
            
        return redirect('manage_users')
        
    except Exception as e:
        messages.error(request, f'Lỗi khi tạo user mẫu: {str(e)}')
        return redirect('manage_users')
    finally:
        if client is not None:
            try:
                client.close()
            except:
                pass

@login_required
@role_required(['admin'])
def register_otp(request):
    if request.method == 'POST':
        try:
            # Lấy thông tin từ request
            username_register = request.POST.get('username_register')
            if not username_register:
                return JsonResponse({
                    'success': False,
                    'message': 'Vui lòng nhập username'
                })
            
            # Kiểm tra username đã tồn tại trong Django không
            user_in_django = User.objects.filter(username=username_register).first()
            
            # Kiểm tra username đã tồn tại trong MongoDB không
            users_collection, client = get_collection_handle('users')
            if users_collection is None:
                return JsonResponse({
                    'success': False,
                    'message': 'Không thể kết nối đến cơ sở dữ liệu'
                })
            try:
                mongo_user = users_collection.find_one({'username': username_register})
                if user_in_django and mongo_user:
                    return JsonResponse({
                        'success': False,
                        'message': 'Username đã tồn tại trong hệ thống, vui lòng chọn username khác'
                    })
                elif user_in_django and not mongo_user:
                    # Nếu user chỉ tồn tại ở Django, xóa user ở Django
                    user_in_django.delete()
                    # Cho phép tạo mới (gửi OTP)
                elif not user_in_django and mongo_user:
                    return JsonResponse({
                        'success': False,
                        'message': 'Username đã tồn tại trong hệ thống, vui lòng chọn username khác'
                    })
                # Nếu username chưa tồn tại ở cả hai, hoặc vừa xóa ở Django, gửi OTP
                otp_code = send_otp_email(username_register)
                if not otp_code:
                    return JsonResponse({
                        'success': False,
                        'message': 'Không thể gửi mã OTP, vui lòng thử lại sau'
                    })
                request.session['otp_username'] = username_register
                request.session['otp_required'] = True
                request.session['otp_code'] = otp_code
                request.session.save()
                return JsonResponse({
                    'success': True,
                    'message': 'OTP đã được gửi thành công'
                })
            finally:
                client.close()
        except Exception as e:
            logger.error(f'Error in register_otp: {str(e)}')
            return JsonResponse({
                'success': False,
                'message': f'Có lỗi xảy ra khi tạo OTP: {str(e)}'
            })
    return JsonResponse({
        'success': False,
        'message': 'Phương thức không được hỗ trợ'
    })

@login_required
@role_required(['admin'])
def render_manage_users(request, extra_context=None):
    users = User.objects.all()
    roles = request.user.roles.all()
    context = {
        'users': users,
        'roles': roles,
    }
    if extra_context:
        context.update(extra_context)
    return render(request, 'authentication/manage_users.html', context)

@login_required
@role_required(['admin'])
def verify_otp_view_register(request):
    if request.method == 'POST':
        try:
            input_otp = request.POST.get('otp')
            session_otp = request.session.get('otp_code')
            username = request.session.get('otp_username')
            password = request.POST.get('password_register')
            role = request.POST.get('role')

            if not all([input_otp, session_otp, username, password, role]):
                return JsonResponse({
                    'success': False,
                    'message': 'Thiếu thông tin cần thiết'
                })

            if input_otp != session_otp:
                return JsonResponse({
                    'success': False,
                    'message': 'Mã OTP không đúng, vui lòng thử lại'
                })

            # Kiểm tra username đã tồn tại trong MongoDB không
            users_collection, client = get_collection_handle('users')
            if users_collection is None:
                return JsonResponse({
                    'success': False,
                    'message': 'Không thể kết nối đến cơ sở dữ liệu'
                })
                
            try:
                mongo_user = users_collection.find_one({'username': username})
                if mongo_user is not None:
                    return JsonResponse({
                        'success': False,
                        'message': 'Username đã tồn tại trong hệ thống, vui lòng chọn username khác'
                    })
                
                # Tạo unique email
                timestamp = int(timezone.now().timestamp())
                unique_email = f"{username}_{timestamp}@example.com"
                
                # Tạo user trong Django trước
                user = User.objects.create_user(
                    username=username,
                    email=unique_email,
                    password=password
                )
                
                # Tạo user trong MongoDB với user_id từ Django
                mongo_user_data = {
                    'user_id': str(user.id),
                    'username': username,
                    'email': unique_email,
                    'password': password,
                    'role': role,
                    'created_at': get_current_time().isoformat()
                }
                
                users_collection.insert_one(mongo_user_data)
                
                # Xóa thông tin OTP khỏi session
                if 'otp_code' in request.session:
                    del request.session['otp_code']
                if 'otp_username' in request.session:
                    del request.session['otp_username']
                if 'otp_required' in request.session:
                    del request.session['otp_required']
                request.session.save()
                
                return JsonResponse({
                    'success': True,
                    'message': 'Tạo user thành công',
                    'redirect_url': '/manage-users/'
                })
                
            except Exception as e:
                # Nếu có lỗi khi tạo trong MongoDB, xóa user trong Django
                if 'user' in locals():
                    user.delete()
                raise e
                
            finally:
                client.close()
                
        except Exception as e:
            print(f'Error in verify_otp_view_register: {str(e)}')
            return JsonResponse({
                'success': False,
                'message': f'Có lỗi xảy ra khi xác thực OTP: {str(e)}'
            })
            
    return JsonResponse({
        'success': False,
        'message': 'Phương thức không được hỗ trợ'
    })

@login_required
@role_required('admin')
def update_user_role(request):
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        new_role = request.POST.get('role')
        
        if not user_id or not new_role or new_role not in ROLES:
            return JsonResponse({'success': False, 'message': 'Invalid parameters'})
        
        try:
            # Cập nhật trong MongoDB
            users_collection, client = get_collection_handle('users')
            if users_collection is None:
                return JsonResponse({'success': False, 'message': 'Cannot connect to database'})
                
            # Kiểm tra user tồn tại trong MongoDB
            mongo_user = users_collection.find_one({'user_id': user_id})
            if not mongo_user:
                return JsonResponse({'success': False, 'message': 'User not found in MongoDB'})
                
            # Cập nhật role trong MongoDB
            result = users_collection.update_one(
                {'user_id': user_id},
                {'$set': {'role': new_role}}
            )
            
            if result.modified_count > 0:
                return JsonResponse({'success': True})
            else:
                return JsonResponse({'success': False, 'message': 'Failed to update role in MongoDB'})
                
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
        finally:
            if 'client' in locals():
                client.close()
    
    return JsonResponse({'success': False, 'message': 'Invalid request method'})

@login_required
@role_required('admin')
def delete_user(request):
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        
        if not user_id:
            return JsonResponse({
                'success': False,
                'message': 'Thiếu thông tin user'
            })
        
        try:
            # Lấy thông tin user từ MongoDB trước khi xóa
            users_collection, client = get_collection_handle('users')
            if users_collection is None:
                return JsonResponse({
                    'success': False,
                    'message': 'Không thể kết nối đến cơ sở dữ liệu'
                })
            
            mongo_user = users_collection.find_one({'user_id': user_id})
            if not mongo_user:
                return JsonResponse({
                    'success': False,
                    'message': 'Không tìm thấy user trong MongoDB'
                })

            # Lưu thông tin user để có thể rollback nếu cần
            user_backup = mongo_user.copy()
            
            # Xóa user khỏi MongoDB
            mongo_result = users_collection.delete_one({'user_id': user_id})
            
            if mongo_result.deleted_count > 0:
                try:
                    # Xóa user khỏi Django
                    user = User.objects.get(id=user_id)
                    user.delete()
                    
                    # Ghi log hoạt động
                    logger.info(f'User {user_id} đã được xóa thành công')
                    
                    return JsonResponse({
                        'success': True,
                        'message': 'Xóa user thành công'
                    })
                    
                except User.DoesNotExist:
                    # Nếu không tìm thấy user trong Django, rollback MongoDB
                    users_collection.insert_one(user_backup)
                    logger.error(f'Không tìm thấy user {user_id} trong Django, đã rollback MongoDB')
                    return JsonResponse({
                        'success': False,
                        'message': 'Không tìm thấy user trong Django'
                    })
                except Exception as e:
                    # Nếu có lỗi khi xóa trong Django, rollback MongoDB
                    users_collection.insert_one(user_backup)
                    logger.error(f'Lỗi khi xóa user {user_id} trong Django: {str(e)}, đã rollback MongoDB')
                    return JsonResponse({
                        'success': False,
                        'message': f'Lỗi khi xóa user trong Django: {str(e)}'
                    })
            else:
                return JsonResponse({
                    'success': False,
                    'message': 'Không thể xóa user khỏi MongoDB'
                })
                
        except Exception as e:
            logger.error(f'Lỗi khi xóa user {user_id}: {str(e)}')
            return JsonResponse({
                'success': False,
                'message': f'Có lỗi xảy ra: {str(e)}'
            })
        finally:
            if 'client' in locals():
                client.close()
    
    return JsonResponse({
        'success': False,
        'message': 'Phương thức không được hỗ trợ'
    })

@login_required
@role_required('admin')
def change_user_password(request):
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        new_password = request.POST.get('new_password')
        
        if not user_id or not new_password:
            return JsonResponse({
                'success': False,
                'message': 'Thiếu thông tin cần thiết'
            })
        
        try:
            # Lấy user từ Django
            user = User.objects.get(id=user_id)
            
            # Đặt mật khẩu mới trong Django
            user.set_password(new_password)
            user.save()
            
            # Cập nhật mật khẩu trong MongoDB
            users_collection, client = get_collection_handle('users')
            if users_collection is None:
                # Nếu không thể kết nối MongoDB, rollback thay đổi trong Django
                user.set_password(user.password)  # Khôi phục mật khẩu cũ
                user.save()
                return JsonResponse({
                    'success': False,
                    'message': 'Không thể kết nối đến cơ sở dữ liệu'
                })
            
            result = users_collection.update_one(
                {'user_id': str(user_id)},
                {'$set': {'password': new_password}}
            )
            
            client.close()
            
            if result.modified_count > 0:
                return JsonResponse({
                    'success': True,
                    'message': 'Đổi mật khẩu thành công'
                })
            else:
                # Nếu không cập nhật được trong MongoDB, rollback thay đổi trong Django
                user.set_password(user.password)  # Khôi phục mật khẩu cũ
                user.save()
                return JsonResponse({
                    'success': False,
                    'message': 'Không tìm thấy user trong MongoDB'
                })
            
        except User.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Không tìm thấy user'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            })
    
    return JsonResponse({
        'success': False,
        'message': 'Phương thức không được hỗ trợ'
    })

