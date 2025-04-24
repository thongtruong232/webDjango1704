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
import xlsxwriter
from io import BytesIO
import pytz
from datetime import datetime, timedelta
import logging
import time
import json

# Định nghĩa múi giờ GMT+7
TIMEZONE = pytz.timezone('Asia/Bangkok')

logger = logging.getLogger(__name__)

def get_current_time():
    """Lấy thời gian hiện tại theo múi giờ GMT+7"""
    return timezone.now().astimezone(TIMEZONE)


@login_required
@role_required(['admin', 'quanly'])
def work_time_stats(request):
    # Lấy thông tin filter từ request
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    user_id = request.GET.get('user_id')
    export_excel = request.GET.get('export') == 'true'  # Thêm flag xuất Excel

    logger.info(f"work_time_stats called with params - start_date: {start_date}, end_date: {end_date}, user_id: {user_id}")

    # Xử lý ngày tháng
    if not end_date:
        end_date = timezone.now().astimezone(TIMEZONE).date()
    else:
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    if not start_date:
        start_date = end_date - timedelta(days=30)
    else:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()

    # Kết nối MongoDB
    users_collection, client = get_collection_handle('users')
    if users_collection is None:
        logger.error("Failed to connect to MongoDB users collection")
        messages.error(request, 'Không thể kết nối đến cơ sở dữ liệu MongoDB')
        return render(request, 'authentication/work_time_stats.html', {
            'stats': [],
            'start_date': start_date,
            'end_date': end_date,
            'selected_user': user_id,
            'users': [],
            'user_data': None
        })

    try:
        # Lấy danh sách người dùng từ MongoDB
        mongo_users = list(users_collection.find({}, {'user_id': 1, 'username': 1, 'role': 1, 'is_active': 1}))
        
        # Lấy collection work_time
        work_time_collection = client['work_time']['stats']
        
        # Tạo query dựa trên tham số
        query = {
            'date': {
                '$gte': datetime.combine(start_date, datetime.min.time()).astimezone(TIMEZONE).isoformat(),
                '$lte': datetime.combine(end_date, datetime.max.time()).astimezone(TIMEZONE).isoformat()
            }
        }

        if user_id:
            query['user_id'] = str(user_id)

        # Lấy thống kê từ collection work_time
        stats = []
        for mongo_user in mongo_users:
            user_query = query.copy()
            user_query['user_id'] = str(mongo_user['user_id'])
            
            # Lấy thống kê của user
            user_stats = list(work_time_collection.find(user_query).sort('date', -1))
            
            if user_stats:
                # Tính tổng số phiên và thời gian
                total_sessions = len(user_stats)
                
                # Tính tổng thời gian làm việc
                total_duration = 0
                for stat in user_stats:
                    if 'duration' in stat:
                        total_duration += stat['duration']
                    elif 'logout_time' in stat and stat['logout_time']:
                        login_time = datetime.fromisoformat(stat['login_time'])
                        logout_time = datetime.fromisoformat(stat['logout_time'])
                        duration = (logout_time - login_time).total_seconds()
                        total_duration += duration
                
                total_hours = round(total_duration / 3600, 2)
                average_hours = round(total_hours / total_sessions, 2) if total_sessions > 0 else 0
                
                # Format lại các phiên làm việc
                formatted_activities = []
                for stat in user_stats:
                    try:
                        login_time = datetime.fromisoformat(stat['login_time'])
                        logout_time = datetime.fromisoformat(stat['logout_time']) if stat.get('logout_time') else None
                        
                        if 'duration' not in stat and logout_time:
                            duration = (logout_time - login_time).total_seconds()
                            duration_str = str(logout_time - login_time)
                        else:
                            duration = stat.get('duration', 0)
                            duration_str = stat.get('duration_str', '0:00:00')
                        
                        formatted_activities.append({
                            'login_time': login_time,
                            'logout_time': logout_time,
                            'session_duration': duration_str,
                            'session_id': stat['session_id']
                        })

                        # logger.info(f'login_time: {login_time}, logout_time: {logout_time}')
                    except Exception as e:
                        logger.error(f"Error formatting activity: {str(e)}", exc_info=True)
                        continue
                
                stats.append({
                    'user': {
                        'id': mongo_user['user_id'],
                        'username': mongo_user['username'],
                        'is_active': mongo_user['is_active']
                    },
                    'total_sessions': total_sessions,
                    'total_hours': total_hours,
                    'average_session': average_hours,
                    'activities': formatted_activities
                })

        # Nếu yêu cầu xuất Excel
        if export_excel:
            # Tạo file Excel trong bộ nhớ
            output = BytesIO()
            workbook = xlsxwriter.Workbook(output)
            worksheet = workbook.add_worksheet()

            # Định dạng cho header
            header_format = workbook.add_format({
                'bold': True,
                'bg_color': '#f8f9fa',
                'border': 1,
                'align': 'center'
            })

            # Định dạng cho các ô dữ liệu
            cell_format = workbook.add_format({
                'border': 1,
                'align': 'center'
            })

            # Viết tiêu đề báo cáo
            worksheet.merge_range('A1:C1', 'BÁO CÁO THỐNG KÊ THỜI GIAN LÀM VIỆC', header_format)
            
            # Viết thông tin về khoảng thời gian và nhân viên
            worksheet.write(2, 0, 'Từ ngày', header_format)
            worksheet.write(2, 1, start_date.strftime('%d/%m/%Y'), cell_format)
            worksheet.write(3, 0, 'Đến ngày', header_format)
            worksheet.write(3, 1, end_date.strftime('%d/%m/%Y'), cell_format)
            
            # Thêm thông tin nhân viên nếu được chọn
            if user_id:
                selected_user = next((user for user in mongo_users if str(user['user_id']) == user_id), None)
                if selected_user:
                    worksheet.write(4, 0, 'Nhân viên', header_format)
                    worksheet.write(4, 1, selected_user['username'], cell_format)

            # Viết header cho bảng thống kê
            headers = ['Nhân viên', 'Tổng thời gian (giờ)', 'Thời gian trung bình/phiên (giờ)']
            for col, header in enumerate(headers):
                worksheet.write(6, col, header, header_format)

            # Viết dữ liệu thống kê
            row = 7
            for stat in stats:
                # Nếu có chọn nhân viên cụ thể, chỉ xuất dữ liệu của nhân viên đó
                if user_id and str(stat['user']['id']) != user_id:
                    continue
                    
                data = [
                    stat['user']['username'],
                    stat['total_hours'],
                    stat['average_session']
                ]
                for col, value in enumerate(data):
                    worksheet.write(row, col, value, cell_format)
                row += 1

            # Điều chỉnh độ rộng cột
            column_widths = [25, 20, 25]
            for i, width in enumerate(column_widths):
                worksheet.set_column(i, i, width)

            # Đóng workbook
            workbook.close()

            # Chuẩn bị response
            output.seek(0)
            response = HttpResponse(
                output.read(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            
            # Tạo tên file dựa trên thông tin lọc
            filename = f"thong_ke_thoi_gian_lam_viec_{start_date.strftime('%d-%m-%Y')}_{end_date.strftime('%d-%m-%Y')}"
            if user_id:
                selected_user = next((user for user in mongo_users if str(user['user_id']) == user_id), None)
                if selected_user:
                    filename += f"_{selected_user['username']}"
            filename += ".xlsx"
            
            response['Content-Disposition'] = f'attachment; filename={filename}'
            
            return response

        # Lấy thông tin user từ MongoDB
        user_data = users_collection.find_one({'user_id': str(request.user.id)})

        context = {
            'stats': stats,
            'start_date': start_date,
            'end_date': end_date,
            'selected_user': user_id,
            'users': mongo_users,
            'user_data': user_data
        }
        
        return render(request, 'authentication/work_time_stats.html', context)
        
    except Exception as e:
        logger.error(f"Error in work_time_stats: {str(e)}", exc_info=True)
        messages.error(request, 'Có lỗi xảy ra khi tải dữ liệu')
        return render(request, 'authentication/work_time_stats.html', {
            'stats': [],
            'start_date': start_date,
            'end_date': end_date,
            'selected_user': user_id,
            'users': [],
            'user_data': None
        })
    finally:
        if client:
            try:
                client.close()
            except Exception as e:
                logger.error(f"Error closing MongoDB connection: {str(e)}")
@login_required
def user_activity_stream(request):
    """Stream user activity events using Server-Sent Events"""
    response = HttpResponse(content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'  # Disable buffering for Nginx
    
    def event_stream():
        try:
            # Lấy collection từ MongoDB
            users_collection, client = get_collection_handle('users')
            if users_collection is None:
                yield "data: {\"error\": \"Cannot connect to database\"}\n\n"
                return
                
            try:
                # Lấy danh sách user ban đầu với thông tin chi tiết
                users = list(users_collection.find({}, {
                    'user_id': 1, 
                    'is_active': 1,
                    'username': 1,
                    'last_activity': 1,
                    'last_login': 1,
                    'last_logout': 1
                }))
                
                # Lấy thông tin phiên làm việc từ work_time collection
                work_time_collection = client['work_time']['stats']
                
                for user in users:
                    # Lấy phiên làm việc gần nhất
                    latest_session = work_time_collection.find_one(
                        {'user_id': user['user_id']},
                        sort=[('login_time', -1)]
                    )
                    
                    session_data = {
                        'login_time': latest_session.get('login_time') if latest_session else None,
                        'logout_time': latest_session.get('logout_time') if latest_session else None,
                        'duration': latest_session.get('duration_str') if latest_session else None,
                        'session_id': latest_session.get('session_id') if latest_session else None
                    }
                    
                    yield f"data: {{\"type\": \"status_update\", \"user_id\": \"{user['user_id']}\", \"is_active\": {str(user.get('is_active', False)).lower()}, \"username\": \"{user.get('username', '')}\", \"last_activity\": \"{user.get('last_activity', '')}\", \"last_login\": \"{user.get('last_login', '')}\", \"last_logout\": \"{user.get('last_logout', '')}\", \"session\": {json.dumps(session_data)}}}\n\n"
                
                # Theo dõi thay đổi trong collection
                pipeline = [
                    {
                        '$match': {
                            '$or': [
                                {'operationType': 'update'},
                                {'operationType': 'insert'}
                            ]
                        }
                    }
                ]
                
                # Tạo một event để theo dõi client disconnection
                client_disconnected = False
                last_heartbeat = time.time()
                
                def handle_client_disconnect():
                    nonlocal client_disconnected
                    client_disconnected = True
                
                # Gắn handler cho client disconnection
                request.environ['wsgi.input']._sock.settimeout(1)
                
                with users_collection.watch(pipeline) as stream:
                    while not client_disconnected:
                        # Gửi heartbeat mỗi 30 giây
                        current_time = time.time()
                        if current_time - last_heartbeat > 30:
                            yield ": heartbeat\n\n"
                            last_heartbeat = current_time
                        
                        try:
                            # Đọc change từ stream với timeout
                            change = stream.try_next()
                            if change is None:
                                # Kiểm tra client disconnection
                                try:
                                    request.environ['wsgi.input']._sock.recv(1)
                                except:
                                    handle_client_disconnect()
                                continue
                            
                            if change['operationType'] == 'update':
                                # Lấy thông tin user đầy đủ sau khi update
                                user_id = change['documentKey']['_id']
                                updated_user = users_collection.find_one({'_id': user_id}, {
                                    'user_id': 1,
                                    'is_active': 1,
                                    'username': 1,
                                    'last_activity': 1,
                                    'last_login': 1,
                                    'last_logout': 1
                                })
                                
                                if updated_user:
                                    # Lấy phiên làm việc gần nhất cho user đã cập nhật
                                    latest_session = work_time_collection.find_one(
                                        {'user_id': updated_user['user_id']},
                                        sort=[('login_time', -1)]
                                    )
                                    
                                    session_data = {
                                        'login_time': latest_session.get('login_time') if latest_session else None,
                                        'logout_time': latest_session.get('logout_time') if latest_session else None,
                                        'duration': latest_session.get('duration_str') if latest_session else None,
                                        'session_id': latest_session.get('session_id') if latest_session else None
                                    }
                                    
                                    yield f"data: {{\"type\": \"status_update\", \"user_id\": \"{updated_user['user_id']}\", \"is_active\": {str(updated_user.get('is_active', False)).lower()}, \"username\": \"{updated_user.get('username', '')}\", \"last_activity\": \"{updated_user.get('last_activity', '')}\", \"last_login\": \"{updated_user.get('last_login', '')}\", \"last_logout\": \"{updated_user.get('last_logout', '')}\", \"session\": {json.dumps(session_data)}}}\n\n"
                            
                            elif change['operationType'] == 'insert':
                                # Lấy thông tin user mới
                                user = change['fullDocument']
                                if 'user_id' in user and 'is_active' in user:
                                    # Lấy phiên làm việc gần nhất cho user mới
                                    latest_session = work_time_collection.find_one(
                                        {'user_id': user['user_id']},
                                        sort=[('login_time', -1)]
                                    )
                                    
                                    session_data = {
                                        'login_time': latest_session.get('login_time') if latest_session else None,
                                        'logout_time': latest_session.get('logout_time') if latest_session else None,
                                        'duration': latest_session.get('duration_str') if latest_session else None,
                                        'session_id': latest_session.get('session_id') if latest_session else None
                                    }
                                    
                                    yield f"data: {{\"type\": \"status_update\", \"user_id\": \"{user['user_id']}\", \"is_active\": {str(user['is_active']).lower()}, \"username\": \"{user.get('username', '')}\", \"last_activity\": \"{user.get('last_activity', '')}\", \"last_login\": \"{user.get('last_login', '')}\", \"last_logout\": \"{user.get('last_logout', '')}\", \"session\": {json.dumps(session_data)}}}\n\n"
                                    
                        except Exception as e:
                            logger.error(f"Error processing change: {str(e)}", exc_info=True)
                            continue
                                
            finally:
                client.close()
                
        except Exception as e:
            logger.error(f"Error in user_activity_stream: {str(e)}", exc_info=True)
            yield f"data: {{\"error\": \"{str(e)}\"}}\n\n"
    
    response.streaming_content = event_stream()
    return response

@login_required
@require_POST
def update_activity(request):
    """Cập nhật thời gian hoạt động cuối cùng của user"""
    try:
        # Lấy thông tin user từ MongoDB
        users_collection, client = get_collection_handle('users')
        if users_collection is None:
            return JsonResponse({
                'success': False,
                'message': 'Không thể kết nối đến cơ sở dữ liệu'
            })
            
        try:
            # Cập nhật thời gian hoạt động cuối cùng
            current_time = timezone.now().astimezone(TIMEZONE)
            result = users_collection.update_one(
                {'user_id': str(request.user.id)},
                {
                    '$set': {
                        'last_activity': current_time.isoformat(),
                        'is_active': True  # Đảm bảo is_active luôn là True khi có hoạt động
                    }
                }
            )
            
            if result.modified_count > 0:
                return JsonResponse({
                    'success': True,
                    'message': 'Cập nhật hoạt động thành công'
                })
            else:
                return JsonResponse({
                    'success': False,
                    'message': 'Không tìm thấy user'
                })
                
        finally:
            client.close()
            
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Lỗi: {str(e)}'
        })

@login_required
@role_required(['admin', 'quanly'])
def check_user_status(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            user_ids = data.get('user_ids', [])
            
            logger.info(f"check_user_status called with user_ids: {user_ids}")
            
            if not user_ids:
                logger.warning("No user_ids provided")
                return JsonResponse({
                    'success': False,
                    'message': 'Không có user_id nào được cung cấp'
                })
            
            # Lấy collection từ MongoDB
            users_collection, client = get_collection_handle('users')
            if users_collection is None:
                logger.error("Failed to connect to MongoDB users collection")
                return JsonResponse({
                    'success': False,
                    'message': 'Không thể kết nối đến cơ sở dữ liệu'
                })
            
            try:
                statuses = []
                current_time = timezone.now()
                
                for user_id in user_ids:
                    logger.info(f"Processing user_id: {user_id}")
                    
                    # Tìm user trong MongoDB
                    mongo_user = users_collection.find_one({'user_id': str(user_id)})
                    if not mongo_user:
                        logger.warning(f"User not found in MongoDB: {user_id}")
                        continue
                    
                    # Kiểm tra trong collection user_activities
                    user_activity_collection = client['user_activities']['activities']
                    latest_activity = user_activity_collection.find_one(
                        {'user_id': str(user_id)},
                        sort=[('login_time', -1)]
                    )
                    
                    logger.info(f"Latest activity for user {user_id}: {latest_activity}")
                    
                    logout_time = None
                    session_id = None
                    
                    if latest_activity:
                        session_id = latest_activity.get('session_id')
                        logger.info(f"Session ID: {session_id}")
                        
                        # Kiểm tra xem có thời gian logout không
                        if latest_activity.get('logout_time'):
                            logout_time = latest_activity['logout_time']
                            logger.info(f"Found logout time: {logout_time}")
                    
                    statuses.append({
                        'user_id': user_id,
                        'logout_time': logout_time,
                        'session_id': session_id
                    })
                
                logger.info(f"Returning statuses: {statuses}")
                return JsonResponse({
                    'success': True,
                    'statuses': statuses
                })
                
            finally:
                if client:
                    try:
                        client.close()
                    except Exception as e:
                        logger.error(f"Error closing MongoDB connection: {str(e)}")
                    
        except json.JSONDecodeError:
            logger.error("Invalid JSON data received")
            return JsonResponse({
                'success': False,
                'message': 'Dữ liệu không hợp lệ'
            })
        except Exception as e:
            logger.error(f"Error checking user status: {str(e)}", exc_info=True)
            return JsonResponse({
                'success': False,
                'message': 'Có lỗi xảy ra khi kiểm tra trạng thái'
            })
    
    return JsonResponse({
        'success': False,
        'message': 'Phương thức không được hỗ trợ'
    })

