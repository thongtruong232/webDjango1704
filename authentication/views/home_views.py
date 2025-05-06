from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .mongodb import get_collection_handle
from django.utils import timezone
import pandas as pd
from django.core.files.storage import FileSystemStorage
import os
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
from django.conf import settings
import logging
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import re
import json
from bson.objectid import ObjectId

# Định nghĩa múi giờ GMT+7
TIMEZONE = pytz.timezone('Asia/Bangkok')

logger = logging.getLogger(__name__)

def get_current_time():
    """
    Lấy thời gian hiện tại theo múi giờ Asia/Bangkok
    """
    return timezone.localtime(timezone.now(), pytz.timezone('Asia/Bangkok'))



@login_required
@role_required('admin')
def create_user(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        role = request.POST.get('role')
        
        # Kiểm tra dữ liệu đầu vào
        if not all([username, email, password, role]) or role not in ROLES:
            return JsonResponse({
                'success': False,
                'message': 'Dữ liệu không hợp lệ'
            })
            
        # Kiểm tra username và email đã tồn tại chưa
        if User.objects.filter(username=username).exists():
            return JsonResponse({
                'success': False,
                'message': 'Username đã tồn tại'
            })
            
        if User.objects.filter(email=email).exists():
            return JsonResponse({
                'success': False,
                'message': 'Email đã tồn tại'
            })
            
        try:
            # Tạo user mới trong Django
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password
            )
            
            # Lưu thông tin user trong MongoDB
            users_collection, client = get_collection_handle('users')
            mongo_user_data = {
                'user_id': str(user.id),
                'username': username,
                'email': email,
                'password': password,
                'role': role,
                'created_at': get_current_time().isoformat()
            }
            
            users_collection.update_one(
                {'user_id': str(user.id)},
                {'$set': mongo_user_data},
                upsert=True
            )
            
            client.close()
            
            return JsonResponse({
                'success': True,
                'user_id': str(user.id)
            })
            
        except Exception as e:
            logger.error(f"Error creating user: {str(e)}")
            return JsonResponse({
                'success': False,
                'message': str(e)
            })
            
    return JsonResponse({
        'success': False,
        'message': 'Phương thức không được hỗ trợ'
    })



def seconds_to_days_hours(seconds):
    """
    Chuyển đổi số giây thành số ngày và số giờ
    """
    days = seconds // (24 * 3600)
    remaining_seconds = seconds % (24 * 3600)
    hours = remaining_seconds // 3600
    return days, hours
