from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .mongodb import get_collection_handle
from bson.objectid import ObjectId
from django.utils import timezone
import pandas as pd
from django.core.files.storage import FileSystemStorage
import os
from django.views.decorators.http import require_POST
from .permissions import (
    role_required, can_manage_users, can_update_status, 
    ROLES, get_allowed_status_updates
)
from .models import User, UserActivity
import xlsxwriter
from io import BytesIO
import pytz
from datetime import datetime, timedelta
from django.db.models import Count
from django.db.models.functions import TruncDate, ExtractWeek

# Định nghĩa múi giờ GMT+7
TIMEZONE = pytz.timezone('Asia/Bangkok')

def get_current_time():
    """Lấy thời gian hiện tại theo múi giờ GMT+7"""
    return timezone.now().astimezone(TIMEZONE)

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            
            # Ghi lại thời gian login
            UserActivity.objects.create(
                user=user,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT')
            )
            
            return redirect('home')
        else:
            messages.error(request, 'Tên đăng nhập hoặc mật khẩu không đúng')
    
    return render(request, 'authentication/login.html')

def check_and_delete_expired_emails():
    """Kiểm tra và xóa các email hết hạn (3600 giây không thay đổi trạng thái)"""
    excel_data_collection, client = get_collection_handle('excel_data')
    
    # Tính thời điểm 1 giờ trước
    expiration_time = get_current_time() - timedelta(seconds=3600)
    
    # Tìm và xóa các email đã hết hạn
    result = excel_data_collection.delete_many({
        'status': 'Chưa sử dụng',
        'imported_at': {
            '$lt': expiration_time.isoformat()
        }
    })
    
    client.close()
    return result.deleted_count

