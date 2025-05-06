from django.contrib import messages
from .mongodb import get_collection_handle
import logging
logger = logging.getLogger(__name__)
from datetime import datetime, time
from django.utils import timezone
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from bson import ObjectId



@login_required
def employee_verified_view(request):
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
        logger.error(f"Error in employee_verified_view: {str(e)}", exc_info=True)
        messages.error(request, 'Có lỗi xảy ra khi tải dữ liệu')
        return render(request, 'authentication/employee_verified.html', {
            'textnow_accounts': [],
            'current_page': 1,
            'total_pages': 1
        })

@csrf_exempt
@require_POST
def bulk_verify_success(request):
    try:
        if not request.user.is_authenticated:
            return JsonResponse({'success': False, 'message': 'Chưa đăng nhập'})

        ids = request.POST.getlist('ids[]')
        if not ids:
            return JsonResponse({'success': False, 'message': 'Không có ID nào được chọn'})

        # Kết nối MongoDB
        textnow_collection, client = get_collection_handle('employee_textnow')
        if not textnow_collection:
            return JsonResponse({'success': False, 'message': 'Không thể kết nối đến cơ sở dữ liệu'})

        try:
            # Cập nhật trạng thái cho các tài khoản đã chọn
            result = textnow_collection.update_many(
                {'_id': {'$in': [ObjectId(id) for id in ids]}},
                {'$set': {'status_account_TN': 'tạo acc thành công'}}
            )

            return JsonResponse({
                'success': True,
                'message': f'Đã cập nhật {result.modified_count} tài khoản thành công'
            })

        finally:
            if client:
                client.close()

    except Exception as e:
        logger.error(f"Error in bulk_verify_success: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'message': f'Có lỗi xảy ra: {str(e)}'})

@csrf_exempt
@require_POST
def bulk_verify_fail(request):
    try:
        if not request.user.is_authenticated:
            return JsonResponse({'success': False, 'message': 'Chưa đăng nhập'})

        ids = request.POST.getlist('ids[]')
        if not ids:
            return JsonResponse({'success': False, 'message': 'Không có ID nào được chọn'})

        # Kết nối MongoDB
        textnow_collection, client = get_collection_handle('employee_textnow')
        if not textnow_collection:
            return JsonResponse({'success': False, 'message': 'Không thể kết nối đến cơ sở dữ liệu'})

        try:
            # Cập nhật trạng thái cho các tài khoản đã chọn
            result = textnow_collection.update_many(
                {'_id': {'$in': [ObjectId(id) for id in ids]}},
                {'$set': {'status_account_TN': 'tạo acc thất bại'}}
            )

            return JsonResponse({
                'success': True,
                'message': f'Đã cập nhật {result.modified_count} tài khoản thất bại'
            })

        finally:
            if client:
                client.close()

    except Exception as e:
        logger.error(f"Error in bulk_verify_fail: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'message': f'Có lỗi xảy ra: {str(e)}'})