@login_required
def home_view(request):
    # Get user data from MongoDB
    users_collection, client = get_collection_handle('users')
    if users_collection is None or client is None:
        messages.error(request, 'Không thể kết nối đến cơ sở dữ liệu')
        return render(request, 'authentication/home.html', {
            'user_data': None,
            'excel_data': [],
            'can_import': False,
            'can_update_status': False,
            'allowed_status_updates': [],
            'is_nhanvien': False,
            'current_page': 1,
            'total_pages': 1,
            'has_more': False,
            'page_range': [1],
            'start_index': 0,
            'name': request.user.username
        })
        
    try:
        # Lấy user data một lần và sử dụng lại
        user_data = users_collection.find_one({'user_id': str(request.user.id)})
        if not user_data:
            messages.error(request, 'Không tìm thấy thông tin người dùng')
            return redirect('login')
            
        user_role = user_data.get('role', 'nhanvien')
        
        # Nếu là nhân viên, chuyển hướng về trang verified
        if user_role == 'nhanvien':
            print('Chuyển hướng về trang verified với role:', user_role)
            return redirect('employee_verified')
        
        # Handle Excel file upload
        if request.method == 'POST' and request.FILES.get('excel_file'):
            if not can_manage_users(request.user.id):
                messages.error(request, 'Bạn không có quyền import dữ liệu')
                return redirect('home')
                
            excel_file = request.FILES['excel_file']
            
            # Save the uploaded file temporarily
            fs = FileSystemStorage()
            filename = fs.save(excel_file.name, excel_file)
            file_path = fs.path(filename)
            
            try:
                # Read Excel file
                df = pd.read_excel(file_path)

                # Get Excel data collection
                excel_data_collection, excel_client = get_collection_handle('employee_textnow')
                if excel_data_collection is None:
                    messages.error(request, 'Không thể kết nối đến cơ sở dữ liệu')
                    return redirect('home')

                # Process and save data
                records = []
                for index, row in df.iterrows():

                    email, password, refresh_token, client_id = parse_excel_data(row['Mail'])

                    record = {
                        'stt': index + 1,
                        'Email': email,
                        'Pass': password,
                        'PassFree': str(row['PassFree']) if pd.notna(row['PassFree']) else 'Chưa cập nhật',
                        'PassTexNow': str(row['PassTextNow']) if pd.notna(row['PassTextNow']) else 'Chưa cập nhật',
                        'status': str(row['Trạng thái']) if pd.notna(row['Trạng thái']) else 'Chưa rõ',
                        'imported_at': get_current_time().isoformat(),
                        'imported_by': str(request.user.id),
                        'imported_by_username': request.user.username,
                        'time': str(row['Time']) if pd.notna(row['Time']) else 'Chưa rõ',
                        'all_info_mail': row['Mail']
                    }
                    records.append(record)


                # Insert records in bulk
                if records:
                    excel_data_collection.insert_many(records)
                    # Không thêm message từ server, để client xử lý
                    success_message = f'Đã import thành công {len(records)} email'
                    return JsonResponse({
                        'success': True,
                        'message': success_message
                    })

                excel_client.close()
                
            except Exception as e:
                messages.error(request, f'Lỗi khi import dữ liệu: {str(e)}')
            finally:
                # Clean up temporary file
                if os.path.exists(file_path):
                    os.remove(file_path)
                
            return redirect('home')
            
        # Get Excel data based on user role
        excel_data_collection, excel_client = get_collection_handle('employee_textnow')
        if excel_data_collection is None:
            messages.error(request, 'Không thể kết nối đến cơ sở dữ liệu')
            return render(request, 'authentication/home.html', {
                'user_data': user_data,
                'excel_data': [],
                'can_import': False,
                'can_update_status': False,
                'allowed_status_updates': [],
                'is_nhanvien': user_role == 'nhanvien',
                'current_page': 1,
                'total_pages': 1,
                'has_more': False,
                'page_range': [1],
                'start_index': 0
            })
            
        # Get pagination parameters
        page = int(request.GET.get('page', 1))
        
        # Điều chỉnh số lượng bản ghi hiển thị dựa trên role
        if user_role in ['admin', 'quanly']:
            per_page = 50  # Hiển thị nhiều hơn cho admin và quanly
        else:
            per_page = 10  # Giữ nguyên cho các role khác
            
        skip = (page - 1) * per_page
        
        # Get total count
        total_records = excel_data_collection.count_documents({})
        total_pages = (total_records + per_page - 1) // per_page
        
        # Get records based on role
        cursor = excel_data_collection.find().sort('imported_at', -1).skip(skip).limit(per_page)
        
        # Convert cursor to list and add mongo_id
        excel_data = []
        for record in cursor:
            # Thêm mongo_id vào record
            record['mongo_id'] = str(record.get('_id'))
            # Đảm bảo có trường status
            if 'status' not in record:
                record['status'] = 'Chưa sử dụng'
            # Thêm thông tin thời gian
            if 'created_at' in record:
                try:
                    raw_time = record['created_at']
                    
                    # Xử lý trường hợp raw_time là string
                    if isinstance(raw_time, str):
                        try:
                            # Thử parse string thành datetime
                            imported_time = datetime.fromisoformat(raw_time)
                        except ValueError:
                            logger.error(f"Invalid datetime string format: {raw_time}")
                            record['time_info'] = None
                            continue
                    else:
                        imported_time = raw_time
                    
                    # Đảm bảo imported_time là aware datetime
                    if not timezone.is_aware(imported_time):
                        imported_time = timezone.make_aware(imported_time, timezone.get_default_timezone())
                    
                    current_time = get_current_time()
                    time_diff = current_time - imported_time
                    total_seconds = int(time_diff.total_seconds())

                    days, hours = seconds_to_days_hours(total_seconds)

                    if total_seconds < 0:
                        # Thời gian còn lại
                        record['time_info'] = {
                            'type': 'remaining',
                            'days': abs(days),
                            'hours': abs(hours),
                        }
                    else:
                        # Thời gian đã trôi qua
                        record['time_info'] = {
                            'type': 'elapsed',
                            'days': days,
                            'hours': hours,
                        }

                except Exception as e:
                    logger.error(f"Error processing time info: {str(e)}")
                    record['time_info'] = None
            else:
                record['time_info'] = None
                
            excel_data.append(record)
        
        excel_client.close()
        
        # Get allowed status updates
        allowed_status_updates = get_allowed_status_updates(request.user.id)
        
        # Calculate pagination info
        has_more = page < total_pages
        page_range = range(max(1, page - 2), min(total_pages + 1, page + 3))
        start_index = skip + 1
        
        logger.info(f"Retrieved {len(excel_data)} records for page {page}, total records: {total_records}")
        
        return render(request, 'authentication/home.html', {
            'user_data': user_data,
            'excel_data': excel_data,
            'can_import': can_manage_users(request.user.id),
            'can_update_status': can_update_status(request.user.id),
            'allowed_status_updates': allowed_status_updates,
            'is_nhanvien': user_role == 'nhanvien',
            'current_page': page,
            'total_pages': total_pages,
            'has_more': has_more,
            'page_range': page_range,
            'start_index': start_index
        })
        
    except Exception as e:
        logger.error(f"Error in home_view: {str(e)}")
        messages.error(request, 'Có lỗi xảy ra khi tải dữ liệu')
        return render(request, 'authentication/home.html', {
            'user_data': None,
            'excel_data': [],
            'can_import': False,
            'can_update_status': False,
            'allowed_status_updates': [],
            'is_nhanvien': False,
            'current_page': 1,
            'total_pages': 1,
            'has_more': False,
            'page_range': [1],
            'start_index': 0
        })
    finally:
        if client is not None:
            client.close()

