from authentication.employee_permissions import DynamicEmailForm
from authentication.employee_models import Email,TextNow, WorkSession, PasswordRegProduct,TextFree
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from .mongodb import get_collection_handle
from django.utils.dateparse import parse_datetime
import random
import json
import logging
logger = logging.getLogger(__name__)
from pymongo.errors import OperationFailure
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db.models import Q
from mongoengine import connect, disconnect
from django.conf import settings
from datetime import datetime, time
import pytz
from django.core.paginator import Paginator
import string
from django.utils import timezone
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required


def get_vietnam_datetime():
    """
    Lấy ngày giờ hiện tại theo múi giờ Việt Nam với định dạng dd/mm/yyyy
    Returns:
        str: Ngày giờ định dạng dd/mm/yyyy
    """
    vietnam_tz = pytz.timezone('Asia/Ho_Chi_Minh')
    return datetime.now(vietnam_tz).strftime('%d/%m/%Y')

def create_email_view(request):
    if request.method == 'POST':
        form = DynamicEmailForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                cleaned_data = form.cleaned_data
                status = cleaned_data['status']
                sub_status = cleaned_data['sub_status']
                supplier = cleaned_data['supplier']
                added_count = 0
                error_count = 0
                raw_lines = []

                # Xử lý file upload
                import_file = request.FILES.get('import_file')
                if import_file:
                    try:
                        file_data = import_file.read().decode('utf-8')
                        raw_lines = file_data.splitlines()
                    except Exception as e:
                        logger.error(f"Lỗi đọc file: {str(e)}", exc_info=True)
                        messages.error(request, "File upload không đúng định dạng hoặc bị lỗi")
                        return render(request, 'employee/create_mail.html', {'form': form})

                elif cleaned_data.get('bulk_input'):
                    raw_lines = cleaned_data['bulk_input'].splitlines()

                if not raw_lines:
                    messages.warning(request, "Không có dữ liệu email nào được nhập")
                    return render(request, 'employee/create_mail.html', {'form': form})

                # Tạo các email
                for idx, line in enumerate(raw_lines, 1):
                    try:
                        parts = [part.strip() for part in line.strip().split('|')]
                        if len(parts) < 2:
                            logger.warning(f"Dòng {idx} không đủ thông tin: {line}")
                            error_count += 1
                            continue

                        email = parts[0]
                        password = parts[1]
                        refresh_token = parts[2] if len(parts) > 2 else None
                        client_id = parts[3] if len(parts) > 3 else None

                        if not email or not password:
                            logger.warning(f"Dòng {idx} thiếu email hoặc password: {line}")
                            error_count += 1
                            continue

                        if Email.objects.filter(email=email).exists():
                            logger.warning(f"Email {email} đã tồn tại (dòng {idx})")
                            error_count += 1
                            continue

                        Email.objects.create(
                            email=email,
                            password=password,
                            refresh_token=refresh_token,
                            client_id=client_id,
                            status=status,
                            sub_status=sub_status,
                            supplier=supplier,
                            # created_by=request.user if request.user.is_authenticated else None
                        )
                        added_count += 1

                    except Exception as e:
                        logger.error(f"Lỗi khi xử lý dòng {idx}: {line}. Lỗi: {str(e)}", exc_info=True)
                        error_count += 1
                        continue

                if added_count > 0:
                    messages.success(request, f"Đã thêm thành công {added_count} email!")
                if error_count > 0:
                    messages.warning(request, f"Có {error_count} email không thể thêm do lỗi")

                return redirect('create_email')  # Chuyển hướng để tránh submit lại form
                # ... code xử lý của bạn ...
            except OperationFailure as e:
                logger.error(f"Lỗi MongoDB: {str(e)}")
                messages.error(request, "Lỗi kết nối database. Vui lòng thử lại sau.")
                return redirect('create_email')
            except Exception as e:
                logger.error(f"Lỗi hệ thống: {str(e)}", exc_info=True)
                messages.error(request, "Đã xảy ra lỗi khi tạo email.")
                return redirect('create_email')
    else:
        form = DynamicEmailForm()
    
    return render(request, 'employee/create_mail.html', {'form': form})

