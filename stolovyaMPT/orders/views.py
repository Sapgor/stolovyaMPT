from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from .models import MenuItem, Order
from .forms import CustomerRegistrationForm
from django.shortcuts import get_object_or_404, redirect
from .models import MenuItem, Order, OrderItem
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import user_passes_test
from django.contrib import messages
from .models import CustomUser, MenuItem, Order, OrderItem
from .forms import CustomUserForm, MenuItemForm
from django.contrib.auth import login
from django.contrib.auth.backends import ModelBackend
from django.shortcuts import render
from django.http import HttpResponse
from orders.utils.ratelimit import rate_limit, ip_key, user_or_ip_key, user_key

User = get_user_model()

@rate_limit(key_func=ip_key, rate=5, period_seconds=60, block=True)
def register(request):
    if request.method == 'POST':
        form = CustomerRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            return redirect('menu')
    else:
        form = CustomerRegistrationForm()
    return render(request, 'registration/register.html', {'form': form})

def login_view(request):
    return render(request, 'registration/login.html')

@login_required
def menu_view(request):
    items = MenuItem.objects.all()
    return render(request, 'orders/menu.html', {'items': items})

@login_required
def profile_view(request):
    return render(request, 'orders/profile.html')

@login_required
def orders_view(request):
    if request.user.user_type == 'canteen_admin':
        orders = Order.objects.all().prefetch_related('orderitem_set__menu_item')
    else:
        orders = Order.objects.filter(customer=request.user).prefetch_related('orderitem_set__menu_item')
    return render(request, 'orders/orders.html', {'orders': orders})

@login_required
def canteen_admin_view(request):
    if request.user.user_type != 'canteen_admin':
        return redirect('menu')
    return render(request, 'orders/canteen_admin.html')

@rate_limit(key_func=ip_key, rate=5, period_seconds=60, block=True)
@login_required
def place_order(request, item_id):
    menu_item = get_object_or_404(MenuItem, id=item_id)

    if request.user.user_type != 'customer':
        return redirect('menu')

    if request.method == 'POST':
        quantity = int(request.POST.get('quantity', 1))

        if not menu_item.is_available(quantity):
            messages.error(request,
                           f"Простите, данная позиция закончилась или недостаточно в наличии. Осталось: {menu_item.stock} шт.")
            return redirect('menu')

        order, created = Order.objects.get_or_create(
            customer=request.user,
            status='ожидается'
        )

        order_item, created = OrderItem.objects.get_or_create(
            order=order,
            menu_item=menu_item,
            defaults={'quantity': quantity}
        )
        if not created:
            order_item.quantity += quantity
            order_item.save()

        menu_item.stock -= quantity
        menu_item.save()

        messages.success(request, f"Вы успешно заказали {menu_item.name} ({quantity} шт.)!")
        return redirect('orders')

    return redirect('menu')


@login_required
def toggle_order_status(request, order_id):
    if request.user.user_type != 'canteen_admin':
        return HttpResponseForbidden("Только администратор столовой может менять статус заказа.")

    order = get_object_or_404(Order, id=order_id)
    if order.status == 'ожидается':
        order.status = 'выдан'
    else:
        order.status = 'ожидается'
    order.save()
    return redirect('orders')

@rate_limit(key_func=ip_key, rate=5, period_seconds=60, block=True)
@login_required
def delete_order(request, order_id):
    if request.user.user_type != 'canteen_admin':
        return HttpResponseForbidden("Только администратор столовой может удалять заказы.")

    order = get_object_or_404(Order, id=order_id)
    order.delete()
    return redirect('orders')

def superuser_required(view_func):
    return user_passes_test(
        lambda u: u.is_superuser,
        login_url='login'
    )(view_func)

@superuser_required
def db_admin_panel(request):
    return render(request, 'orders/db_admin_panel.html')

# --- Пользователи ---
@rate_limit(key_func=ip_key, rate=5, period_seconds=60, block=True)
@superuser_required
def db_admin_users(request):
    users = CustomUser.objects.all()
    return render(request, 'orders/db_admin_users.html', {'users': users})

@rate_limit(key_func=ip_key, rate=5, period_seconds=60, block=True)
@superuser_required
def db_admin_create_user(request):
    if request.method == 'POST':
        form = CustomUserForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Пользователь создан!")
            return redirect('db_admin_users')
    else:
        form = CustomUserForm()
    return render(request, 'orders/db_admin_user_form.html', {'form': form, 'title': 'Создать пользователя'})

@rate_limit(key_func=ip_key, rate=5, period_seconds=60, block=True)
@superuser_required
def db_admin_edit_user(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id)
    if request.method == 'POST':
        form = CustomUserForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, "Пользователь обновлён!")
            return redirect('db_admin_users')
    else:
        form = CustomUserForm(instance=user)
    return render(request, 'orders/db_admin_user_form.html', {'form': form, 'title': 'Редактировать пользователя'})

@rate_limit(key_func=ip_key, rate=5, period_seconds=60, block=True)
@superuser_required
def db_admin_delete_user(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id)
    if request.method == 'POST':
        user.delete()
        messages.success(request, "Пользователь удалён!")
        return redirect('db_admin_users')
    return render(request, 'orders/db_admin_confirm_delete.html', {'obj': user, 'cancel_url': 'db_admin_users'})

# --- Блюда ---
@superuser_required
def db_admin_menu_items(request):
    items = MenuItem.objects.all()
    return render(request, 'orders/db_admin_menu_items.html', {'items': items})

@superuser_required
def db_admin_create_menu_item(request):
    if request.method == 'POST':
        form = MenuItemForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, "Блюдо создано!")
            return redirect('db_admin_menu_items')
    else:
        form = MenuItemForm()
    return render(request, 'orders/db_admin_menu_item_form.html', {'form': form, 'title': 'Создать блюдо'})

@superuser_required
def db_admin_edit_menu_item(request, item_id):
    item = get_object_or_404(MenuItem, id=item_id)
    if request.method == 'POST':
        form = MenuItemForm(request.POST, request.FILES, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, "Блюдо обновлено!")
            return redirect('db_admin_menu_items')
    else:
        form = MenuItemForm(instance=item)
    return render(request, 'orders/db_admin_menu_item_form.html', {'form': form, 'title': 'Редактировать блюдо'})

@superuser_required
def db_admin_delete_menu_item(request, item_id):
    item = get_object_or_404(MenuItem, id=item_id)
    if request.method == 'POST':
        item.delete()
        messages.success(request, "Блюдо удалено!")
        return redirect('db_admin_menu_items')
    return render(request, 'orders/db_admin_confirm_delete.html', {'obj': item, 'cancel_url': 'db_admin_menu_items'})

# --- Заказы ---
@superuser_required
def db_admin_orders(request):
    orders = Order.objects.all().prefetch_related('orderitem_set__menu_item', 'customer')
    return render(request, 'orders/db_admin_orders.html', {'orders': orders})

@superuser_required
def db_admin_toggle_order_status(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    order.status = 'выдан' if order.status == 'ожидается' else 'ожидается'
    order.save()
    return redirect('db_admin_orders')

def ratelimited_handler(request, exception):
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return HttpResponse(
            'Слишком много запросов. Пожалуйста, подождите 60 секунд.',
            status=429,
            content_type='text/plain'
        )
    return render(request, 'orders/ratelimited.html', status=429)

def error_404(request, exception):
    return render(request, 'orders/404.html', status=404)

def error_500(request):
    return render(request, 'orders/500.html', status=500)