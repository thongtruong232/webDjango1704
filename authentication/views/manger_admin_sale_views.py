from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from pymongo import MongoClient
from datetime import datetime, timedelta
from django.conf import settings
import logging
from django.http import JsonResponse, HttpResponse
from bson.objectid import ObjectId
import openpyxl
from openpyxl.utils import get_column_letter
from django.views.decorators.csrf import csrf_exempt
import json
from authentication.permissions import (
    role_required, can_manage_users, can_update_status, 
    ROLES, get_allowed_status_updates
)
from authentication.mongodb import get_collection_handle

logger = logging.getLogger(__name__)

# Singleton MongoDB client
_mongo_client = None

def get_mongo_client():
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = MongoClient(settings.MONGODB_URI)
    return _mongo_client

@login_required
@role_required('kiemtra')  # Yêu cầu quyền admin
def manager_textnow_view(request):
    try:
        # Test kết nối MongoDB
        text_now_collection, client = get_collection_handle('employee_textnow')

        # Định nghĩa projection ngay từ đầu
        projection = {
            '_id': 1,
            'email': 1,
            'password_email': 1,
            'password': 1,
            'password_TF': 1,
            'status_account_TN': 1,
            'status_account_TF': 1,
            'created_at': 1,
            'created_by': 1,
            'full_information': 1,
            'sold_status_TN': 1,
            'sold_status_TF': 1
        }

        # Lấy tham số tìm kiếm từ request
        status_tn = request.GET.get('status_tn')
        status_tf = request.GET.get('status_tf')
        sold_status_tn = request.GET.get('sold_status_tn')
        sold_status_tf = request.GET.get('sold_status_tf')
        date_type = request.GET.get('date_type', 'single')
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        created_by = request.GET.get('created_by')
        search_query = request.GET.get('search', '')
        
        print("Search parameters:", {
            'status_tn': status_tn,
            'status_tf': status_tf,
            'sold_status_tn': sold_status_tn,
            'sold_status_tf': sold_status_tf,
            'date_type': date_type,
            'start_date': start_date,
            'end_date': end_date,
            'created_by': created_by,
            'search_query': search_query
        })
        
        # Xây dựng query
        query = {}
        
        # Xử lý query theo thời gian
        if date_type == 'single' and start_date:
            try:
                date_query = {'created_at': {'$regex': f'^{start_date}'}}
                date_count = text_now_collection.count_documents(date_query)
                print(f"Documents matching single date {start_date}:", date_count)
                query.update(date_query)
            except ValueError as e:
                print(f"Single date parsing error: {e}")
        elif date_type == 'range' and start_date and end_date:
            try:
                start = datetime.strptime(start_date, '%Y-%m-%d')
                end = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
                date_query = {
                    'created_at': {
                        '$gte': start.strftime('%Y-%m-%d'),
                        '$lt': end.strftime('%Y-%m-%d')
                    }
                }
                date_count = text_now_collection.count_documents(date_query)
                print(f"Documents matching date range {start_date} to {end_date}:", date_count)
                query.update(date_query)
            except ValueError as e:
                print(f"Date range parsing error: {e}")
        
        # Xử lý các điều kiện tìm kiếm khác
        if status_tn:
            status_query = {'status_account_TN': status_tn}
            status_count = text_now_collection.count_documents(status_query)
            print(f"Documents matching TN status {status_tn}:", status_count)
            query.update(status_query)
            
        if status_tf:
            status_query = {'status_account_TF': status_tf}
            status_count = text_now_collection.count_documents(status_query)
            print(f"Documents matching TF status {status_tf}:", status_count)
            query.update(status_query)

        if sold_status_tn:
            sold_status = sold_status_tn.lower() == 'true'
            sold_query = {'sold_status_TN': sold_status}
            sold_count = text_now_collection.count_documents(sold_query)
            print(f"Documents matching TN sold status {sold_status}:", sold_count)
            query.update(sold_query)

        if sold_status_tf:
            sold_status = sold_status_tf.lower() == 'true'
            sold_query = {'sold_status_TF': sold_status}
            sold_count = text_now_collection.count_documents(sold_query)
            print(f"Documents matching TF sold status {sold_status}:", sold_count)
            query.update(sold_query)
        
        if created_by:
            creator_query = {'created_by': created_by}
            creator_count = text_now_collection.count_documents(creator_query)
            print(f"Documents matching creator {created_by}:", creator_count)
            query.update(creator_query)
            
        if search_query:
            text_query = {
                '$or': [
                    {'email': {'$regex': search_query, '$options': 'i'}},
                    {'textnow_username': {'$regex': search_query, '$options': 'i'}}
                ]
            }
            text_count = text_now_collection.count_documents(text_query)
            print(f"Documents matching search text {search_query}:", text_count)
            query.update(text_query)

        print("Final query:", query)
        
        # Thực hiện truy vấn
        employees = list(text_now_collection.find(query, projection))
        print(f"Found {len(employees)} documents with query conditions")

        # Format lại ngày
        for employee in employees:
            if '_id' in employee:
                employee['id'] = str(employee['_id'])
            if 'created_at' in employee:
                employee['created_at'] = datetime.strptime(employee['created_at'], '%Y-%m-%dT%H:%M:%S.%f')
        
        # Lấy danh sách người tạo và trạng thái
        creators = list(text_now_collection.distinct('created_by'))
        creators = sorted([creator for creator in creators if creator])
        
        # Lấy danh sách trạng thái từ cả TN và TF
        status_list = list(set(
            list(text_now_collection.distinct('status_account_TN')) + 
            list(text_now_collection.distinct('status_account_TF'))
        ))
        status_list = sorted([status for status in status_list if status])
  
        users_collection, client = get_collection_handle('users')
        user_data = users_collection.find_one({'user_id': str(request.user.id)})
        context = {
            'user_data': user_data,
            'employees': employees,
            'date_type': date_type,
            'start_date': start_date,
            'end_date': end_date,
            'status_tn': status_tn,
            'status_tf': status_tf,
            'sold_status_tn': sold_status_tn,
            'sold_status_tf': sold_status_tf,
            'status_list': status_list,
            'created_by': created_by,
            'search_query': search_query,
            'creators': creators
        }
        
        return render(request, 'authentication/manager_textnow_admin_sale.html', context)
        
    except Exception as e:
        print(f"Error in query: {str(e)}")
        logger.error(f"Error in manager_textnow_view: {str(e)}", exc_info=True)
        context = {
            'error': f'Lỗi: {str(e)}'
        }
        return render(request, 'authentication/manager_textnow_admin_sale.html', context)