# Chuyển đổi dữ liệu excel thành dạng email, password, refresh_token, client_id
def parse_excel_data(text):
    match = re.match(r'^([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)$', text)
    if match:
        email = match.group(1)
        password = match.group(2)
        refresh_token = match.group(3)
        client_id = match.group(4)
        return email, password, refresh_token, client_id
    else:
        print("Không đúng định dạng!")


def sync_user_data(user_id):
    """
    Đồng bộ dữ liệu xác thực từ MongoDB sang Django
    Chỉ cập nhật username và email cho mục đích xác thực
    """
    try:
        # Lấy collection từ MongoDB
        users_collection, client = get_collection_handle('users')
        if users_collection is None:
            print("Cannot connect to MongoDB")
            return False
            
        # Lấy dữ liệu từ MongoDB
        mongo_user = users_collection.find_one({'user_id': str(user_id)})
        if not mongo_user:
            print(f"User {user_id} not found in MongoDB")
            return False
            
        try:
            # Lấy hoặc tạo user trong Django
            user, created = User.objects.get_or_create(id=user_id)
            
            # Chỉ cập nhật username và email cho mục đích xác thực
            user.username = mongo_user.get('username', user.username)
            user.email = mongo_user.get('email', user.email)
            user.save()
            
            return True
        except Exception as e:
            print(f"Error updating Django user: {str(e)}")
            return False
        finally:
            client.close()
            
    except Exception as e:
        print(f"Error in sync_user_data: {str(e)}")
        return False


