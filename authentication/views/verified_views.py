from django.contrib import messages
from .mongodb import get_collection_handle
import logging
import json
from bson import json_util
logger = logging.getLogger(__name__)
from datetime import datetime, time
from django.utils import timezone
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from bson import ObjectId
from pymongo import MongoClient
from django.conf import settings



@login_required
def employee_verified_view(request):
    client = None
    try:
        print('Đã vào trang verified')
        # Kết nối trực tiếp đến MongoDB
        client = MongoClient(
            settings.MONGODB_URI,
            username=settings.MONGODB_USERNAME,
            password=settings.MONGODB_PASSWORD,
            retryWrites=True,
            w='majority'
        )
        db = client[settings.MONGODB_DATABASE]
        users_collection = db['users']
        textnow_collection = db['employee_textnow']

        # Lấy thông tin user
        user_data = users_collection.find_one({'user_id': str(request.user.id)})
        if not user_data:
            messages.error(request, 'Không tìm thấy thông tin người dùng')
            return redirect('login')

        # Lấy dữ liệu TextNow accounts với các tham số tìm kiếm
        search_date = request.GET.get('date')
        status_tn = request.GET.get('status_tn')
        created_by = request.GET.get('created_by')

        # Xây dựng query
        query = {}
        if search_date:
            start_date = datetime.strptime(search_date, '%Y-%m-%d')
            end_date = start_date.replace(hour=23, minute=59, second=59)
            query['created_at'] = {'$gte': start_date, '$lte': end_date}
        if status_tn:
            query['status_account_TN'] = status_tn
        if created_by:
            query['created_by'] = created_by

        # Lấy dữ liệu với query
        accounts = list(textnow_collection.find(query).sort('created_at', -1))

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

        # Convert to JSON string using bson.json_util
        textnow_accounts_json = json_util.dumps(processed_accounts)

        # Lấy danh sách người tạo duy nhất
        creators = list(textnow_collection.distinct('created_by'))

        context = {
            'textnow_accounts': textnow_accounts_json,
            'user_data': user_data,
            'creators': creators,
            'search_date': search_date or datetime.now().strftime('%Y-%m-%d'),
            'status_tn': status_tn or '',
            'created_by': created_by or ''
        }

        return render(request, 'authentication/verified.html', context)

    except Exception as e:
        logger.error(f"Error in employee_verified_view: {str(e)}", exc_info=True)
        messages.error(request, 'Có lỗi xảy ra khi tải dữ liệu')
        return render(request, 'authentication/verified.html', {
            'textnow_accounts': '[]',
            'current_page': 1,
            'total_pages': 1
        })
    finally:
        if client:
            try:
                client.close()
            except Exception as e:
                logger.error(f"Error closing MongoDB connection: {str(e)}")

@csrf_exempt
@require_POST
def bulk_verify_success(request):
    client = None
    try:
        if not request.user.is_authenticated:
            return JsonResponse({'success': False, 'message': 'Chưa đăng nhập'})

        ids = request.POST.getlist('ids[]')
        if not ids:
            return JsonResponse({'success': False, 'message': 'Không có ID nào được chọn'})

        # Kết nối MongoDB
        client = MongoClient(
            settings.MONGODB_URI,
            username=settings.MONGODB_USERNAME,
            password=settings.MONGODB_PASSWORD,
            retryWrites=True,
            w='majority'
        )
        db = client[settings.MONGODB_DATABASE]
        textnow_collection = db['employee_textnow']

        # Cập nhật trạng thái cho các tài khoản đã chọn
        result = textnow_collection.update_many(
            {'_id': {'$in': [ObjectId(id) for id in ids]}},
            {'$set': {'status_account_TN': 'verified quay số'}}
        )

        return JsonResponse({
            'success': True,
            'message': f'Đã cập nhật {result.modified_count} tài khoản thành công'
        })

    except Exception as e:
        logger.error(f"Error in bulk_verify_success: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'message': f'Có lỗi xảy ra: {str(e)}'})
    finally:
        if client:
            try:
                client.close()
            except Exception as e:
                logger.error(f"Error closing MongoDB connection: {str(e)}")

@csrf_exempt
@require_POST
def bulk_verify_fail(request):
    client = None
    try:
        if not request.user.is_authenticated:
            return JsonResponse({'success': False, 'message': 'Chưa đăng nhập'})

        ids = request.POST.getlist('ids[]')
        if not ids:
            return JsonResponse({'success': False, 'message': 'Không có ID nào được chọn'})

        # Kết nối MongoDB
        client = MongoClient(
            settings.MONGODB_URI,
            username=settings.MONGODB_USERNAME,
            password=settings.MONGODB_PASSWORD,
            retryWrites=True,
            w='majority'
        )
        db = client[settings.MONGODB_DATABASE]
        textnow_collection = db['employee_textnow']

        # Cập nhật trạng thái cho các tài khoản đã chọn
        result = textnow_collection.update_many(
            {'_id': {'$in': [ObjectId(id) for id in ids]}},
            {'$set': {'status_account_TN': 'verified lỗi'}}
        )

        return JsonResponse({
            'success': True,
            'message': f'Đã cập nhật {result.modified_count} tài khoản thất bại'
        })

    except Exception as e:
        logger.error(f"Error in bulk_verify_fail: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'message': f'Có lỗi xảy ra: {str(e)}'})
    finally:
        if client:
            try:
                client.close()
            except Exception as e:
                logger.error(f"Error closing MongoDB connection: {str(e)}")