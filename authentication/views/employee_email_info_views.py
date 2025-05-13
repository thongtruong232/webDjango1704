from django.http import JsonResponse
from django.utils.dateparse import parse_date
from django.utils.timezone import datetime
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.conf import settings
import pymongo

@api_view(['GET'])
def check_employee_password_today(request):
    try:
        # Kết nối tới MongoDB
        client = pymongo.MongoClient(settings.MONGODB_URI)
        db = client[settings.MONGODB_DATABASE]
        collection = db['employee_passwordregproduct']

        # Lấy ngày hiện tại
        today = datetime.now().strftime('%d/%m/%Y')
        
        # Tìm bản ghi với use_at là ngày hôm nay
        employee_password = collection.find_one({
            'use_at': today,
            'type': 'TextFree'
        })
        if employee_password:
           employee_password = collection.find_one({
            'use_at': today,
            'type': 'TextNow'
           })
           print("oke")
           if employee_password:
              return JsonResponse({
                    'success': True,
                    'has_record': employee_password is not None,
                    'message': 'Đã kiểm tra bản ghi thành công'
                })
           else:
                return JsonResponse({
                'success': False,
                'error': 'Không tìm thấy mật khẩu Tn cho ngày hôm nay'
            })
        else:
                return JsonResponse({
                'success': False,
                'error': 'Không tìm thấy mật khẩu Tf cho ngày hôm nay'
            })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })
    finally:
        # Đóng kết nối MongoDB
        if 'client' in locals():
            client.close()

@api_view(['GET'])
def get_employee_passwords(request):
    try:
        # Kết nối tới MongoDB
        client = pymongo.MongoClient(settings.MONGODB_URI)
        db = client[settings.MONGODB_DATABASE]
        collection = db['employee_passwordregproduct']

        # Lấy ngày hiện tại
        today = datetime.now().strftime('%d/%m/%Y')
        
        # Tìm bản ghi với use_at là ngày hôm nay và type là TextNow
        employee_password_Tn = collection.find_one({
            'use_at': today,
            'type': 'TextNow'
        })
        
        employee_password_Tf = collection.find_one({
            'use_at': today,
            'type': 'TextFree'
        })
        print(employee_password_Tn)
        print(employee_password_Tf)
        if employee_password_Tn or employee_password_Tf:
            return JsonResponse({
                'success': True,
                'pass_tn': employee_password_Tn['password'],
                'pass_tf': employee_password_Tf['password'],
                'message': 'Đã lấy mật khẩu thành công'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Không tìm thấy mật khẩu cho ngày hôm nay'
            })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })
    finally:
        # Đóng kết nối MongoDB
        if 'client' in locals():
            client.close()

@api_view(['GET'])
def get_random_area_phones(request):
    try:
        # Lấy số lượng từ query parameter, mặc định là 5 nếu không có
        quantity = int(request.GET.get('quantity', 5))
        
        # Kết nối tới MongoDB
        client = pymongo.MongoClient(settings.MONGODB_URI)
        db = client[settings.MONGODB_DATABASE]
        collection = db['area_phone']

        # Sử dụng $sample để lấy random records
        random_records = list(collection.aggregate([
            {'$sample': {'size': quantity}}
        ]))
        for record in random_records:
            record['_id'] = str(record['_id'])
        if random_records:
            return JsonResponse({
                'success': True,
                'data': random_records,
                'message': f'Đã lấy {len(random_records)} bản ghi area_phone ngẫu nhiên'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Không tìm thấy bản ghi area_phone nào'
            })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })
    finally:
        # Đóng kết nối MongoDB
        if 'client' in locals():
            client.close()

