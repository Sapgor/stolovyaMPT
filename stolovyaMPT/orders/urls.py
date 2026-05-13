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
    path('change-password/', views.change_password_view, name='change_password'),
    path('change-email/', views.change_email_view, name='change_email'),
    path('settings/', views.settings_view, name='settings'),
    path('favorites/', views.favorites_view, name='favorites'),
    path('toggle-favorite/<int:item_id>/', views.toggle_favorite, name='toggle_favorite'),
    path('pre-order/', views.pre_order_view, name='pre_order'),
    path('pre-orders/', views.pre_orders_view, name='pre_orders'),
    path('orders/', views.orders_view, name='orders'),
    path('canteen/', views.canteen_admin_view, name='canteen_admin'),
    path('order/<int:item_id>/', views.place_order, name='place_order'),
    path('order/toggle-status/<int:order_id>/', views.toggle_order_status, name='toggle_order_status'),
    path('order/delete/<int:order_id>/', views.delete_order, name='delete_order'),
    path('update-stock/<int:item_id>/', views.update_stock, name='update_stock'),

    path('review/add/<int:item_id>/', views.add_review, name='add_review'),
    path('review/delete/<int:item_id>/', views.delete_review, name='delete_review'),

    path('db-admin/', views.db_admin_panel, name='db_admin_panel'),

    path('db-admin/users/', views.db_admin_users, name='db_admin_users'),
    path('db-admin/users/create/', views.db_admin_create_user, name='db_admin_create_user'),
    path('db-admin/users/edit/<int:user_id>/', views.db_admin_edit_user, name='db_admin_edit_user'),
    path('db-admin/users/delete/<int:user_id>/', views.db_admin_delete_user, name='db_admin_delete_user'),

    path('db-admin/menu-items/', views.db_admin_menu_items, name='db_admin_menu_items'),
    path('db-admin/menu-items/create/', views.db_admin_create_menu_item, name='db_admin_create_menu_item'),
    path('db-admin/menu-items/edit/<int:item_id>/', views.db_admin_edit_menu_item, name='db_admin_edit_menu_item'),
    path('db-admin/menu-items/delete/<int:item_id>/', views.db_admin_delete_menu_item,
         name='db_admin_delete_menu_item'),

    path('db-admin/orders/', views.db_admin_orders, name='db_admin_orders'),
    path('db-admin/orders/toggle-status/<int:order_id>/', views.db_admin_toggle_order_status,
         name='db_admin_toggle_order_status'),

    path('reports/sales/', views.sales_report, name='sales_report'),

    path('support/create/', views.create_support_request, name='create_support_request'),
    path('support/', views.support_dashboard, name='support_dashboard'),
    path('support/respond/<int:request_id>/', views.respond_support_request, name='respond_support_request'),
    path('support/send-message/<int:request_id>/', views.send_support_message, name='send_support_message'),
    path('support/my-requests/', views.customer_support_requests, name='customer_support_requests'),
    path('support/chat/<int:request_id>/', views.support_chat, name='support_chat'),

    path('password-reset/', views.password_reset_request, name='password_reset_request'),
    path('password-reset/verify/', views.password_reset_verify, name='password_reset_verify'),

    path('recommendations/', views.recommendations_view, name='recommendations'),
    path('update-recommendations/', views.update_recommendations, name='update_recommendations'),
    path('popular-items/', views.popular_items_view, name='popular_items'),
    path('trending-items/', views.trending_items_view, name='trending_items'),
    
    path('admin/recommendations/', views.admin_recommendations_settings, name='admin_recommendations_settings'),
    path('admin/update-popularity/', views.admin_update_popularity, name='admin_update_popularity'),
]