# def generate_session_code():
#     """Tạo mã phiên làm việc ngẫu nhiên"""
#     return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def employee_work_view(request):
    try:
        # Kiểm tra cookie
        session_code = request.COOKIES.get('code_WorkSession')
        print(session_code)
     
        if session_code is None:
            # Tạo mã phiên làm việc mới
            session_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            
            # Lấy tất cả email chưa được cung cấp
            all_emails = Email.objects.all()
            available_emails = []
            for email in all_emails:
                if email.status == 'chưa sử dụng' and not email.is_provided:
                    available_emails.append(email)
            
            # Chọn ngẫu nhiên 5 email từ danh sách có sẵn
            filtered_emails = random.sample(available_emails, min(5, len(available_emails)))
            
            # Lấy ngày hiện tại theo múi giờ Việt Nam
        
            # Tìm password TextNow cho ngày hôm nay
            passwordRegProduct_Tn = PasswordRegProduct.objects.filter(
                type='TextNow',
                use_at=get_vietnam_datetime(),
            ).first()
            passwordRegProduct_Tf = PasswordRegProduct.objects.filter(
                type='TextFree',
                use_at=get_vietnam_datetime(),
            ).first()
            if not passwordRegProduct_Tn:
                return HttpResponse("Không tìm thấy mật khẩu TextNow cho ngày hôm nay. Vui lòng thêm mật khẩu trước khi tiếp tục.", status=400)
            if not passwordRegProduct_Tf:
                return HttpResponse("Không tìm thấy mật khẩu TextFee cho ngày hôm nay. Vui lòng thêm mật khẩu trước khi tiếp tục.", status=400)

                
            pass_word_textnow_Tn = passwordRegProduct_Tn.password
            pass_word_textnow_Tf = passwordRegProduct_Tf.password
            # Cập nhật trạng thái các email đã chọn và thêm password
            for email in filtered_emails:
                email.is_provided = True
                setattr(email, 'pass_word_textnow', pass_word_textnow_Tn)
                setattr(email, 'pass_word_textnow_Tf', pass_word_textnow_Tf)
                email.save()
                print(f"pass1: {email.pass_word_textnow}")
                print(f"pass2: {email.pass_word_textnow_Tf}")
                # Thêm password vào email nếu có
            
            # Tạo phiên làm việc mới
            work_session = WorkSession.objects.create(
                code=session_code,
                total_accounts=len(filtered_emails),
                created_textnow_emails=[{
                    'email': email.email,
                    'password': email.password,
                    'refresh_token': email.refresh_token,
                    'client_id': email.client_id,
                    'status': email.status,
                    'supplier': email.supplier,
                    'is_provided': email.is_provided,
                    'status_reg_account_TN': 'chưa tạo acc',
                    'status_reg_account_TF': 'chưa tạo acc',
                    'pass_word_textnow': email.pass_word_textnow,
                    'pass_word_textnow_Tf': email.pass_word_textnow_Tf,
                    'is_reg_TN': False,
                    'is_reg_TF': False

                } for email in filtered_emails]
            )
            
            # Tạo response với cookie chứa session_code
            response = render(request, 'employee/employee_work.html', {
                'emails': filtered_emails
            })
            response.set_cookie('code_WorkSession', session_code, max_age=86400)  # Cookie hết hạn sau 24 giờ
            return response
        else:
            connect(settings.NAME_MONGODB, host=settings.HOST_MONGODB)
            work_session = WorkSession.objects.filter(code=session_code).first()
            
            if work_session:
                if request.GET.get('provide_new') == 'true':
            
            # Tìm password TextNow cho ngày hôm nay
                    passwordRegProduct_Tn = PasswordRegProduct.objects.filter(
                        type='TextNow',
                        use_at=get_vietnam_datetime(),
                    )
                    passwordRegProduct_Tf = PasswordRegProduct.objects.filter(
                        type='TextFree',
                        use_at=get_vietnam_datetime(),
                    )
                    pass_word_textnow = (passwordRegProduct_Tn.first().password)
                    pass_word_textnow_Tf = (passwordRegProduct_Tf.first().password)
                    # Lấy tất cả email chưa được cung cấp
                    all_emails = Email.objects.all()
                    old_session_id = work_session.id
                    available_emails = []
                    for email in all_emails:
                        if email.status == 'chưa sử dụng' and not email.is_provided:
                            available_emails.append(email)
                    
                    if not available_emails:
                        return HttpResponse("Không còn email nào khả dụng", status=400)
                    
                    # Chọn ngẫu nhiên 5 email từ danh sách có sẵn
                    new_emails = random.sample(available_emails, min(5, len(available_emails)))
                    
                    # Cập nhật trạng thái các email đã chọn
                    for email in new_emails:
                        email.is_provided = True
                        setattr(email, 'pass_word_textnow', pass_word_textnow)
                        setattr(email, 'pass_word_textnow_Tf', pass_word_textnow_Tf)
                        email.save()
                    WorkSession.objects.filter(id=old_session_id).delete()
                    # Thêm email mới vào work_session hiện tại
                    work_session.created_textnow_emails.extend([{
                        'email': email.email,
                        'password': email.password,
                        'refresh_token': email.refresh_token,
                        'client_id': email.client_id,
                        'status': email.status,
                        'supplier': email.supplier,
                        'is_provided': email.is_provided,
                        'status_reg_account_TN': 'chưa tạo acc',
                        'status_reg_account_TF': 'chưa tạo acc',
                        'pass_word_textnow': email.pass_word_textnow,
                        'pass_word_textnow_Tf': email.pass_word_textnow_Tf,
                        'is_reg_TN': False,
                        'is_reg_TF': False

                    } for email in new_emails])
                    
                    # Cập nhật tổng số tài khoản
                    work_session.total_accounts = len(work_session.created_textnow_emails)
                    work_session.save()
                    
                    return render(request, 'employee/employee_work.html', {
                        'emails': work_session.created_textnow_emails
                    })
                else:
                # Nếu không có yêu cầu cấp email mới, hiển thị email hiện tại
                    emails = work_session.created_textnow_emails
                    print(emails)
                    return render(request, 'employee/employee_work.html', {
                        'emails': emails
                    })
            else:
                all_emails_1 = Email.objects.all()
                available_emails_1 = []
                for email in all_emails_1:
                    if email.status == 'chưa sử dụng' and not email.is_provided:
                        available_emails_1.append(email)
                
                # Chọn ngẫu nhiên 5 email từ danh sách có sẵn
                filtered_emails_1 = random.sample(available_emails_1, min(5, len(available_emails_1)))
            
                # Tìm password TextNow cho ngày hôm nay
                passwordRegProduct_1 = PasswordRegProduct.objects.filter(
                    type='TextNow',
                    use_at=get_vietnam_datetime(),
                )
                passwordRegProduct_Tf = PasswordRegProduct.objects.filter(
                    type='TextFree',
                    use_at=get_vietnam_datetime(),
                )
                pass_word_textnow_1 = (passwordRegProduct_1.first().password)
                pass_word_textnow_Tf = (passwordRegProduct_Tf.first().password)
                for email in filtered_emails_1:
                    email.is_provided = True
                    setattr(email, 'pass_word_textnow', pass_word_textnow_1)
                    setattr(email, 'pass_word_textnow_Tf', pass_word_textnow_Tf)

                    
                    email.save()
                
                WorkSession.objects.create(
                    code=session_code,
                    total_accounts=len(filtered_emails_1),
                    created_textnow_emails=[{
                        'email': email.email,
                        'password': email.password,
                        'refresh_token': email.refresh_token,
                        'client_id': email.client_id,
                        'status': email.status,
                        'supplier': email.supplier,
                        'is_provided': email.is_provided,
                        'status_reg_account_TN': 'chưa tạo acc',
                        'status_reg_account_TF': 'chưa tạo acc',
                        'pass_word_textnow': email.pass_word_textnow,
                        'pass_word_textnow_Tf': email.pass_word_textnow_Tf,
                        'is_reg_TN': False,
                        'is_reg_TF': False


                    } for email in filtered_emails_1]
                )
                logger.warning(f"No work session found with code: {session_code}")
                return render(request, 'employee/employee_work.html', {
                    'emails': filtered_emails_1
                })
                   
    except Exception as e:
        logger.error(f"Error in employee_work_view: {str(e)}", exc_info=True)
        return HttpResponse("Đã xảy ra lỗi khi khởi tạo phiên làm việc", status=500)