@login_required
def home_view(request):
    # Kiểm tra và xóa email hết hạn trước khi hiển thị trang
    deleted_count = check_and_delete_expired_emails()
    if deleted_count > 0:
        messages.warning(request, f'Đã xóa {deleted_count} email hết hạn (không sử dụng trong 1 giờ)')
    
    # Get user data from MongoDB
    users_collection, client = get_collection_handle('users')
    user_data = users_collection.find_one({'user_id': str(request.user.id)})
    user_role = user_data.get('role', 'nhanvien') if user_data else 'nhanvien'
    
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
            
            # Validate columns
            if 'Email' not in df.columns or 'Pass' not in df.columns or 'PassFree' not in df.columns or 'PassTexNow' not in df.columns:
                messages.error(request, 'Excel file must contain Email, Pass, PassFree, and PassTexNow columns')
            else:
                # Get MongoDB collection
                excel_data_collection, _ = get_collection_handle('excel_data')
                
                # Lấy số thứ tự lớn nhất hiện tại
                last_record = excel_data_collection.find_one(
                    {},
                    sort=[('stt', -1)]
                )
                next_stt = (last_record.get('stt', 0) if last_record else 0) + 1
                
                # Convert DataFrame to list of dictionaries
                records = df.to_dict('records')
                new_records = []
                duplicate_emails = []
                
                # Check for duplicates
                for record in records:
                    # Check if email already exists in database
                    existing_record = excel_data_collection.find_one({'Email': record['Email']})
                    
                    if existing_record:
                        duplicate_emails.append(record['Email'])
                    else:
                        record['status'] = 'Chưa sử dụng'
                        record['imported_at'] = get_current_time().isoformat()
                        record['imported_by'] = str(request.user.id)
                        record['assigned_to'] = None
                        record['assigned_to_kiemtra'] = None
                        record['stt'] = next_stt
                        new_records.append(record)
                        next_stt += 1
                
                if new_records:
                    # Insert only non-duplicate records
                    excel_data_collection.insert_many(new_records)
                    success_message = f'Imported {len(new_records)} records successfully.'
                    if duplicate_emails:
                        success_message += f' Skipped {len(duplicate_emails)} duplicate emails.'
                    messages.success(request, success_message)
                else:
                    messages.warning(request, 'All emails already exist in database. No new records imported.')
                
                if duplicate_emails:
                    messages.warning(request, f'Duplicate emails: {", ".join(duplicate_emails)}')
        
        except Exception as e:
            messages.error(request, f'Error importing data: {str(e)}')
        
        finally:
            # Clean up the temporary file
            if os.path.exists(file_path):
                os.remove(file_path)
    
    # Fetch Excel data based on user role
    excel_data_collection, _ = get_collection_handle('excel_data')
    
    # Xử lý phân trang
    page = int(request.GET.get('page', 1))
    per_page = 10
    skip = (page - 1) * per_page
    
    # Nếu là nhân viên, chỉ hiển thị email chưa sử dụng và chưa được gán
    if user_role == 'nhanvien':
        # Đếm tổng số records chưa được gán và có trạng thái "Chưa sử dụng"
        total_records = excel_data_collection.count_documents({
            'status': 'Chưa sử dụng',
            'assigned_to': None
        })
        
        # Lấy danh sách email và gán cho nhân viên này
        cursor = excel_data_collection.find({
            'status': 'Chưa sử dụng',
            'assigned_to': None
        }).sort('imported_at', -1).skip(skip).limit(per_page)
        
        # Cập nhật assigned_to cho các email được hiển thị
        email_ids = []
        for doc in cursor:
            email_ids.append(doc['_id'])
        
        if email_ids:
            excel_data_collection.update_many(
                {'_id': {'$in': email_ids}},
                {'$set': {
                    'assigned_to': str(request.user.id),
                    'nhanvien_assigned_to': request.user.username,
                    'nhanvien_assigned_at': get_current_time().isoformat()
                }}
            )
        
        # Lấy lại cursor sau khi đã gán
        cursor = excel_data_collection.find({
            '$or': [
                {'assigned_to': str(request.user.id), 'status': 'Chưa sử dụng'},
                {'_id': {'$in': email_ids}}
            ]
        }).sort('imported_at', -1)
    elif user_role == 'kiemtra':
        # Chỉ hiển thị email có trạng thái "Đã đăng ký" và chưa được gán hoặc đã gán cho user kiemtra này
        total_records = excel_data_collection.count_documents({
            'status': 'Đã đăng ký',
            '$or': [
                {'assigned_to_kiemtra': None},
                {'assigned_to_kiemtra': str(request.user.id)}
            ]
        })
        
        # Lấy danh sách email và gán cho kiemtra này
        cursor = excel_data_collection.find({
            'status': 'Đã đăng ký',
            '$or': [
                {'assigned_to_kiemtra': None},
                {'assigned_to_kiemtra': str(request.user.id)}
            ]
        }).sort('imported_at', -1).skip(skip).limit(per_page)
        
        # Cập nhật assigned_to_kiemtra cho các email được hiển thị
        email_ids = []
        for doc in cursor:
            email_ids.append(doc['_id'])
        
        if email_ids:
            excel_data_collection.update_many(
                {
                    '_id': {'$in': email_ids},
                    'assigned_to_kiemtra': None
                },
                {'$set': {
                    'assigned_to_kiemtra': str(request.user.id),
                    'kiemtra_assigned_to': request.user.username,
                    'kiemtra_assigned_at': get_current_time().isoformat()
                }}
            )
        
        # Lấy lại cursor sau khi đã gán
        cursor = excel_data_collection.find({
            '_id': {'$in': email_ids}
        }).sort('imported_at', -1)
    else:
        # Hiển thị tất cả email cho admin
        total_records = excel_data_collection.count_documents({})
        cursor = excel_data_collection.find().sort('imported_at', -1).skip(skip).limit(per_page)
    
    # Convert MongoDB cursor to list and process _id
    excel_data = []
    current_time = get_current_time()
    for doc in cursor:
        # Create a new dict without _id
        processed_doc = {k: v for k, v in doc.items() if not k.startswith('_')}
        # Add id field
        processed_doc['id'] = str(doc['_id'])
        
        # Tính thời gian cho email
        if doc.get('imported_at'):
            imported_time = timezone.datetime.fromisoformat(doc['imported_at'])
            time_diff = current_time - imported_time.astimezone(TIMEZONE)
            
            if user_role == 'kiemtra':
                # Với user kiemtra: tính thời gian tăng dần từ lúc import
                elapsed_seconds = int(time_diff.total_seconds())
                elapsed_minutes = int(elapsed_seconds // 60)
                elapsed_secs = int(elapsed_seconds % 60)
                
                processed_doc['time_info'] = {
                    'minutes': elapsed_minutes,
                    'seconds': elapsed_secs,
                    'total_seconds': elapsed_seconds,
                    'type': 'elapsed'  # Đánh dấu là thời gian tăng dần
                }
            elif doc.get('status') == 'Chưa sử dụng':
                # Với các user khác: tính thời gian đếm ngược nếu trạng thái là "Chưa sử dụng"
                remaining_seconds = max(3600 - time_diff.total_seconds(), 0)
                remaining_minutes = int(remaining_seconds // 60)
                remaining_secs = int(remaining_seconds % 60)
                
                processed_doc['time_info'] = {
                    'minutes': remaining_minutes,
                    'seconds': remaining_secs,
                    'total_seconds': int(remaining_seconds),
                    'type': 'remaining'  # Đánh dấu là thời gian đếm ngược
                }
            else:
                processed_doc['time_info'] = None
        else:
            processed_doc['time_info'] = None
            
        excel_data.append(processed_doc)
    
    client.close()
    
    # Tính toán phạm vi trang hiển thị
    total_pages = (total_records + per_page - 1) // per_page
    page_range = []
    
    if total_pages <= 5:
        page_range = range(1, total_pages + 1)
    else:
        if page <= 3:
            page_range = range(1, 6)
        elif page >= total_pages - 2:
            page_range = range(total_pages - 4, total_pages + 1)
        else:
            page_range = range(page - 2, page + 3)
    
    context = {
        'user_data': user_data,
        'excel_data': excel_data,
        'can_import': can_manage_users(request.user.id),
        'can_update_status': can_update_status(request.user.id),
        'allowed_status_updates': get_allowed_status_updates(request.user.id),
        'is_nhanvien': user_role == 'nhanvien',
        'current_page': page,
        'total_pages': total_pages,
        'has_more': (page * per_page) < total_records if user_role == 'nhanvien' else (
            (page * per_page) < total_records if user_role == 'kiemtra' else False
        ),
        'page_range': page_range,
        'start_index': (page - 1) * per_page
    }
    return render(request, 'authentication/home.html', context)

@login_required
@role_required('admin')
def manage_users(request):
    users_collection, client = get_collection_handle('users')
    users = list(users_collection.find())
    client.close()
    
    context = {
        'users': users,
        'roles': ROLES.keys()
    }
    return render(request, 'authentication/manage_users.html', context)

@login_required
@role_required('admin')
def update_user_role(request):
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        new_role = request.POST.get('role')
        
        if not user_id or not new_role or new_role not in ROLES:
            return JsonResponse({'success': False, 'message': 'Invalid parameters'})
        
        users_collection, client = get_collection_handle('users')
        result = users_collection.update_one(
            {'user_id': user_id},
            {'$set': {'role': new_role}}
        )
        client.close()
        
        if result.modified_count > 0:
            return JsonResponse({'success': True})
        return JsonResponse({'success': False, 'message': 'User not found'})
    
    return JsonResponse({'success': False, 'message': 'Invalid request method'})

def logout_view(request):
    if request.user.is_authenticated:
        # Cập nhật thời gian logout cho session gần nhất
        try:
            last_activity = UserActivity.objects.filter(
                user=request.user,
                logout_time__isnull=True
            ).latest('login_time')
            
            last_activity.logout_time = timezone.now()
            last_activity.calculate_duration()
            last_activity.save()
        except UserActivity.DoesNotExist:
            pass
    
    logout(request)
    return redirect('login')

@login_required
@require_POST
def update_status(request):
    try:
        if not can_update_status(request.user.id):
            return JsonResponse({
                'success': False,
                'message': 'Bạn không có quyền cập nhật trạng thái'
            })
            
        record_id = request.POST.get('record_id')
        new_status = request.POST.get('status')
        
        if not record_id or not new_status:
            return JsonResponse({'success': False, 'message': 'Missing required parameters'})
            
        # Check if user is allowed to set this status
        allowed_status_updates = get_allowed_status_updates(request.user.id)
        if new_status not in allowed_status_updates:
            return JsonResponse({
                'success': False,
                'message': 'Bạn không có quyền cập nhật trạng thái này'
            })
            
        # Get MongoDB collection
        excel_data_collection, client = get_collection_handle('excel_data')
        
        # Get user role
        users_collection, _ = get_collection_handle('users')
        user_data = users_collection.find_one({'user_id': str(request.user.id)})
        user_role = user_data.get('role', 'nhanvien') if user_data else 'nhanvien'

        # Prepare update data based on user role
        update_data = {
            'status': new_status,
            'updated_at': get_current_time().isoformat(),
            'updated_by': str(request.user.id),
            'updated_by_username': request.user.username
        }

        # Add role-specific timestamps
        if user_role == 'nhanvien':
            update_data.update({
                'nhanvien_assigned_to': request.user.username,
                'nhanvien_assigned_at': get_current_time().isoformat()
            })
        elif user_role == 'kiemtra':
            update_data.update({
                'kiemtra_assigned_to': request.user.username,
                'kiemtra_assigned_at': get_current_time().isoformat()
            })

        # Update the record
        result = excel_data_collection.update_one(
            {'_id': ObjectId(record_id)},
            {'$set': update_data}
        )
        
        client.close()
        
        if result.modified_count > 0:
            return JsonResponse({
                'success': True,
                'message': 'Status updated successfully',
                'new_status': new_status
            })
        else:
            return JsonResponse({
                'success': False,
                'message': 'Record not found'
            })
            
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        })

