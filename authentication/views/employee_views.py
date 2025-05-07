from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.shortcuts import render, redirect
from .mongodb import get_collection_handle
from datetime import datetime
from django.utils import timezone
import logging
import json
from django.contrib import messages
from pymongo import MongoClient
from django.conf import settings
from datetime import datetime, time
from authentication.permissions import (
    role_required, can_manage_users, can_update_status, 
    ROLES, get_allowed_status_updates
)
logger = logging.getLogger(__name__)

@login_required
def email_info_view(request):
    try:
        # Get MongoDB collection handle
        worksession_collection = get_collection_handle('employee_worksession')
        checkPass_Today = get_collection_handle('employee_passwordregproduct')

        if worksession_collection is None:
            return JsonResponse({
                'success': False,
                'error': 'Không thể kết nối đến cơ sở dữ liệu'
            }, status=500)
        
        # Get today's date in YYYY-MM-DD format
        today = datetime.now().strftime('%Y-%m-%d')
        todayDmY = datetime.now().strftime('%d/%m/%Y')
        print(todayDmY)
        # Check if there are any records with today's date and matching owner
        current_worksession = worksession_collection.find_one({
            'created_at': {'$regex': f'^{today}'},
            'owner': request.user.username
        })
        print(current_worksession)
        checkPass_TodayTn = checkPass_Today.find_one({
            'created_at': {'$regex': f'^{todayDmY}'},
            'type': 'TextNow'
        })
        checkPass_TodayTf = checkPass_Today.find_one({
            'created_at': {'$regex': f'^{todayDmY}'},
            'type': 'TextFree'
        })
        if checkPass_TodayTn is None:
            pass_Tn = None
        else:
            pass_Tn = checkPass_TodayTn.get('password')
        if checkPass_TodayTf is None:
            pass_Tf = None
        else:
            pass_Tf = checkPass_TodayTf.get('password')
        if not current_worksession:
            # If no records exist for today, create a new one
            new_worksession = {
                'owner': request.user.username,
                'created_at': datetime.now().isoformat(),
                'created_textnow_emails': [],
                'total_accounts': 0,
            }
            worksession_collection.insert_one(new_worksession)
            current_worksession = new_worksession

        # Get created_textnow_emails from current_worksession
        created_textnow_emails = current_worksession.get('created_textnow_emails', [])
        total_accounts = current_worksession.get('total_accounts', 0)

        # Convert Python boolean values to JavaScript compatible format
        for email in created_textnow_emails:
            if 'is_reg_acc' in email:
                email['is_reg_acc'] = 'true' if email['is_reg_acc'] else 'false'

        # Prepare context data
        print(created_textnow_emails)
        context = {
            'emails': json.dumps(created_textnow_emails),  # Convert to JSON string
            'total_accounts': total_accounts,
            'worksession': current_worksession
        }

        return render(request, 'authentication/employee_email_info.html', context)
            
    except Exception as e:
        logger.error(f"Error in email_info_view: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@csrf_exempt
@require_http_methods(["GET"])
def get_available_emails_api(request):
    try:
        # Get MongoDB collection handles
        email_collection = get_collection_handle('employee_email')
        pass_Tn = get_collection_handle('employee_passwordregproduct')
        worksession_collection = get_collection_handle('employee_worksession')

        if email_collection is None or pass_Tn is None or worksession_collection is None:
            return JsonResponse({
                'success': False,
                'error': 'Không thể kết nối đến cơ sở dữ liệu'
            }, status=500)

        try:
            # Get current user and datetime
            current_user = request.user.username
            current_datetime = datetime.now()
            today = current_datetime.strftime('%Y-%m-%d')

            # Get current worksession
            current_worksession = worksession_collection.find_one({
                'created_at': {'$regex': f'^{today}'},
                'owner': current_user
            })

            if not current_worksession:
                # Create new worksession if not exists
                current_worksession = {
                    'owner': current_user,
                    'created_at': current_datetime.isoformat(),
                    'created_textnow_emails': [],
                    'total_accounts': 0
                }
                worksession_collection.insert_one(current_worksession)

            # Check for missing passwords
          
           

            # Query emails with status='chưa sử dụng' and is_provided=false, limit to 5 records
            available_emails = list(email_collection.find({
                'status': 'chưa sử dụng',
                'is_provided': False
            }).sort('created_at', -1).limit(5))
            
            pass_Tn_today = pass_Tn.find_one({
                'type': 'TextNow',
                'use_at': current_datetime.strftime('%d/%m/%Y')
            }, sort=[('created_at', -1)])
            
            pass_Tf_today = pass_Tn.find_one({
                'type': 'TextFree',
                'use_at': current_datetime.strftime('%d/%m/%Y')
            }, sort=[('created_at', -1)])
            missing_passwords = []

            if pass_Tn_today is None:
                missing_passwords.append('TextNow')
            if pass_Tf_today is None:
                missing_passwords.append('TextFree')

            # Convert MongoDB documents to list of dictionaries and update records
            if missing_passwords:
                return JsonResponse({
                    'success': False,
                    'error': f'Vui lòng bổ sung mật khẩu {" và ".join(missing_passwords)} cho ngày hôm nay',
                    'missing_passwords': True
                })
            processed_emails = []

            for email in available_emails:
                # Update the record in MongoDB
                email_collection.update_one(
                    {'_id': email['_id']},
                    {
                        '$set': {
                            'status': 'đã được cấp phát',
                            'is_provided': True,
                            'date_get': current_datetime,
                            'user_get': current_user
                        }
                    }
                )

                # Create new email record
                new_email = {
                    'email': email.get('email'),
                    'password': email.get('password'),
                    'refresh_token': email.get('refresh_token'),
                    'client_id': email.get('client_id'),
                    'status': 'đã được cấp phát',
                    'status_tn': 'chưa tạo acc',
                    'status_tf': 'chưa tạo acc',
                    'sub_status': email.get('sub_status'),
                    'supplier': email.get('supplier'),
                    'created_at': email.get('created_at'),
                    'is_provided': True,
                    'date_get': current_datetime,
                    'pass_TN': pass_Tn_today.get('password') if pass_Tn_today else None,
                    'pass_TF': pass_Tf_today.get('password') if pass_Tf_today else None,
                }

                # Add to processed emails list
                processed_emails.append(new_email)

                # Add to worksession
                worksession_collection.update_one(
                    {'_id': current_worksession['_id']},
                    {
                        '$push': {'created_textnow_emails': new_email},
                        '$inc': {'total_accounts': 1}
                    }
                )

            return JsonResponse({
                'success': True,
                'data': processed_emails
            })
                
        except Exception as e:
            logger.error(f"Error in get_available_emails_api: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
            
    except Exception as e:
        logger.error(f"Error in get_available_emails_api: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
def create_password_view(request):
    if request.method == 'POST':
        try:
            password = request.POST.get('password')
            type = request.POST.get('type')
            create_by = request.POST.get('create_by')
            use_at = datetime.strptime(request.POST.get('use_at'), '%Y-%m-%d').strftime('%d/%m/%Y')
            
            # Get MongoDB collection handle
            collection = get_collection_handle('employee_passwordregproduct')
            
            if collection is None:
                return JsonResponse({
                    'success': False,
                    'error': 'Không thể kết nối đến cơ sở dữ liệu'
                }, status=500)
            
            # Create new password document
            new_password = {
                'password': password,
                'type': type,
                'create_by': create_by,
                'use_at': use_at,
                'is_used': False,
                'created_at': datetime.now(),
                'updated_at': datetime.now()
            }
            
            # Insert into MongoDB
            collection.insert_one(new_password)
            
            return JsonResponse({
                'success': True,
                'message': 'Thêm mật khẩu thành công'
            })
            
        except Exception as e:
            logger.error(f"Error in create_password_view: {str(e)}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
                    
    return render(request, 'authentication/create_password.html')

@csrf_exempt
@require_http_methods(["GET"])
@login_required
def search_textnow_api(request):
    try:
        # Kết nối MongoDB
        client = MongoClient(settings.MONGODB_URI)
        db = client[settings.MONGODB_DATABASE]
        collection = db['employee_textnow']
        
        # Lấy parameters từ request
        status_tn = request.GET.get('status_tn')
        search_date = request.GET.get('date', datetime.now().strftime('%Y-%m-%d'))
        created_by = request.GET.get('created_by')
        
        # Xây dựng query
        query = {}
        
        # Thêm điều kiện ngày nếu có
        if search_date:
            query['created_at'] = {'$regex': f'^{search_date}'}
            
        # Thêm điều kiện status_tn nếu có
        if status_tn:
            query['status_account_TN'] = status_tn
            
        # Thêm điều kiện created_by nếu có
        if created_by:
            query['created_by'] = created_by
            
        # Chỉ lấy các trường cần thiết
        projection = {
            '_id': 0,
            'email': 1,
            'password_email': 1,
            'password': 1,
            'password_TF': 1,
            'status_account_TN': 1,
            'status_account_TF': 1,
            'created_at': 1,
            'created_by': 1,
            'full_information': 1
        }
        
        # Thực hiện query
        records = list(collection.find(query, projection).sort('created_at', -1))
        
        # Format lại ngày trong records
        for record in records:
            if 'created_at' in record:
                record['created_at'] = record['created_at'].split('T')[0]
        
        # Lấy danh sách người tạo để trả về cho dropdown
        creators = list(collection.distinct('created_by'))
        creators = sorted([creator for creator in creators if creator])

        return JsonResponse({
            'success': True,
            'data': records,
            'total': len(records),
            'creators': creators,
            'filters': {
                'status_tn': status_tn,
                'date': search_date,
                'created_by': created_by
            }
        })
        
    except Exception as e:
        logger.error(f"Error in search_textnow_api: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
    finally:
        if 'client' in locals():
            client.close()

@login_required
def verified_view(request):
    try:
        print('Đã vào trang verified')
        # Lấy thông tin user từ MongoDB
        users_collection, client = get_collection_handle('users')
        if users_collection is None:
            messages.error(request, 'Không thể kết nối đến cơ sở dữ liệu')
            return render(request, 'authentication/verified.html', {
                'textnow_accounts': [],
                'current_page': 1,
                'total_pages': 1
            })

        try:
            # Lấy thông tin user
            user_data = users_collection.find_one({'user_id': str(request.user.id)})
            if not user_data:
                messages.error(request, 'Không tìm thấy thông tin người dùng')
                return redirect('login')

            # Lấy dữ liệu TextNow accounts
            textnow_collection, client = get_collection_handle('employee_textnow')
            # query = {'assigned_to': str(request.user.id)}
            
            # # Phân trang
            # page = int(request.GET.get('page', 1))
            # per_page = 10
            # skip = (page - 1) * per_page

            # # Đếm tổng số bản ghi
            # total_records = textnow_collection.count_documents(query)
            # total_pages = (total_records + per_page - 1) // per_page

            # # Lấy dữ liệu phân trang
            # accounts = list(textnow_collection.find(query)
            #               .sort('created_at', -1)
            #               .skip(skip)
            #               .limit(per_page))
            accounts = textnow_collection.find()

            # Xử lý dữ liệu
            processed_accounts = []
            
            for account in accounts:
                try:
                    # Thêm mongo_id
                    account['mongo_id'] = str(account['_id'])
                    
                    # Xử lý thời gian với timezone
                    if isinstance(account['created_at'], str):
                        created_at = datetime.fromisoformat(account['created_at'])
                    else:
                        created_at = account['created_at']
                    
                    # Đảm bảo created_at có timezone
                    if created_at.tzinfo is None:
                        created_at = timezone.make_aware(created_at)
                    
                    now = timezone.now()
                    time_diff = now - created_at
                    
                    if time_diff.days > 0:
                        account['time_info'] = f"{time_diff.days} ngày trước"
                    elif time_diff.seconds >= 3600:
                        hours = time_diff.seconds // 3600
                        account['time_info'] = f"{hours} giờ trước"
                    else:
                        minutes = time_diff.seconds // 60
                        account['time_info'] = f"{minutes} phút trước"
                        
                except Exception as e:
                    logger.error(f"Error processing account {account.get('_id')}: {str(e)}")
                    continue
                    
                processed_accounts.append(account)

            context = {
                'textnow_accounts': processed_accounts,
                # 'current_page': page,
                # 'total_pages': total_pages,
                'user_data': user_data
            }

            return render(request, 'authentication/verified.html', context)

        finally:
            if client:
                try:
                    client.close()
                except Exception as e:
                    logger.error(f"Error closing MongoDB connection: {str(e)}")

    except Exception as e:
        logger.error(f"Error in verified_view: {str(e)}", exc_info=True)
        messages.error(request, 'Có lỗi xảy ra khi tải dữ liệu')
        return render(request, 'authentication/verified.html', {
            'textnow_accounts': [],
            'current_page': 1,
            'total_pages': 1
        })


@login_required
def create_email_view(request):
    try:
        # Get MongoDB collection handle
        email_collection = get_collection_handle('employee_email')
        
        if email_collection is None:
            return JsonResponse({
                'success': False,
                'error': 'Không thể kết nối đến cơ sở dữ liệu'
            }, status=500)

        if request.method == 'POST':
            try:
                # Get form data
                supplier = request.POST.get('supplier')
                status = request.POST.get('status', 'chưa sử dụng')
                sub_status = request.POST.get('sub_status', 'chưa sử dụng')
                import_file = request.FILES.get('import_file')

                if not all([supplier, import_file]):
                    return JsonResponse({
                        'success': False,
                        'error': 'Vui lòng điền đầy đủ thông tin'
                    }, status=400)

                # Read and process file
                try:
                    file_data = import_file.read().decode('utf-8')
                    lines = file_data.splitlines()
                    added_count = 0
                    error_count = 0

                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue

                        try:
                            parts = line.split('|')
                            if len(parts) < 2:
                                error_count += 1
                                continue

                            email = parts[0].strip()
                            password = parts[1].strip()
                            refresh_token = parts[2].strip() if len(parts) > 2 else ''
                            client_id = parts[3].strip() if len(parts) > 3 else ''

                            if not email or not password:
                                error_count += 1
                                continue

                            # Check if email exists
                            if email_collection.find_one({'email': email}):
                                error_count += 1
                                continue

                            # Create new email document
                            new_email = {
                                'email': email,
                                'password': password,
                                'refresh_token': refresh_token,
                                'client_id': client_id,
                                'status': status,
                                'sub_status': sub_status,
                                'supplier': supplier,
                                'is_provided': False,
                                'created_at': datetime.now().isoformat()
                            }

                            # Insert into MongoDB
                            email_collection.insert_one(new_email)
                            added_count += 1

                        except Exception as e:
                            logger.error(f"Error processing line: {line}. Error: {str(e)}")
                            error_count += 1
                            continue

                    message = f"Đã thêm thành công {added_count} email"
                    if error_count > 0:
                        message += f", có {error_count} email không thể thêm"

                    return JsonResponse({
                        'success': True,
                        'message': message
                    })

                except Exception as e:
                    logger.error(f"Error reading file: {str(e)}")
                    return JsonResponse({
                        'success': False,
                        'error': 'Lỗi đọc file'
                    }, status=400)

            except Exception as e:
                logger.error(f"Error in create_email_view POST: {str(e)}")
                return JsonResponse({
                    'success': False,
                    'error': str(e)
                }, status=500)

        # If GET request, prepare form data
        form_data = {
            'status': 'chưa sử dụng',
            'sub_status': 'chưa sử dụng',
            'supplier': 'f1mail'  # Default supplier
        }
        
        return render(request, 'authentication/create_mail.html', {
            'form': form_data
        })

    except Exception as e:
        logger.error(f"Error in create_email_view: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@csrf_exempt
@require_http_methods(["POST"])
@login_required
def create_textnow_api(request):
    try:
        # Get data from request
        data = request.POST.get('data')
        if not data:
            return JsonResponse({
                'success': False,
                'error': 'Thiếu dữ liệu'
            }, status=400)
            
        try:
            accounts = json.loads(data)
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Dữ liệu không đúng định dạng JSON'
            }, status=400)
        
        if not isinstance(accounts, list):
            return JsonResponse({
                'success': False,
                'error': 'Dữ liệu phải là một mảng'
            }, status=400)

        # Get MongoDB collection handle
        collection = get_collection_handle('employee_textnow')
        if collection is None:
            return JsonResponse({
                'success': False,
                'error': 'Không thể kết nối đến cơ sở dữ liệu'
            }, status=500)
        
        # Process each account
        created_accounts = []
        for account in accounts:
            # Validate required fields
            required_fields = ['email', 'password', 'pass_TN', 'pass_TF', 'status_tn', 
                             'status_tf', 'supplier']
            if not all(field in account for field in required_fields):
                continue

            # Create new textnow document
            new_textnow = {
                'email': account['email'],
                'password_email': account['password'],
                'password': account['pass_TN'],
                'password_TF': account['pass_TF'],
                'supplier': account['supplier'],
                'status_account_TN': account['status_tn'],
                'status_account_TF': account['status_tf'],
                'refresh_token': account.get('refresh_token', ''),
                'client_id': account.get('client_id', ''),
                'full_information': f"{account['email']}|{account['password']}|{account.get('refresh_token', '')}|{account.get('client_id', '')}",
                'created_by': account.get('created_by', request.user.username),
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat(),
                'sold_status_TN': False,
                'sold_status_TF': False
            }
            
            # Insert into MongoDB
            collection.insert_one(new_textnow)
            
            created_accounts.append({
                'email': new_textnow['email'],
                'status_TN': new_textnow['status_account_TN'],
                'status_TF': new_textnow['status_account_TF'],
                'created_at': new_textnow['created_at']
            })

        if not created_accounts:
            return JsonResponse({
                'success': False,
                'error': 'Không có tài khoản nào được tạo thành công'
            }, status=400)

        return JsonResponse({
            'success': True,
            'message': f'Đã tạo thành công {len(created_accounts)} tài khoản',
            'data': created_accounts
        })

    except Exception as e:
        logger.error(f"Error in create_textnow_api: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@csrf_exempt
@require_http_methods(["POST"])
@login_required
def save_worksession_api(request):
    try:
        # Get data from request
        data = request.POST.get('data')
        if not data:
            return JsonResponse({
                'success': False,
                'error': 'Thiếu dữ liệu'
            }, status=400)
            
        try:
            worksession_data = json.loads(data)
            print(worksession_data)
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Dữ liệu không đúng định dạng JSON'
            }, status=400)
        
        if not isinstance(worksession_data, list):
            return JsonResponse({
                'success': False,
                'error': 'Dữ liệu phải là một mảng'
            }, status=400)

        # Get MongoDB collection handle
        collection = get_collection_handle('employee_worksession')
        if collection is None:
            return JsonResponse({
                'success': False,
                'error': 'Không thể kết nối đến cơ sở dữ liệu'
            }, status=500)

        # Get current date
        current_date = datetime.now().strftime('%Y-%m-%d')
        
        # Find existing worksession for today
        existing_worksession = collection.find_one({
            'owner': request.user.username,
            'created_at': {'$regex': f'^{current_date}'}
        })

        if existing_worksession:
            # Update existing worksession
            collection.update_one(
                {'_id': existing_worksession['_id']},
                {
                    '$set': {
                        'created_textnow_emails': worksession_data,
                        'total_accounts': len(worksession_data),
                        'updated_at': datetime.now().isoformat()
                    }
                }
            )
        else:
            # Create new worksession
            new_worksession = {
                'owner': request.user.username,
                'created_textnow_emails': worksession_data,
                'total_accounts': len(worksession_data),
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            collection.insert_one(new_worksession)

        return JsonResponse({
            'success': True,
            'message': 'Đã lưu phiên làm việc thành công'
        })

    except Exception as e:
        logger.error(f"Error in save_worksession_api: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
def employee_dashboard_view(request):
    try:
        # Get user data from MongoDB
        users_collection, client = get_collection_handle('users')
        if users_collection is None or client is None:
            messages.error(request, 'Không thể kết nối đến cơ sở dữ liệu')
            return redirect('login')
            
        user_data = users_collection.find_one({'user_id': str(request.user.id)})
        if not user_data:
            messages.error(request, 'Không tìm thấy thông tin người dùng')
            return redirect('login')
            
        context = {
            'user_data': user_data,
        }
        
        return render(request, 'authentication/employee_dashboard.html', context)
            
    except Exception as e:
        logger.error(f"Error in employee_dashboard_view: {str(e)}")
        messages.error(request, 'Đã xảy ra lỗi. Vui lòng thử lại sau.')
        return redirect('login')

@login_required
def employee_work_view(request):
    try:
        # Get user data from MongoDB
        users_collection, client = get_collection_handle('users')
        if users_collection is None or client is None:
            messages.error(request, 'Không thể kết nối đến cơ sở dữ liệu')
            return redirect('login')
            
        user_data = users_collection.find_one({'user_id': str(request.user.id)})
        if not user_data:
            messages.error(request, 'Không tìm thấy thông tin người dùng')
            return redirect('login')
            
        context = {
            'user_data': user_data,
        }
        
        return render(request, 'authentication/employee_work.html', context)
            
    except Exception as e:
        logger.error(f"Error in employee_work_view: {str(e)}")
        messages.error(request, 'Đã xảy ra lỗi. Vui lòng thử lại sau.')
        return redirect('login')

@csrf_exempt
@require_http_methods(["POST"])
@login_required
def update_textnow_status_api(request):
    try:
        # Lấy dữ liệu từ request
        data = json.loads(request.body)
        email = data.get('email')
        status_tn = data.get('status_tn')
        status_tf = data.get('status_tf')

        if not email:
            return JsonResponse({
                'success': False,
                'error': 'Email không được để trống'
            }, status=400)

        # Kết nối MongoDB
        client = MongoClient(settings.MONGODB_URI)
        db = client[settings.MONGODB_DATABASE]
        collection = db['employee_textnow']

        # Tạo update query
        update_query = {'$set': {}}
        
        if status_tn is not None:
            update_query['$set']['status_account_TN'] = status_tn
        if status_tf is not None:
            update_query['$set']['status_account_TF'] = status_tf
        
        # Thêm updated_at vào update query
        update_query['$set']['updated_at'] = datetime.now().isoformat()

        # Thực hiện update
        result = collection.update_one(
            {'email': email},
            update_query
        )

        if result.matched_count == 0:
            return JsonResponse({
                'success': False,
                'error': 'Không tìm thấy email trong hệ thống'
            }, status=404)

        return JsonResponse({
            'success': True,
            'message': 'Cập nhật trạng thái thành công'
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Dữ liệu không hợp lệ'
        }, status=400)
    except Exception as e:
        logger.error(f"Error in update_textnow_status_api: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
    finally:
        if 'client' in locals():
            client.close() 