@csrf_exempt
@require_http_methods(["POST"])
def update_status_api_Tn(request):
    try:
        # Kiểm tra nếu request body là rỗng
        if not request.body:
            return JsonResponse({
                'success': False,
                'error': 'Empty request body'
            }, status=400)
            
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError as e:
            return JsonResponse({
                'success': False,
                'error': f'Invalid JSON: {str(e)}'
            }, status=400)
            
        email = data.get('email')
        status_reg_account_TN = data.get('status_reg_account_TN')
        
        if not email or not status_reg_account_TN:
            return JsonResponse({
                'success': False,
                'error': 'Missing required fields'
            }, status=400)
            
        # Cập nhật trạng thái trong WorkSession
        session_code = request.COOKIES.get('code_WorkSession')
        if session_code:
            try:
                # Kết nối với MongoDB Atlas
                connect(settings.NAME_MONGODB, host=settings.HOST_MONGODB)
                
                # Tìm work session theo code
                work_session = WorkSession.objects.filter(code=session_code).first()
                if not work_session:
                    disconnect()
                    return JsonResponse({
                        'success': False,
                        'error': 'Work session not found'
                    }, status=404)
                
                # Lưu ID của session cũ
                old_session_id = work_session.id
                
                # Cập nhật trạng thái trong danh sách email
                updated_emails = []
                for email_data in work_session.created_textnow_emails:
                    if email_data['email'] == email:
                        email_data['status_reg_account_TN'] = status_reg_account_TN
                    updated_emails.append(email_data)
                
                # Xóa session cũ
                WorkSession.objects.filter(id=old_session_id).delete()
                
                # Tạo session mới với dữ liệu đã cập nhật
                new_session = WorkSession(
                    code=session_code,
                    total_accounts=len(updated_emails),
                    created_textnow_emails=updated_emails
                )
                new_session.save()
                
                # Đóng kết nối
                disconnect()
                
                return JsonResponse({
                    'success': True,
                    'message': 'Status updated successfully'
                })
                
            except Exception as e:
                disconnect()  # Đảm bảo đóng kết nối nếu có lỗi
                return JsonResponse({
                    'success': False,
                    'error': str(e)
                }, status=500)
        else:
            return JsonResponse({
                'success': False,
                'error': 'No active work session'
            }, status=400)
            
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
@csrf_exempt
@require_http_methods(["POST"])
def update_status_api_Tf(request):
    try:
        # Kiểm tra nếu request body là rỗng
        if not request.body:
            return JsonResponse({
                'success': False,
                'error': 'Empty request body'
            }, status=400)
            
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError as e:
            return JsonResponse({
                'success': False,
                'error': f'Invalid JSON: {str(e)}'
            }, status=400)
            
        email = data.get('email')
        status_reg_account_TF = data.get('status_reg_account_TF')
        
        if not email or not status_reg_account_TF:
            return JsonResponse({
                'success': False,
                'error': 'Missing required fields'
            }, status=400)
            
        # Cập nhật trạng thái trong WorkSession
        session_code = request.COOKIES.get('code_WorkSession')
        if session_code:
            try:
                # Kết nối với MongoDB Atlas
                connect(settings.NAME_MONGODB, host=settings.HOST_MONGODB)
                
                # Tìm work session theo code
                work_session = WorkSession.objects.filter(code=session_code).first()
                if not work_session:
                    disconnect()
                    return JsonResponse({
                        'success': False,
                        'error': 'Work session not found'
                    }, status=404)
                
                # Lưu ID của session cũ
                old_session_id = work_session.id
                
                # Cập nhật trạng thái trong danh sách email
                updated_emails = []
                for email_data in work_session.created_textnow_emails:
                    if email_data['email'] == email:
                        email_data['status_reg_account_TF'] = status_reg_account_TF
                    updated_emails.append(email_data)
                
                # Xóa session cũ
                WorkSession.objects.filter(id=old_session_id).delete()
                
                # Tạo session mới với dữ liệu đã cập nhật
                new_session = WorkSession(
                    code=session_code,
                    total_accounts=len(updated_emails),
                    created_textnow_emails=updated_emails
                )
                new_session.save()
                
                # Đóng kết nối
                disconnect()
                
                return JsonResponse({
                    'success': True,
                    'message': 'Status updated successfully'
                })
                
            except Exception as e:
                disconnect()  # Đảm bảo đóng kết nối nếu có lỗi
                return JsonResponse({
                    'success': False,
                    'error': str(e)
                }, status=500)
        else:
            return JsonResponse({
                'success': False,
                'error': 'No active work session'
            }, status=400)
            
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
@csrf_exempt
def create_password_view(request):
    if request.method == 'GET':
        return render(request, 'employee/create_password.html')
    elif request.method == 'POST':
        try:
            # Lấy dữ liệu từ form
            password = request.POST.get('password')
            type = request.POST.get('type')
            create_by = request.POST.get('create_by')
            use_at = request.POST.get('use_at')
            
            # Chuyển đổi định dạng ngày từ yyyy-mm-dd sang dd/mm/yyyy nếu cần
            if use_at and '-' in use_at:
                try:
                    # Chuyển từ yyyy-mm-dd sang dd/mm/yyyy
                    date_obj = datetime.strptime(use_at, '%Y-%m-%d')
                    use_at = date_obj.strftime('%d/%m/%Y')
                except ValueError:
                    return JsonResponse({
                        'success': False,
                        'error': 'Định dạng ngày không hợp lệ'
                    }, status=400)
            
            # Kiểm tra định dạng ngày dd/mm/yyyy
            if use_at:
                try:
                    datetime.strptime(use_at, '%d/%m/%Y')
                except ValueError:
                    return JsonResponse({
                        'success': False,
                        'error': 'Ngày phải có định dạng dd/mm/yyyy'
                    }, status=400)
            
            if not all([password, type, create_by]):
                return JsonResponse({
                    'success': False,
                    'error': 'Thiếu thông tin bắt buộc'
                }, status=400)
            
            # Kiểm tra xem password đã tồn tại chưa
            if PasswordRegProduct.objects.filter(password=password).first():
                return JsonResponse({
                    'success': False,
                    'error': 'Mật khẩu đã tồn tại'
                }, status=400)
            
            # Nếu có ngày sử dụng, kiểm tra xem đã có bản ghi cùng type và ngày chưa
            if use_at:
                # Kiểm tra trùng lặp
                existing_record = PasswordRegProduct.objects.filter(
                    type=type,
                    use_at=use_at
                ).first()
                
                if existing_record:
                    return JsonResponse({
                        'success': False,
                        'error': f'Đã tồn tại bản ghi {type} cho ngày {use_at}'
                    }, status=400)
            
            # Tạo mới PasswordRegProduct
            password_obj = PasswordRegProduct(
                password=password,
                type=type,
                create_by=create_by
            )
            
            # Nếu có ngày sử dụng, thêm vào
            if use_at:
                password_obj.use_at = use_at
            
            password_obj.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Thêm mật khẩu thành công'
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': 'Đã xảy ra lỗi khi thêm mật khẩu'
            }, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def create_textnow_api(request):
    try:
        if not request.body:
            return JsonResponse({
                'success': False,
                'error': 'Empty request body'
            }, status=400)
            
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError as e:
            return JsonResponse({
                'success': False,
                'error': f'Invalid JSON: {str(e)}'
            }, status=400)
            
        # Lấy dữ liệu từ request, thêm refresh_token và client_id
        email = data.get('email')
        password_email = data.get('password_email')
        password = data.get('password')
        status_account = data.get('status_account_TN')
        refresh_token = data.get('refresh_token')  # Thêm trường mới
        client_id = data.get('client_id')  # Thêm trường mới
        supplier = 'Quân'
        
        if status_account == 'chưa tạo acc':
            return JsonResponse({
                'success': False,
                'error': 'Vui lòng cập nhật trạng thái Reg Acc TN trước khi tạo tài khoản TextNow'
            }, status=400)
        
        if not all([email, password_email, password, status_account, supplier]):
            return JsonResponse({
                'success': False,
                'error': 'Missing required fields'
            }, status=400)
            
        if TextNow.objects.filter(email=email).first():
            return JsonResponse({
                'success': False,
                'error': 'Email already exists'
            }, status=400)
            
        # Tạo mới TextNow với các trường mới
        textnow = TextNow.objects.create(
            email=email,
            password_email=password_email,
            password=password,
            status_account=status_account,
            supplier=supplier,
            refresh_token=refresh_token,  # Thêm trường mới
            client_id=client_id  # Thêm trường mới
        )
        
        # Cập nhật WorkSession như cũ
        session_code = request.COOKIES.get('code_WorkSession')
        if session_code:
            work_session = WorkSession.objects.filter(code=session_code).first()
            if work_session:
                for email_data in work_session.created_textnow_emails:
                    if email_data['email'] == email:
                        email_data['is_reg_TN'] = True
                        break
                old_session_id = work_session.id
                WorkSession.objects.filter(id=old_session_id).delete()
                work_session.save()
        
        return JsonResponse({
            'success': True,
            'message': 'TextNow created successfully',
            'data': {
                'id': str(textnow.id),
                'email': textnow.email,
                'status_account': textnow.status_account,
                'refresh_token': textnow.refresh_token,
                'client_id': textnow.client_id
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': 'An error occurred while creating TextNow'
        }, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def create_textfree_api(request):
    try:
        if not request.body:
            return JsonResponse({
                'success': False,
                'error': 'Empty request body'
            }, status=400)
            
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError as e:
            return JsonResponse({
                'success': False,
                'error': f'Invalid JSON: {str(e)}'
            }, status=400)
            
        # Lấy dữ liệu từ request, thêm refresh_token và client_id
        email = data.get('email')
        password_email = data.get('password_email')
        password = data.get('password')
        status_account = data.get('status_account_TF')
        refresh_token = data.get('refresh_token')  # Thêm trường mới
        client_id = data.get('client_id')  # Thêm trường mới
        supplier = 'Quân'
        
        if status_account == 'chưa tạo acc':
            return JsonResponse({
                'success': False,
                'error': 'Vui lòng cập nhật trạng thái Reg Acc TF trước khi tạo tài khoản TextFree'
            }, status=400)
        
        if not all([email, password_email, password, status_account, supplier]):
            return JsonResponse({
                'success': False,
                'error': 'Missing required fields'
            }, status=400)
            
        if TextFree.objects.filter(email=email).first():
            return JsonResponse({
                'success': False,
                'error': 'Email already exists'
            }, status=400)
            
        # Tạo mới TextFree với các trường mới
        textfree = TextFree.objects.create(
            email=email,
            password_email=password_email,
            password=password,
            status_account=status_account,
            supplier=supplier,
            refresh_token=refresh_token,  # Thêm trường mới
            client_id=client_id  # Thêm trường mới
        )
        
        # Cập nhật WorkSession như cũ
        session_code = request.COOKIES.get('code_WorkSession')
        if session_code:
            work_session = WorkSession.objects.filter(code=session_code).first()
            if work_session:
                for email_data in work_session.created_textnow_emails:
                    if email_data['email'] == email:
                        email_data['is_reg_TF'] = True
                        break
                old_session_id = work_session.id
                WorkSession.objects.filter(id=old_session_id).delete()
                work_session.save()
        
        return JsonResponse({
            'success': True,
            'message': 'TextFree created successfully',
            'data': {
                'id': str(textfree.id),
                'email': textfree.email,
                'status_account': textfree.status_account,
                'refresh_token': textfree.refresh_token,
                'client_id': textfree.client_id
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': 'An error occurred while creating TextFree'
        }, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def create_multiple_textnow_api(request):
    try:
        # Kiểm tra nếu request body là rỗng
        if not request.body:
            return JsonResponse({
                'success': False,
                'error': 'Empty request body'
            }, status=400)
            
        try:
            data = json.loads(request.body)
            accounts = data.get('accounts', [])
            print(accounts)  # Mảng các tài khoản cần tạo
        except json.JSONDecodeError as e:
            return JsonResponse({
                'success': False,
                'error': f'Invalid JSON: {str(e)}'
            }, status=400)
        
        if not accounts or not isinstance(accounts, list):
            return JsonResponse({
                'success': False,
                'error': 'Accounts data must be a non-empty array'
            }, status=400)

        created_accounts = []
        failed_accounts = []
        session_code = request.COOKIES.get('code_WorkSession')
        work_session = None

        if session_code:
            work_session = WorkSession.objects.filter(code=session_code).first()

        for account_data in accounts:
            try:
                # Lấy dữ liệu từ mỗi tài khoản
                email = account_data.get('email')
                password_email = account_data.get('password_email')
                password = account_data.get('password')
                status_account = account_data.get('status_account_TN')
                refresh_token = account_data.get('refresh_token')  # Thêm trường mới
                client_id = account_data.get('client_id')  # Thêm trường mới
                supplier = 'Quân'

                # Kiểm tra các trường bắt buộc
                if status_account == 'chưa tạo acc':
                    failed_accounts.append({
                        'email': email,
                        'error': 'Vui lòng cập nhật trạng thái Reg Acc TN trước khi tạo tài khoản'
                    })
                    continue

                if not all([email, password_email, password, status_account]):
                    failed_accounts.append({
                        'email': email,
                        'error': 'Missing required fields'
                    })
                    continue

                # Kiểm tra email đã tồn tại chưa
                if TextNow.objects.filter(email=email).first():
                    failed_accounts.append({
                        'email': email,
                        'error': 'Email already exists'
                    })
                    continue

                # Tạo mới TextNow với các trường mới
                textnow = TextNow.objects.create(
                    email=email,
                    password_email=password_email,
                    password=password,
                    status_account=status_account,
                    supplier=supplier,
                    refresh_token=refresh_token,  # Thêm trường mới
                    client_id=client_id  # Thêm trường mới
                )
                print(textnow)
                # Cập nhật trạng thái trong WorkSession
                if work_session:
                    for email_data in work_session.created_textnow_emails:
                        if email_data['email'] == email:
                            email_data['is_reg_TN'] = True
                            break

                created_accounts.append({
                    'id': str(textnow.id),
                    'email': textnow.email,
                    'status_account': textnow.status_account,
                    'refresh_token': textnow.refresh_token,
                    'client_id': textnow.client_id
                })

            except Exception as e:
                logger.error(f"Error creating TextNow for email {email}: {str(e)}")
                failed_accounts.append({
                    'email': email,
                    'error': str(e)
                })

        # Lưu work session sau khi cập nhật tất cả
        if work_session:
            old_session_id = work_session.id
            WorkSession.objects.filter(id=old_session_id).delete()
            work_session.save()

        return JsonResponse({
            'success': True,
            'message': f'Created {len(created_accounts)} accounts successfully, {len(failed_accounts)} failed',
            'data': {
                'created_accounts': created_accounts,
                'failed_accounts': failed_accounts
            }
        })

    except Exception as e:
        logger.error(f"Error in bulk creation: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'An error occurred during bulk creation'
        }, status=500)
@csrf_exempt
@require_http_methods(["POST"])
def create_multiple_textfree_api(request):
    try:
        # Kiểm tra nếu request body là rỗng
        if not request.body:
            return JsonResponse({
                'success': False,
                'error': 'Empty request body'
            }, status=400)
            
        try:
            data = json.loads(request.body)
            accounts = data.get('accounts', [])
            print(accounts)  # Mảng các tài khoản cần tạo
        except json.JSONDecodeError as e:
            return JsonResponse({
                'success': False,
                'error': f'Invalid JSON: {str(e)}'
            }, status=400)
        
        if not accounts or not isinstance(accounts, list):
            return JsonResponse({
                'success': False,
                'error': 'Accounts data must be a non-empty array'
            }, status=400)

        created_accounts = []
        failed_accounts = []
        session_code = request.COOKIES.get('code_WorkSession')
        work_session = None

        if session_code:
            work_session = WorkSession.objects.filter(code=session_code).first()

        for account_data in accounts:
            try:
                # Lấy dữ liệu từ mỗi tài khoản
                email = account_data.get('email')
                password_email = account_data.get('password_email')
                password = account_data.get('password')
                status_account = account_data.get('status_account_TF')
                refresh_token = account_data.get('refresh_token')  # Thêm trường mới
                client_id = account_data.get('client_id')  # Thêm trường mới
                supplier = 'Quân'

                # Kiểm tra các trường bắt buộc
                if status_account == 'chưa tạo acc':
                    failed_accounts.append({
                        'email': email,
                        'error': 'Vui lòng cập nhật trạng thái Reg Acc TF trước khi tạo tài khoản'
                    })
                    continue

                if not all([email, password_email, password, status_account]):
                    failed_accounts.append({
                        'email': email,
                        'error': 'Missing required fields'
                    })
                    continue

                # Kiểm tra email đã tồn tại chưa
                if TextFree.objects.filter(email=email).first():
                    failed_accounts.append({
                        'email': email,
                        'error': 'Email already exists'
                    })
                    continue

                # Tạo mới TextFree với các trường mới
                textfree = TextFree.objects.create(
                    email=email,
                    password_email=password_email,
                    password=password,
                    status_account=status_account,
                    supplier=supplier,
                    refresh_token=refresh_token,  # Thêm trường mới
                    client_id=client_id  # Thêm trường mới
                )
                print(textfree)
                # Cập nhật trạng thái trong WorkSession
                if work_session:
                    for email_data in work_session.created_textnow_emails:
                        if email_data['email'] == email:
                            email_data['is_reg_TF'] = True
                            break

                created_accounts.append({
                    'id': str(textfree.id),
                    'email': textfree.email,
                    'status_account': textfree.status_account,
                    'refresh_token': textfree.refresh_token,
                    'client_id': textfree.client_id
                })

            except Exception as e:
                logger.error(f"Error creating TextFree for email {email}: {str(e)}")
                failed_accounts.append({
                    'email': email,
                    'error': str(e)
                })

        # Lưu work session sau khi cập nhật tất cả
        if work_session:
            old_session_id = work_session.id
            WorkSession.objects.filter(id=old_session_id).delete()
            work_session.save()

        return JsonResponse({
            'success': True,
            'message': f'Created {len(created_accounts)} accounts successfully, {len(failed_accounts)} failed',
            'data': {
                'created_accounts': created_accounts,
                'failed_accounts': failed_accounts
            }
        })

    except Exception as e:
        logger.error(f"Error in bulk creation: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'An error occurred during bulk creation'
        }, status=500)


