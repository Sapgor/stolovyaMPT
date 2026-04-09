from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
from django.conf.urls.static import static

urlpatterns = [
    path('', views.menu_view, name='menu'),
    path('register/', views.register, name='register'),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('profile/', views.profile_view, name='profile'),
    path('orders/', views.orders_view, name='orders'),
    path('canteen/', views.canteen_admin_view, name='canteen_admin'),
    path('order/<int:item_id>/', views.place_order, name='place_order'),
    path('order/toggle-status/<int:order_id>/', views.toggle_order_status, name='toggle_order_status'),
    path('order/delete/<int:order_id>/', views.delete_order, name='delete_order'),

    # --- Панель администратора БД (полный доступ) ---
    path('db-admin/', views.db_admin_panel, name='db_admin_panel'),

    # Управление пользователями
    path('db-admin/users/', views.db_admin_users, name='db_admin_users'),
    path('db-admin/users/create/', views.db_admin_create_user, name='db_admin_create_user'),
    path('db-admin/users/edit/<int:user_id>/', views.db_admin_edit_user, name='db_admin_edit_user'),
    path('db-admin/users/delete/<int:user_id>/', views.db_admin_delete_user, name='db_admin_delete_user'),

    # Управление блюдами
    path('db-admin/menu-items/', views.db_admin_menu_items, name='db_admin_menu_items'),
    path('db-admin/menu-items/create/', views.db_admin_create_menu_item, name='db_admin_create_menu_item'),
    path('db-admin/menu-items/edit/<int:item_id>/', views.db_admin_edit_menu_item, name='db_admin_edit_menu_item'),
    path('db-admin/menu-items/delete/<int:item_id>/', views.db_admin_delete_menu_item,
         name='db_admin_delete_menu_item'),

    # Управление заказами
    path('db-admin/orders/', views.db_admin_orders, name='db_admin_orders'),
    path('db-admin/orders/toggle-status/<int:order_id>/', views.db_admin_toggle_order_status,
         name='db_admin_toggle_order_status'),
]