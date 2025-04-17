def user_data_context(request):
    if request.user.is_authenticated:
        return {'user_data': request.user}
    return {}