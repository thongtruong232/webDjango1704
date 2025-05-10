from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from authentication.mongodb import MongoDBConnection, get_collection_handle
from bson.objectid import ObjectId
from django.utils import timezone
from django.views.decorators.http import require_POST
from authentication.permissions import (
    role_required, can_manage_users, can_update_status, 
    ROLES, get_allowed_status_updates
)
from authentication.models import User, UserActivity
import pytz
from datetime import datetime, timedelta
from authentication.otpsend import send_otp_email
from django.contrib.auth import get_user_model, login
import logging
from django.db import transaction
from django.core.exceptions import ValidationError
import time
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.conf import settings

# Định nghĩa múi giờ GMT+7
TIMEZONE = pytz.timezone('Asia/Bangkok')

logger = logging.getLogger(__name__)

def get_current_time():
    """Lấy thời gian hiện tại theo múi giờ GMT+7"""
    return timezone.now().astimezone(TIMEZONE)


def login_view(request):
    if request.user.is_authenticated:
        print('Đã đăng nhập')
        # Kiểm tra role của user
        with MongoDBConnection() as mongo:
            if mongo is None or mongo.db is None:
                messages.error(request, 'Không thể kết nối đến cơ sở dữ liệu')
                return redirect('login')
                
            users_collection = mongo.get_collection('users')
            if users_collection is None:
                messages.error(request, 'Không thể truy cập collection users')
                return redirect('login')
                
            user_data = users_collection.find_one({'user_id': str(request.user.id)})
            
            if user_data:
                user_role = user_data.get('role')
                print(f'Role của user: {user_role}')
                if user_role == 'nhanvien':
                    return redirect('employee_verified')
                elif user_role in ['admin', 'quanly', 'kiemtra']:
                    return redirect('manager_admin_sale')
                else:
                    return redirect('manager_admin_sale')
            else:
                # Nếu không tìm thấy user trong MongoDB, đăng xuất và chuyển về trang login
                logout(request)
                messages.error(request, 'Không tìm thấy thông tin người dùng')
                return redirect('login')
        
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        try:
            with transaction.atomic():
                with MongoDBConnection() as mongo:
                    if mongo is None or mongo.db is None:
                        raise ValidationError('Không thể kết nối đến cơ sở dữ liệu')
                    
                    users_collection = mongo.get_collection('users')
                    if users_collection is None:
                        raise ValidationError('Không thể truy cập collection users')
                    
                    # Tìm user trong MongoDB
                    mongo_user = users_collection.find_one({'username': username})
                            
                    if mongo_user is None or mongo_user.get('password') != password:
                        messages.error(request, 'Tên đăng nhập hoặc mật khẩu không đúng')
                        return render(request, 'authentication/login.html')
                            
                    # Kiểm tra user có tồn tại trong Django không
                    user = None
                    if 'user_id' in mongo_user:
                        try:
                            user = User.objects.get(id=mongo_user['user_id'])
                        except User.DoesNotExist:
                            pass
                            
                    # Nếu không tìm thấy trong Django, tạo mới
                    if user is None:
                        if 'email' not in mongo_user:
                            mongo_user['email'] = f"{username}_{int(timezone.now().timestamp())}@example.com"
                                    
                        user = User.objects.create_user(
                            username=username,
                            email=mongo_user['email'],
                            password=password
                        )
                                
                        users_collection.update_one(
                            {'username': username},
                            {'$set': {'user_id': str(user.id)}}
                        )
                        mongo_user['user_id'] = str(user.id)
                            
                    # Tạo session_id mới
                    session_id = request.session.session_key or request.session.create()
                    request.session['activity_session_id'] = session_id
                            
                    # Tạo OTP và lưu vào session
                    otp_code = send_otp_email(username)
                    if not otp_code:
                        messages.error(request, 'Không thể gửi mã OTP, vui lòng thử lại sau')
                        return render(request, 'authentication/login.html')
                            
                    # Lưu thông tin vào session
                    request.session['pre_otp_user'] = user.id
                    request.session['otp_username'] = username
                    request.session['otp_required'] = True
                    request.session['otp_code'] = otp_code
                    request.session['otp_timestamp'] = time.time()
                    request.session.set_expiry(3600)  # 1 giờ
                            
                    # Lưu session và kiểm tra
                    request.session.save()
                    if not request.session.session_key:
                        logger.error("Failed to save session")
                        messages.error(request, 'Có lỗi xảy ra, vui lòng thử lại')
                        return render(request, 'authentication/login.html')
                            
                    logger.info(f"Session saved with key: {request.session.session_key}")
                    logger.info(f"OTP code: {otp_code}")
                    logger.info(f"User ID: {user.id}")
                            
                    return render(request, 'authentication/login.html', {
                        'otp_required': True,
                        'username': username
                    })
                    
        except ValidationError as e:
            messages.error(request, str(e))
        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            return render(request, 'authentication/login.html', {'error': 'Có lỗi xảy ra'})
    
    return render(request, 'authentication/login.html')