@login_required
@role_required('quanly')  # Yêu cầu quyền admin
def delete_employee(request):
    if request.method == 'POST':
        try:
            employee_id = request.POST.get('employee_id')
            text_now_collection, client = get_collection_handle('employee_textnow')
            
            # Chuyển string ID thành ObjectId
            result = text_now_collection.delete_one({'_id': ObjectId(employee_id)})
            
            if result.deleted_count > 0:
                return JsonResponse({'status': 'success'})
            else:
                return JsonResponse({'status': 'error', 'message': 'Không tìm thấy bản ghi'})
                
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
    
    return JsonResponse({'status': 'error', 'message': 'Phương thức không được hỗ trợ'})

@csrf_exempt
@login_required
@role_required('quanly')  # Yêu cầu quyền admin
def export_employee_textnow_excel(request):
    if request.method == 'POST':
        try:
            # Lấy danh sách ID từ request
            data = json.loads(request.body)
            selected_ids = data.get('selected_ids', [])

            # Kết nối MongoDB
            text_now_collection, client = get_collection_handle('employee_textnow')

            # Truy vấn các bản ghi được chọn
            query = {'_id': {'$in': [ObjectId(id) for id in selected_ids]}}
            projection = {
                'email': 1,
                'password_email': 1,
                'password': 1,
                'password_TF': 1,
                'status_account_TN': 1,
                'status_account_TF': 1,
                'area_phone': 1,
                'created_at': 1,
                'created_by': 1,
                'full_information': 1,
                'sold_status_TN': 1,
                'sold_status_TF': 1
            }
            employees = list(text_now_collection.find(query, projection))

            # Tạo workbook Excel
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Employee Textnow"

            # Header
            headers = [
                "Email", "Password Email", "Đầu số mã vùng", "Password", "Password TF",
                "TN Sold", "TF Sold","Người tạo", "Ngày tạo", "Thông tin", 
            ]
            ws.append(headers)

            # Data rows
            for emp in employees:
                ws.append([
                    emp.get('email', ''),
                    emp.get('password_email', ''),
                    emp.get('area_phone', ''),
                    emp.get('password', ''),
                    emp.get('password_TF', ''),
                    emp.get('sold_status_TN', ''),
                    emp.get('sold_status_TF', ''),
                    emp.get('created_by', ''),
                    emp.get('created_at', ''),
                    emp.get('full_information', '')
                ])

            # Auto width cho các cột
            for col in ws.columns:
                max_length = 0
                column = col[0].column_letter
                for cell in col:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                ws.column_dimensions[column].width = max_length + 2

            # Xuất file
            response = HttpResponse(
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = 'attachment; filename=employee_textnow.xlsx'
            wb.save(response)
            return response
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})

    return JsonResponse({'status': 'error', 'message': 'Phương thức không được hỗ trợ'})

