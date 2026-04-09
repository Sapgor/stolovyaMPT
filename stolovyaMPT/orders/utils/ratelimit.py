# orders/utils/ratelimit.py
import time
from functools import wraps
from django.core.cache import cache
from django.http import HttpResponse
from django.conf import settings


def rate_limit(key_func, rate, period_seconds, block=True):
    """
    декоратор для ограничения запросов
    """

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            key = f"rl:{key_func(request)}:{view_func.__name__}"

            current = cache.get(key, 0)

            if current >= rate:
                if block:
                    return HttpResponse(
                        'Слишком много запросов. Пожалуйста, подождите 60 секунд.',
                        status=429,
                        content_type='text/plain; charset=utf-8'
                    )
                return view_func(request, *args, **kwargs)

            cache.set(key, current + 1, period_seconds)

            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator


def ip_key(request):
    """Получить ключ по IP"""
    return request.META.get('REMOTE_ADDR', 'unknown')


def user_or_ip_key(request):
    """Получить ключ по пользователю или IP"""
    if request.user.is_authenticated:
        return f"user:{request.user.id}"
    return f"ip:{request.META.get('REMOTE_ADDR', 'unknown')}"


def user_key(request):
    """Получить ключ по пользователю"""
    if request.user.is_authenticated:
        return f"user:{request.user.id}"
    return 'anonymous'