def verify_otp_view(request):
    if request.method == 'POST':
        input_otp = request.POST.get('otp')
        session_otp = request.session.get('otp_code')
        pre_user_id = request.session.get('pre_otp_user')
        username = request.session.get('otp_username')
        
        # Debug log
        # logger.info(f"Input OTP: {input_otp}")
        # logger.info(f"Session OTP: {session_otp}")
        # logger.info(f"Pre User ID: {pre_user_id}")
        # logger.info(f"Username: {username}")
        
        # Kiểm tra session data
        if not all([input_otp, session_otp, pre_user_id, username]):
            logger.error("Missing session data")
            return JsonResponse({
                'success': False,
                'message': 'Thiếu thông tin cần thiết'
            })
            
        # Kiểm tra OTP
        if input_otp != session_otp:
            logger.error(f"OTP mismatch: input={input_otp}, session={session_otp}")
            return JsonResponse({
                'success': False,
                'message': 'Mã OTP không đúng, thử lại',
                'show_loading': False
            })
            
        try:
            # Kiểm tra user trong MongoDB
            users_collection, client = get_collection_handle('users')
            if users_collection is None:
                logger.error("Failed to connect to MongoDB")
                return JsonResponse({
                    'success': False,
                    'message': 'Không thể kết nối đến cơ sở dữ liệu'
                })
                
            try:
                mongo_user = users_collection.find_one({'username': username})
                if mongo_user is None:
                    logger.error(f"User not found in MongoDB: {username}")
                    return JsonResponse({
                        'success': False,
                        'message': 'Tài khoản không tồn tại trong hệ thống'
                    })
                
                # Lấy user từ Django
                User = get_user_model()
                try:
                    user = User.objects.get(id=pre_user_id, username=username)
                except User.DoesNotExist:
                    logger.error(f"User not found in Django: {username}")
                    user = User.objects.create_user(
                        username=username,
                        email=mongo_user.get('email', f"{username}@example.com"),
                        password=mongo_user.get('password', '')
                    )
                
                # Đăng nhập user
                login(request, user)
                
                # Lưu thông tin đăng nhập vào session
                request.session['otp_verified'] = True
                request.session['otp_required'] = False
                request.session.save()  # Lưu session sau khi cập nhật
                
                # Cập nhật trạng thái hoạt động trong MongoDB
                current_time = timezone.now().astimezone(TIMEZONE)
                session_id = request.session.session_key or request.session.create()
                request.session['activity_session_id'] = session_id
                
                users_collection.update_one(
                    {'user_id': str(user.id)},
                    {'$set': {
                        'is_active': True,
                        'last_activity': current_time.isoformat(),
                        'last_login': current_time.isoformat(),
                        'current_session_id': session_id
                    }}
                )
                
                # Lưu thông tin đăng nhập vào MongoDB
                user_activity_collection = client['user_activities']['activities']
                login_data = {
                    'user_id': str(user.id),
                    'username': username,
                    'login_time': current_time.isoformat(),
                    'ip_address': request.META.get('REMOTE_ADDR'),
                    'user_agent': request.META.get('HTTP_USER_AGENT'),
                    'session_id': session_id,
                    'is_active': True,
                    'created_at': current_time.isoformat(),
                    'updated_at': current_time.isoformat(),
                    'status': 'active'
                }
                
                user_activity_collection.insert_one(login_data)

                # Cập nhật work_time collection
                work_time_collection = client['work_time']['stats']
                work_time_data = {
                    'user_id': str(user.id),
                    'username': username,
                    'date': current_time.date().isoformat(),
                    'login_time': current_time.isoformat(),
                    'session_id': session_id,
                    'is_active': True,
                    'created_at': current_time.isoformat(),
                    'updated_at': current_time.isoformat()
                }
                
                work_time_collection.insert_one(work_time_data)
                
                # Gửi thông báo WebSocket
                try:
                    channel_layer = get_channel_layer()
                    if channel_layer is not None:
                        async_to_sync(channel_layer.group_send)(
                            "user_activity",
                            {
                                'type': 'activity_status',
                                'user_id': str(user.id),
                                'is_active': True,
                                'session_id': session_id,
                                'last_activity': current_time.strftime('%Y-%m-%d %H:%M:%S')
                            }
                        )
                except Exception as e:
                    logger.error(f"Error sending WebSocket notification: {str(e)}")
                
                # Ghi lại thời gian login
                UserActivity.objects.create(
                    user=user,
                    ip_address=request.META.get('REMOTE_ADDR'),
                    user_agent=request.META.get('HTTP_USER_AGENT')
                )
                
                user_role = mongo_user.get('role')
                if user_role == 'nhanvien':
                    return JsonResponse({
                        'success': True,
                        'redirect_url': '/verified/',
                        'message': 'Đăng nhập thành công'
                    })
                else:
                    return JsonResponse({
                        'success': True,
                        'redirect_url': '/manager-admin-sale/',
                        'message': 'Đăng nhập thành công'
                    })
                    
            finally:
                client.close()
            
        except Exception as e:
            logger.error('Error during OTP verification', exc_info=True)
            return JsonResponse({
                'success': False,
                'message': f'Có lỗi xảy ra: {str(e)}'
            })

    return redirect('login')