@login_required
@role_required(['admin', 'quanly'])
def export_emails(request):
    # Lấy thông tin ngày xử lý từ request
    process_date = request.GET.get('process_date')
    
    # Lấy danh sách trạng thái được chọn
    selected_statuses = request.GET.getlist('status')
    
    # Nếu không có trạng thái nào được chọn, xuất tất cả
    excel_data_collection, client = get_collection_handle('employee_textnow')
    
    # Tạo query dựa trên trạng thái được chọn và ngày
    query = {}
    
    # Thêm điều kiện ngày xử lý nếu có
    if process_date:
        # Tạo khoảng thời gian cho ngày được chọn (từ 00:00:00 đến 23:59:59)
        start_time = f"{process_date}T00:00:00Z"
        end_time = f"{process_date}T23:59:59Z"
        
        # Tìm các bản ghi được xử lý trong ngày (dựa vào thời gian cập nhật)
        query['updated_at'] = {
            '$gte': start_time,
            '$lte': end_time
        }
    
    if selected_statuses:
        query['status'] = {'$in': selected_statuses}
    
    # Lấy dữ liệu từ MongoDB
    cursor = excel_data_collection.find(query).sort('stt', 1)
    
    # Tạo file Excel trong bộ nhớ
    output = BytesIO()
    workbook = xlsxwriter.Workbook(output, {'nan_inf_to_errors': True})
    worksheet = workbook.add_worksheet()
    
    # Định dạng cho header
    header_format = workbook.add_format({
        'bold': True,
        'bg_color': '#f8f9fa',
        'border': 1
    })
    
    # Viết header
    headers = [
        'STT', 'Email', 'Pass', 'PassFree', 'PassTexNow', 'Trạng thái', 
        'Ngày import', 'Người import', 'Nhân viên xử lý', 'Thời gian xử lý',
        'Kiểm tra viên', 'Thời gian kiểm tra'
    ]
    
    for col, header in enumerate(headers):
        worksheet.write(0, col, header, header_format)
    
    # Định dạng cho các ô dữ liệu
    cell_format = workbook.add_format({
        'border': 1
    })
    
    # Viết dữ liệu
    for row, record in enumerate(cursor, start=1):
        # Chuyển đổi thời gian từ ISO format sang múi giờ GMT+7
        imported_at = record.get('imported_at', '')
        nhanvien_time = record.get('nhanvien_assigned_at', '')
        kiemtra_time = record.get('kiemtra_assigned_at', '')

        if imported_at:
            imported_at = timezone.datetime.fromisoformat(imported_at).astimezone(TIMEZONE)
            imported_at = imported_at.strftime('%Y-%m-%d %H:%M:%S')
        
        if nhanvien_time:
            nhanvien_time = timezone.datetime.fromisoformat(nhanvien_time).astimezone(TIMEZONE)
            nhanvien_time = nhanvien_time.strftime('%Y-%m-%d %H:%M:%S')
            
        if kiemtra_time:
            kiemtra_time = timezone.datetime.fromisoformat(kiemtra_time).astimezone(TIMEZONE)
            kiemtra_time = kiemtra_time.strftime('%Y-%m-%d %H:%M:%S')

        data = [
            record.get('stt', ''),
            record.get('Email', ''),
            record.get('Pass', ''),
            record.get('PassFree', ''),
            record.get('PassTexNow', ''),
            record.get('status', ''),
            imported_at,
            record.get('imported_by', ''),
            record.get('nhanvien_assigned_to', ''),
            nhanvien_time,
            record.get('kiemtra_assigned_to', ''),
            kiemtra_time
        ]
        for col, value in enumerate(data):
            worksheet.write(row, col, value, cell_format)
    
    # Điều chỉnh độ rộng cột
    column_widths = [8, 30, 15, 15, 15, 15, 15, 20, 20, 20, 20, 20]
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
    response['Content-Disposition'] = 'attachment; filename=danh_sach_email.xlsx'
    
    client.close()
    return response

