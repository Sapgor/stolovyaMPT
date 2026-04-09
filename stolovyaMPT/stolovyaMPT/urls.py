from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

handler429 = 'orders.views.ratelimited_handler'
handler404 = 'orders.views.error_404'
handler500 = 'orders.views.error_500'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('orders.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)