def create_sample_users(request):
    if not request.user.is_authenticated or not request.user.is_superuser:
        messages.error(request, 'Bạn không có quyền tạo user mẫu')
        return redirect('home')
        
    users_collection, client = get_collection_handle('users')
    
    # Define sample users
    sample_users = [
        {
            'username': 'admin_user',
            'password': 'Admin@123',
            'email': 'admin@example.com',
            'role': 'admin'
        },
        {
            'username': 'quanly_user',
            'password': 'Quanly@123',
            'email': 'quanly@example.com',
            'role': 'quanly'
        },
        {
            'username': 'kiemtra_user',
            'password': 'Kiemtra@123',
            'email': 'kiemtra@example.com',
            'role': 'kiemtra'
        },
        {
            'username': 'nhanvien_user',
            'password': 'Nhanvien@123',
            'email': 'nhanvien@example.com',
            'role': 'nhanvien'
        }
    ]
    
    created_users = []
    existing_users = []
    
    for user_data in sample_users:
        # Check if user already exists
        if User.objects.filter(username=user_data['username']).exists():
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
                'role': user_data['role'],
                'created_at': get_current_time().isoformat()
            }
            
            users_collection.update_one(
                {'user_id': str(user.id)},
                {'$set': mongo_user_data},
                upsert=True
            )
            
            created_users.append(user_data['username'])
        except Exception as e:
            messages.error(request, f'Error creating user {user_data["username"]}: {str(e)}')
    
    client.close()
    
    if created_users:
        messages.success(request, f'Đã tạo thành công các user: {", ".join(created_users)}')
    if existing_users:
        messages.warning(request, f'Các user đã tồn tại: {", ".join(existing_users)}')
        
    return redirect('manage_users')

