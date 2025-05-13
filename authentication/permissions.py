from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from .views.mongodb_employee import get_collection_handle_employee
# Define user roles
ROLES = {
    'admin': ['admin', 'quanly', 'kiemtra', 'nhanvien'],  # Admin có quyền truy cập tất cả
    'quanly': ['quanly', 'kiemtra', 'nhanvien'],  # Quản lý có quyền truy cập trừ admin
    'kiemtra': ['kiemtra', 'nhanvien'],  # Kiểm tra có quyền truy cập verified và nhanvien
    'nhanvien': ['nhanvien']  # Nhân viên chỉ có quyền truy cập chức năng của mình
}

# Define allowed status updates for each role
ALLOWED_STATUS_UPDATES = {
    'admin': ['Chưa sử dụng', 'Đã đăng ký', 'Email lỗi', 'Đã kiểm tra', 'Kiểm tra lỗi', 'Đã xử lý', 'Đang xử lý', 'Chưa xử lý'],
    'quanly': ['Chưa sử dụng', 'Đã đăng ký', 'Email lỗi', 'Đã kiểm tra', 'Kiểm tra lỗi', 'Đã xử lý', 'Đang xử lý', 'Chưa xử lý'],
    'kiemtra': ['Đã kiểm tra', 'Kiểm tra lỗi', 'Đã xử lý', 'Đang xử lý'],
    'nhanvien': ['Đã đăng ký', 'Email lỗi', 'Đang xử lý']
}

def get_user_role(user_id):
    """Get user role from MongoDB"""
    try:
        users_collection = get_collection_handle_employee('users')
        if users_collection is None:
            return 'nhanvien'
            
        user_data = users_collection.find_one({'user_id': str(user_id)})
        return user_data.get('role', 'nhanvien') if user_data else 'nhanvien'
    except Exception as e:
        print(f"Error getting user role: {e}")
        return 'nhanvien'

def role_required(required_roles):
    """Decorator to check if user has required role(s)"""
    # Convert single role to list for consistent handling
    if isinstance(required_roles, str):
        required_roles = [required_roles]
        
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            
            user_role = get_user_role(request.user.id)
            allowed_roles = ROLES.get(user_role, [])
            
            # Check if any of the required roles are allowed
            if not any(role in allowed_roles for role in required_roles):
                messages.error(request, 'Bạn không có quyền thực hiện chức năng này')
                return redirect('home')
            
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator

def can_manage_users(user_id):
    """Check if user can manage other users"""
    user_role = get_user_role(user_id)
    print(user_role)
    return user_role in ['admin', 'quanly']

def can_update_status(user_id):
    """Check if user can update status"""
    user_role = get_user_role(user_id)
    return True  # All roles can update status, but with different permissions

def get_allowed_status_updates(user_id):
    """Get list of status updates allowed for user"""
    user_role = get_user_role(user_id)
    return ALLOWED_STATUS_UPDATES.get(user_role, []) 