from django.test import TestCase

# Create your tests here.
def render_manage_users(request, extra_context=None):
    # Lấy thông tin người dùng hiện tại
    current_user = request.user  # Đối tượng User của người dùng hiện tại
    username = current_user.username
    email = current_user.email
    first_name = current_user.first_name
    last_name = current_user.last_name
    is_authenticated = current_user.is_authenticated  # Kiểm tra người dùng đã đăng nhập hay chưa


    print(f'request: {request}')
    print(f'current_user: {current_user}')
    print(f'username: {username}')
    print(f'email: {email}')
    print(f'first_name: {first_name}')
    print(f'last_name: {last_name}')
    print(f'is_authenticated: {is_authenticated}')
    # Truyền thông tin người dùng vào context
    context = {
        'username': username,
        'email': email,
        'first_name': first_name,
        'last_name': last_name,
        'is_authenticated': is_authenticated,
    }

    # Bạn cũng có thể lấy thêm các thông tin khác về người dùng
    # Chẳng hạn, role (nếu bạn có định nghĩa role tùy chỉnh)

    if extra_context:
        context.update(extra_context)