@login_required
@role_required('admin')
def create_user(request):
    if request.method == 'POST':
        # Debug logging
        print("Creating user...")
        print("POST data:", request.POST)
        
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        role = request.POST.get('role')
        
        print(f"Username: {username}")
        print(f"Email: {email}")
        print(f"Role: {role}")
        
        # Kiểm tra dữ liệu đầu vào
        if not all([username, email, password, role]) or role not in ROLES:
            print("Invalid data:", {
                'username': bool(username),
                'email': bool(email),
                'password': bool(password),
                'role': role in ROLES
            })
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
            # Log the error for debugging
            print(f"Error creating user: {str(e)}")
            return JsonResponse({
                'success': False,
                'message': str(e)
            })
            
    return JsonResponse({
        'success': False,
        'message': 'Phương thức không được hỗ trợ'
    })

@login_required
@role_required(['admin', 'quanly'])
def export_emails(request):
    # Lấy thông tin ngày xử lý từ request
    process_date = request.GET.get('process_date')
    
    # Lấy danh sách trạng thái được chọn
    selected_statuses = request.GET.getlist('status')
    
    # Nếu không có trạng thái nào được chọn, xuất tất cả
    excel_data_collection, client = get_collection_handle('excel_data')
    
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
    excel_data_collection, client = get_collection_handle('excel_data')

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
            
            # Đặt mật khẩu mới
            user.set_password(new_password)
            user.save()
            
            return JsonResponse({
                'success': True
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
            # Xóa user khỏi MongoDB
            users_collection, client = get_collection_handle('users')
            result = users_collection.delete_one({'user_id': user_id})
            
            # Xóa user khỏi Django
            user = User.objects.get(id=user_id)
            user.delete()
            
            client.close()
            
            if result.deleted_count > 0:
                return JsonResponse({
                    'success': True
                })
            else:
                return JsonResponse({
                    'success': False,
                    'message': 'Không tìm thấy user trong MongoDB'
                })
            
        except User.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Không tìm thấy user trong Django'
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

@login_required
@role_required(['admin', 'quanly'])
def work_time_stats(request):
    # Lấy thông tin filter từ request
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    user_id = request.GET.get('user_id')

    # Xử lý ngày tháng
    if not end_date:
        end_date = timezone.now().date()
    else:
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    if not start_date:
        start_date = end_date - timedelta(days=30)
    else:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()

    # Query cơ bản
    activities = UserActivity.objects.filter(
        login_time__date__gte=start_date,
        login_time__date__lte=end_date
    )

    # Lọc theo user nếu được chọn
    if user_id:
        activities = activities.filter(user_id=user_id)

    # Tính toán thống kê
    stats = []
    for user in User.objects.all():
        user_activities = activities.filter(user=user)
        total_sessions = user_activities.count()
        total_duration = sum(
            (activity.session_duration or timedelta()).total_seconds()
            for activity in user_activities
            if activity.session_duration
        )
        
        stats.append({
            'user': user,
            'total_sessions': total_sessions,
            'total_hours': round(total_duration / 3600, 2),
            'average_session': round(total_duration / total_sessions / 3600, 2) if total_sessions > 0 else 0,
            'activities': user_activities.order_by('-login_time')
        })

    context = {
        'stats': stats,
        'start_date': start_date,
        'end_date': end_date,
        'selected_user': user_id,
        'users': User.objects.all()
    }
    
    return render(request, 'authentication/work_time_stats.html', context)