def logout_view(request):
    try:
        if request.user.is_authenticated:
            username = request.user.username
            user_id = request.user.id
            current_time = timezone.now().astimezone(TIMEZONE)
            session_id = request.session.get('activity_session_id')
            
            # Kết nối MongoDB
            users_collection, client = get_collection_handle('users')
            if client:
                try:
                    # Cập nhật trạng thái is_active trong users collection
                    users_collection.update_one(
                        {'user_id': str(user_id)},
                        {
                            '$set': {
                                'is_active': False,
                                'last_activity': current_time.isoformat(),
                                'last_logout': current_time.isoformat()
                            }
                        }
                    )
                    
                    # Lấy phiên hoạt động mới nhất của user
                    user_activity_collection = client['user_activities']['activities']
                    query = {'user_id': str(user_id)}
                    if session_id:
                        query['session_id'] = session_id
                    else:
                        query['logout_time'] = {'$exists': False}
                    
                    latest_activity = user_activity_collection.find_one(
                        query,
                        sort=[('login_time', -1)]
                    )

                    if latest_activity:
                        # Cập nhật logout_time và các thông tin khác cho phiên hoạt động
                        user_activity_collection.update_one(
                            {'_id': latest_activity['_id']},
                            {
                                '$set': {
                                    'logout_time': current_time.isoformat(),
                                    'is_active': False,
                                    'status': 'inactive',
                                    'updated_at': current_time.isoformat(),
                                    'session_duration': {
                                        'seconds': (current_time - datetime.fromisoformat(latest_activity['login_time'])).total_seconds(),
                                        'formatted': str(current_time - datetime.fromisoformat(latest_activity['login_time']))
                                    }
                                }
                            }
                        )

                        # Cập nhật work_time collection
                        work_time_collection = client['work_time']['stats']
                        work_time_collection.update_one(
                            {
                                'user_id': str(user_id),
                                'session_id': session_id,
                                'logout_time': {'$exists': False}
                            },
                            {
                                '$set': {
                                    'logout_time': current_time.isoformat(),
                                    'is_active': False,
                                    'updated_at': current_time.isoformat(),
                                    'duration': (current_time - datetime.fromisoformat(latest_activity['login_time'])).total_seconds(),
                                    'duration_str': str(current_time - datetime.fromisoformat(latest_activity['login_time']))
                                }
                            }
                        )
                        
                        # Gửi thông báo WebSocket
                        try:
                            channel_layer = get_channel_layer()
                            if channel_layer:
                                async_to_sync(channel_layer.group_send)(
                                    "user_activity",
                                    {
                                        "type": "activity_status",
                                        "user_id": str(user_id),
                                        "logout_time": current_time.isoformat(),
                                        "session_id": latest_activity.get('session_id'),
                                        "is_active": False,
                                        "session_duration": {
                                            "seconds": (current_time - datetime.fromisoformat(latest_activity['login_time'])).total_seconds(),
                                            "formatted": str(current_time - datetime.fromisoformat(latest_activity['login_time']))
                                        }
                                    }
                                )
                        except Exception as e:
                            logger.error(f"Error sending WebSocket notification: {str(e)}")
                            
                finally:
                    client.close()
            
            # Xóa session_id
            if 'activity_session_id' in request.session:
                del request.session['activity_session_id']
    
        # Đăng xuất người dùng
        logout(request)
        return redirect('login')
        
    except Exception as e:
        logger.error(f"Error in logout_view: {str(e)}")
        messages.error(request, 'Có lỗi xảy ra khi đăng xuất. Vui lòng thử lại.')
        return redirect('home')