@login_required
@role_required(['admin', 'quanly'])
def work_management(request):
    # Lấy thông tin filter từ request
    stats_type = request.GET.get('stats_type', 'day')
    end_date = request.GET.get('end_date')
    start_date = request.GET.get('start_date')
     # Get user data from MongoDB
    users_collection, _ = get_collection_handle('users')
    user_data = users_collection.find_one({'user_id': str(request.user.id)})
    # Nếu không có ngày được chọn, mặc định lấy 7 ngày gần nhất
    if not end_date:
        end_date = datetime.now().date()
    else:
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    if not start_date:
        start_date = end_date - timedelta(days=6)
    else:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()

    # Chuyển đổi ngày thành ISO format cho MongoDB
    start_date_iso = datetime.combine(start_date, datetime.min.time()).astimezone(TIMEZONE).isoformat()
    end_date_iso = datetime.combine(end_date, datetime.max.time()).astimezone(TIMEZONE).isoformat()

    # Lấy collection từ MongoDB
    excel_data_collection, client = get_collection_handle('employee_textnow')

    # Query thống kê cho nhân viên đăng ký
    nhanvien_pipeline = [
        {
            '$match': {
                'status': 'Đã đăng ký',
                'nhanvien_assigned_at': {
                    '$gte': start_date_iso,
                    '$lte': end_date_iso
                }
            }
        },
        {
            '$group': {
                '_id': '$nhanvien_assigned_to',
                'count': {'$sum': 1}
            }
        }
    ]

    # Query thống kê cho kiểm tra viên
    kiemtra_pipeline = [
        {
            '$match': {
                'status': 'Đã kiểm tra',
                'kiemtra_assigned_at': {
                    '$gte': start_date_iso,
                    '$lte': end_date_iso
                }
            }
        },
        {
            '$group': {
                '_id': '$kiemtra_assigned_to',
                'count': {'$sum': 1}
            }
        }
    ]

    # Thực hiện aggregation
    nhanvien_stats = list(excel_data_collection.aggregate(nhanvien_pipeline))
    kiemtra_stats = list(excel_data_collection.aggregate(kiemtra_pipeline))

    # Xử lý kết quả thống kê
    nhanvien_total = sum(stat['count'] for stat in nhanvien_stats)
    kiemtra_total = sum(stat['count'] for stat in kiemtra_stats)

    # Format dữ liệu thống kê nhân viên
    nhanvien_stats = [
        {
            'username': stat['_id'],
            'count': stat['count'],
            'percentage': round((stat['count'] / nhanvien_total * 100) if nhanvien_total > 0 else 0, 1)
        }
        for stat in nhanvien_stats if stat['_id']
    ]

    # Format dữ liệu thống kê kiểm tra viên
    kiemtra_stats = [
        {
            'username': stat['_id'],
            'count': stat['count'],
            'percentage': round((stat['count'] / kiemtra_total * 100) if kiemtra_total > 0 else 0, 1)
        }
        for stat in kiemtra_stats if stat['_id']
    ]

    # Pipeline cho biểu đồ theo thời gian
    if stats_type == 'week':
        # Thống kê theo tuần
        time_group_stage = {
            '$week': {
                '$dateFromString': {
                    'dateString': '$nhanvien_assigned_at'
                }
            }
        }
        time_format = lambda x: f"Tuần {x}"
    else:
        # Thống kê theo ngày
        time_group_stage = {
            '$dateToString': {
                'format': '%Y-%m-%d',
                'date': {
                    '$dateFromString': {
                        'dateString': '$nhanvien_assigned_at'
                    }
                }
            }
        }
        time_format = lambda x: datetime.strptime(x, '%Y-%m-%d').strftime('%d/%m/%Y')

    # Pipeline cho thống kê theo thời gian - nhân viên
    nhanvien_time_pipeline = [
        {
            '$match': {
                'status': 'Đã đăng ký',
                'nhanvien_assigned_at': {
                    '$gte': start_date_iso,
                    '$lte': end_date_iso
                }
            }
        },
        {
            '$group': {
                '_id': time_group_stage,
                'count': {'$sum': 1}
            }
        },
        {'$sort': {'_id': 1}}
    ]

    # Pipeline cho thống kê theo thời gian - kiểm tra viên
    kiemtra_time_pipeline = [
        {
            '$match': {
                'status': 'Đã kiểm tra',
                'kiemtra_assigned_at': {
                    '$gte': start_date_iso,
                    '$lte': end_date_iso
                }
            }
        },
        {
            '$group': {
                '_id': time_group_stage,
                'count': {'$sum': 1}
            }
        },
        {'$sort': {'_id': 1}}
    ]

    # Thực hiện aggregation cho dữ liệu biểu đồ
    nhanvien_time_stats = list(excel_data_collection.aggregate(nhanvien_time_pipeline))
    kiemtra_time_stats = list(excel_data_collection.aggregate(kiemtra_time_pipeline))

    # Format dữ liệu cho biểu đồ
    chart_labels = [time_format(str(stat['_id'])) for stat in nhanvien_time_stats]
    nhanvien_data = [stat['count'] for stat in nhanvien_time_stats]
    kiemtra_data = [stat['count'] for stat in kiemtra_time_stats]

    client.close()

    context = {
        'user_data': user_data,
        'stats_type': stats_type,
        'start_date': start_date,
        'end_date': end_date,
        'nhanvien_stats': nhanvien_stats,
        'kiemtra_stats': kiemtra_stats,
        'chart_labels': chart_labels,
        'nhanvien_data': nhanvien_data,
        'kiemtra_data': kiemtra_data,
    }

    return render(request, 'authentication/work_management.html', context)