@csrf_exempt
@login_required
@role_required('quanly')  # Yêu cầu quyền admin
def update_sold_status(request):
    if request.method == 'POST':
        try:
            # Lấy dữ liệu từ request
            data = json.loads(request.body)
            employee_ids = data.get('employee_ids', [])
            sold_status = data.get('sold_status', True)
            type = data.get('type', 'TN')  # Mặc định là TN nếu không có type

            # Kết nối MongoDB
            text_now_collection, client = get_collection_handle('employee_textnow')

            # Xác định trường cần cập nhật dựa vào type
            update_field = 'sold_status_TF' if type == 'TF' else 'sold_status_TN'

            # Cập nhật trạng thái cho các record được chọn
            result = text_now_collection.update_many(
                {'_id': {'$in': [ObjectId(id) for id in employee_ids]}},
                {'$set': {update_field: sold_status}}
            )

            if result.modified_count > 0:
                return JsonResponse({
                    'status': 'success',
                    'message': f'Đã cập nhật {result.modified_count} record'
                })
            else:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Không có record nào được cập nhật'
                })

        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            })

    return JsonResponse({
        'status': 'error',
        'message': 'Phương thức không được hỗ trợ'
    })

@login_required
@role_required('kiemtra')  # Yêu cầu quyền admin
def get_sold_status_counts(request):
    try:
        # Kết nối MongoDB
        text_now_collection, client = get_collection_handle('employee_textnow')
        
        # Đếm số lượng record theo sold_status_TN và sold_status_TF
        tn_sold = text_now_collection.count_documents({'sold_status_TN': True})
        tn_unsold = text_now_collection.count_documents({'sold_status_TN': False})
        tf_sold = text_now_collection.count_documents({'sold_status_TF': True})
        tf_unsold = text_now_collection.count_documents({'sold_status_TF': False})
        
        return JsonResponse({
            'status': 'success',
            'counts': {
                'tn_sold': tn_sold,
                'tn_unsold': tn_unsold,
                'tf_sold': tf_sold,
                'tf_unsold': tf_unsold
            }
        })
        
    except Exception as e:
        logger.error(f"Error in get_sold_status_counts: {str(e)}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)

def get_total_textnow_status_counts(request):
    try:
        # Lấy type từ query parameter
        type = request.GET.get('type', 'TN').upper()  # Mặc định là TN nếu không có type
        
        # Kết nối MongoDB
        text_now_collection, client = get_collection_handle('employee_textnow')

        # Lấy ngày hiện tại
        today = datetime.now()
        
        # Xác định trường sold_status dựa vào type
        sold_status_field = 'sold_status_TN' if type == 'TN' else 'sold_status_TF'
        
        # Sử dụng aggregation để nhóm theo ngày và đếm số lượng record
        pipeline = [
            {
                '$match': {
                    sold_status_field: False
                }
            },
            {
                '$addFields': {
                    'parsed_date': {
                        '$dateFromString': {
                            'dateString': {
                                '$substr': ['$created_at', 0, 10]  # Lấy phần YYYY-MM-DD
                            },
                            'format': '%Y-%m-%d'
                        }
                    }
                }
            },
            {
                '$group': {
                    '_id': {
                        '$dateToString': {
                            'format': '%d-%m-%Y',
                            'date': '$parsed_date'
                        }
                    },
                    'count': {'$sum': 1},
                    'date_obj': {'$first': '$parsed_date'}  # Lưu lại đối tượng date để so sánh
                }
            },
            {
                '$project': {
                    '_id': 0,
                    'date': '$_id',
                    'count': 1,
                    'date_obj': 1
                }
            },
            {
                '$sort': {
                    'date': -1  # Sắp xếp theo ngày giảm dần
                }
            }
        ]
        
        # Thực hiện aggregation
        results = list(text_now_collection.aggregate(pipeline))
        
        # Xử lý thêm thuộc tính check_add_area_phone
        for result in results:
            # Chuyển đổi date_obj từ MongoDB date sang Python datetime
            result_date = result['date_obj']
            # Tính số ngày chênh lệch
            days_diff = (today - result_date).days
            # Thêm thuộc tính check_add_area_phone nếu cách hơn 5 ngày
            if days_diff > 5 and type == 'TN':
                result['check_add_area_phone'] = True
            else:
                result['check_add_area_phone'] = False
            # Xóa trường date_obj vì không cần thiết trong response
            del result['date_obj']
        
        return JsonResponse({
            'status': 'success',
            'dates': results,
            'type': type
        })
        
    except Exception as e:
        logger.error(f"Error in get_total_textnow_status_counts: {str(e)}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)
