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
logger = logging.getLogger(__name__)

@login_required
@role_required('admin','quanly','kiemtra')
def manager_textnow_view(request):
    try:
        # Test kết nối MongoDB
        client = MongoClient(settings.MONGODB_URI)
        db = client[settings.MONGODB_DATABASE]
        collection = db['employee_textnow']

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
        date_type = request.GET.get('date_type', 'single')
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        created_by = request.GET.get('created_by')
        search_query = request.GET.get('search', '')
        
        print("Search parameters:", {
            'status_tn': status_tn,
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
                date_count = collection.count_documents(date_query)
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
                date_count = collection.count_documents(date_query)
                print(f"Documents matching date range {start_date} to {end_date}:", date_count)
                query.update(date_query)
            except ValueError as e:
                print(f"Date range parsing error: {e}")
        
        # Xử lý các điều kiện tìm kiếm khác
        if status_tn:
            status_query = {'status_account_TN': status_tn}
            status_count = collection.count_documents(status_query)
            print(f"Documents matching status {status_tn}:", status_count)
            query.update(status_query)
        
        if created_by:
            creator_query = {'created_by': created_by}
            creator_count = collection.count_documents(creator_query)
            print(f"Documents matching creator {created_by}:", creator_count)
            query.update(creator_query)
            
        if search_query:
            text_query = {
                '$or': [
                    {'email': {'$regex': search_query, '$options': 'i'}},
                    {'textnow_username': {'$regex': search_query, '$options': 'i'}}
                ]
            }
            text_count = collection.count_documents(text_query)
            print(f"Documents matching search text {search_query}:", text_count)
            query.update(text_query)

        print("Final query:", query)
        
        # Thực hiện truy vấn
        employees = list(collection.find(query, projection))
        print(f"Found {len(employees)} documents with query conditions")

        # Format lại ngày
        for employee in employees:
            if '_id' in employee:
                employee['id'] = str(employee['_id'])
            if 'created_at' in employee:
                employee['created_at'] = datetime.strptime(employee['created_at'], '%Y-%m-%dT%H:%M:%S.%f')
        
        # Lấy danh sách người tạo và trạng thái
        creators = list(collection.distinct('created_by'))
        creators = sorted([creator for creator in creators if creator])
        
        status_list = list(collection.distinct('status_account_TN'))
        status_list = sorted([status for status in status_list if status])
        
        context = {
            'employees': employees,
            'date_type': date_type,
            'start_date': start_date,
            'end_date': end_date,
            'status_tn': status_tn,
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

# Thêm view xử lý xóa
@login_required
@role_required('admin','quanly','kiemtra')
def delete_employee(request):
    if request.method == 'POST':
        try:
            employee_id = request.POST.get('employee_id')
            client = MongoClient(settings.MONGODB_URI)
            db = client[settings.MONGODB_DATABASE]
            collection = db['employee_textnow']
            
            # Chuyển string ID thành ObjectId
            result = collection.delete_one({'_id': ObjectId(employee_id)})
            
            if result.deleted_count > 0:
                return JsonResponse({'status': 'success'})
            else:
                return JsonResponse({'status': 'error', 'message': 'Không tìm thấy bản ghi'})
                
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
    
    return JsonResponse({'status': 'error', 'message': 'Phương thức không được hỗ trợ'})

@csrf_exempt
@login_required
@role_required('admin','quanly','kiemtra')
def export_employee_textnow_excel(request):
    if request.method == 'POST':
        try:
            # Lấy danh sách ID từ request
            data = json.loads(request.body)
            selected_ids = data.get('selected_ids', [])

            # Kết nối MongoDB
            client = MongoClient(settings.MONGODB_URI)
            db = client[settings.MONGODB_DATABASE]
            collection = db['employee_textnow']

            # Truy vấn các bản ghi được chọn
            query = {'_id': {'$in': [ObjectId(id) for id in selected_ids]}}
            projection = {
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
            employees = list(collection.find(query, projection))

            # Tạo workbook Excel
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Employee Textnow"

            # Header
            headers = [
                "Email", "Password Email", "Password", "Password TF",
                "TN Status", "TF Status", "TN Sold", "TF Sold",
                "Người tạo", "Ngày tạo", "Thông tin"
            ]
            ws.append(headers)

            # Data rows
            for emp in employees:
                ws.append([
                    emp.get('email', ''),
                    emp.get('password_email', ''),
                    emp.get('password', ''),
                    emp.get('password_TF', ''),
                    emp.get('status_account_TN', ''),
                    emp.get('status_account_TF', ''),
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