@login_required
@role_required('admin')
def check_username(request):
    if request.method == 'POST':
        username = request.POST.get('username_register')
        
        if not username:
            return JsonResponse({
                'success': False,
                'exists': False,
                'message': 'Username không được để trống'
            })
            
        try:
            # Kiểm tra username trong MongoDB
            users_collection, client = get_collection_handle('users')
            if users_collection is None:
                return JsonResponse({
                    'success': False,
                    'exists': False,
                    'message': 'Không thể kết nối đến cơ sở dữ liệu'
                })
                
            try:
                exists = users_collection.find_one({'username': username}) is not None
                return JsonResponse({
                    'success': True,
                    'exists': exists
                })
            finally:
                client.close()
                
        except Exception as e:
            return JsonResponse({
                'success': False,
                'exists': False,
                'message': str(e)
            })
            
    return JsonResponse({
        'success': False,
        'exists': False,
        'message': 'Phương thức không được hỗ trợ'
    })





@login_required
@require_POST
def handle_browser_close(request):
    """Xử lý sự kiện đóng browser"""
    try:
        if request.user.is_authenticated:
            current_time = timezone.now().astimezone(TIMEZONE)
            session_id = request.session.get('activity_session_id')
            
            # Kết nối MongoDB
            work_time_collection, client = get_collection_handle('work_time')
            if client:
                try:
                    # Cập nhật trạng thái trong work_time collection
                    work_time_collection.update_one(
                        {
                            'user_id': str(request.user.id),
                            'session_id': session_id,
                            'logout_time': {'$exists': False}
                        },
                        {
                            '$set': {
                                'logout_time': current_time.isoformat(),
                                'is_active': False,
                                'updated_at': current_time.isoformat()
                            }
                        }
                    )
                    
                    # Cập nhật trạng thái trong users collection
                    users_collection = client['users']['users']
                    users_collection.update_one(
                        {'user_id': str(request.user.id)},
                        {
                            '$set': {
                                'is_active': False,
                                'last_activity': current_time.isoformat(),
                                'last_logout': current_time.isoformat()
                            }
                        }
                    )
                    
                    # Gửi thông báo WebSocket
                    try:
                        channel_layer = get_channel_layer()
                        if channel_layer is not None:
                            async_to_sync(channel_layer.group_send)(
                                "user_activity",
                                {
                                    'type': 'activity_status',
                                    'user_id': str(request.user.id),
                                    'is_active': False,
                                    'session_id': session_id,
                                    'last_activity': current_time.strftime('%Y-%m-%d %H:%M:%S')
                                }
                            )
                    except Exception as e:
                        logger.error(f"Error sending WebSocket notification: {str(e)}")
                        
                finally:
                    client.close()
            
            return JsonResponse({'success': True})
            
    except Exception as e:
        logger.error(f"Error in handle_browser_close: {str(e)}")
        return JsonResponse({'success': False, 'message': str(e)})
    
    return JsonResponse({'success': False, 'message': 'User not authenticated'})