@login_required
def update_status(request):
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'message': 'Vui lòng đăng nhập'})
    
    if request.method == 'POST':
        client = None
        try:
            record_id = request.POST.get('record_id')
            new_status = request.POST.get('status')
            
            if not record_id or not new_status:
                return JsonResponse({'success': False, 'message': 'Thiếu thông tin cần thiết'})
            
            # Kiểm tra quyền cập nhật trạng thái từ MongoDB
            users_collection, users_client = get_collection_handle('users')
            if users_collection is None:
                return JsonResponse({'success': False, 'message': 'Không thể kết nối đến cơ sở dữ liệu'})
            
            user_data = users_collection.find_one({'user_id': str(request.user.id)})
            if not user_data:
                return JsonResponse({'success': False, 'message': 'Không tìm thấy thông tin người dùng'})
            
            user_role = user_data.get('role')
            
            # Chỉ cho phép admin và quanly cập nhật trạng thái
            if user_role not in ['admin', 'quanly']:
                return JsonResponse({'success': False, 'message': 'Bạn không có quyền cập nhật trạng thái'})
            
            # Kiểm tra trạng thái hợp lệ
            allowed_statuses = [
                'Chưa sử dụng',
                'Đã đăng ký',
                'Email lỗi',
                'Đã kiểm tra',
                'Kiểm tra lỗi',
                'Đã xử lý',
                'Đang xử lý',
                'Chưa xử lý'
            ]
            
            if new_status not in allowed_statuses:
                return JsonResponse({'success': False, 'message': 'Trạng thái không hợp lệ'})
            
            # Kết nối MongoDB
            excel_data_collection, excel_client = get_collection_handle('excel_data')
            if excel_data_collection is None:
                return JsonResponse({'success': False, 'message': 'Không thể kết nối đến cơ sở dữ liệu'})
            
            # Kiểm tra bản ghi tồn tại
            existing_record = excel_data_collection.find_one({'id': record_id})
            if not existing_record:
                try:
                    existing_record = excel_data_collection.find_one({'_id': ObjectId(record_id)})
                except:
                    existing_record = None
            
            if not existing_record:
                return JsonResponse({'success': False, 'message': 'Không tìm thấy bản ghi'})
            
            # Cập nhật trạng thái
            result = excel_data_collection.update_one(
                {'id': record_id},
                {
                    '$set': {
                        'status': new_status,
                        'updated_by': request.user.username,
                        'updated_at': datetime.now()
                    }
                }
            )
            
            # Nếu không cập nhật được bằng id, thử bằng _id
            if result.modified_count == 0:
                try:
                    result = excel_data_collection.update_one(
                        {'_id': ObjectId(record_id)},
                        {
                            '$set': {
                                'status': new_status,
                                'updated_by': request.user.username,
                                'updated_at': datetime.now()
                            }
                        }
                    )
                except:
                    pass
            
            if result.modified_count > 0:
                return JsonResponse({
                    'success': True,
                    'message': 'Cập nhật trạng thái thành công',
                    'new_status': new_status
                })
            else:
                return JsonResponse({'success': False, 'message': 'Không tìm thấy bản ghi để cập nhật'})
                
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Lỗi: {str(e)}'})
        finally:
            if excel_client is not None:
                excel_client.close()
            if users_client is not None:
                users_client.close()
    else:
        return JsonResponse({'success': False, 'message': 'Phương thức không hợp lệ'})