@login_required
def update_checkbox_status(request):
    if request.method == 'POST':
        try:
            logger.info("Received checkbox status update request")
            data = json.loads(request.body)
            record_id = data.get('record_id')
            status = data.get('status')
            is_checked = data.get('is_checked')
            
            logger.info(f"Request data: record_id={record_id}, status={status}, is_checked={is_checked}")
            
            if not record_id or status is None or is_checked is None:
                logger.error("Missing required data in request")
                return JsonResponse({
                    'success': False,
                    'message': 'Thiếu thông tin cần thiết'
                })
            
            # Kiểm tra quyền cập nhật trạng thái
            if not can_update_status(request.user.id):
                logger.warning(f"User {request.user.id} does not have permission to update status")
                return JsonResponse({
                    'success': False,
                    'message': 'Bạn không có quyền cập nhật trạng thái'
                })
            
            # Kết nối MongoDB
            excel_data_collection, client = get_collection_handle('employee_textnow')
            if excel_data_collection is None:
                logger.error("Failed to connect to MongoDB")
                return JsonResponse({
                    'success': False,
                    'message': 'Không thể kết nối đến cơ sở dữ liệu'
                })
            
            try:
                # Chuyển đổi record_id thành ObjectId
                try:
                    object_id = ObjectId(record_id)
                    logger.info(f"Converted record_id to ObjectId: {object_id}")
                except Exception as e:
                    logger.error(f"Invalid ObjectId format: {record_id}, error: {str(e)}")
                    return JsonResponse({
                        'success': False,
                        'message': 'ID không hợp lệ'
                    })
                
                # Cập nhật trạng thái trong MongoDB
                update_data = {
                    'status': status,
                    'updated_by': request.user.username,
                    'updated_at': get_current_time().isoformat()
                }
                
                logger.info(f"Updating record {object_id} with data: {update_data}")
                
                result = excel_data_collection.update_one(
                    {'_id': object_id},
                    {'$set': update_data}
                )
                
                logger.info(f"Update result: matched={result.matched_count}, modified={result.modified_count}")
                
                if result.modified_count > 0:
                    logger.info(f"Successfully updated status for record {object_id}")
                    return JsonResponse({
                        'success': True,
                        'message': 'Cập nhật trạng thái thành công',
                        'new_status': status
                    })
                else:
                    # Thử tìm bản ghi để kiểm tra
                    record = excel_data_collection.find_one({'_id': object_id})
                    if not record:
                        logger.error(f"Record not found: {object_id}")
                        return JsonResponse({
                            'success': False,
                            'message': 'Không tìm thấy bản ghi'
                        })
                    else:
                        logger.warning(f"Record exists but not modified: {object_id}")
                        return JsonResponse({
                            'success': False,
                            'message': 'Không thể cập nhật trạng thái'
                        })
                    
            except Exception as e:
                logger.error(f"Error updating status: {str(e)}")
                return JsonResponse({
                    'success': False,
                    'message': f'Lỗi khi cập nhật trạng thái: {str(e)}'
                })
            finally:
                if client:
                    client.close()
                    
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON data: {str(e)}")
            return JsonResponse({
                'success': False,
                'message': 'Dữ liệu không hợp lệ'
            })
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            return JsonResponse({
                'success': False,
                'message': f'Lỗi: {str(e)}'
            })
    
    logger.warning("Invalid request method")
    return JsonResponse({
        'success': False,
        'message': 'Phương thức không được hỗ trợ'
    })

