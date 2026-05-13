from django.shortcuts import render, redirect
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordChangeForm, PasswordResetForm
from django.db.models import Q, Avg
from .models import MenuItem, Order, PasswordResetCode
from .forms import CustomerRegistrationForm
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.contrib.auth import views as auth_views
from django.shortcuts import get_object_or_404, redirect
from .models import MenuItem, Order, OrderItem
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import user_passes_test
from django.contrib import messages
from .models import CustomUser, MenuItem, Order, OrderItem, PreOrder, PreOrderItem, Review, SupportRequest, SupportMessage
from django.utils import timezone
from datetime import datetime, time
from .forms import CustomUserForm, MenuItemForm, EmailChangeForm
from django.contrib.auth import login
from django.contrib.auth.backends import ModelBackend
from django.shortcuts import render
from django.http import HttpResponse
from orders.utils.ratelimit import rate_limit, ip_key, user_or_ip_key, user_key
from .recommendations import RecommendationEngine

User = get_user_model()

def send_order_receipt_email(order, order_item, menu_item, quantity):
    try:
        total_price = menu_item.price * quantity
        
        subject = f'Чек заказа #{order.id} - Столовая МПТ'
        
        message = f'''
Здравствуйте, {order.customer.username}!

Спасибо за ваш заказ в столовой МПТ!

ДЕТАЛИ ЗАКАЗА:
================
Номер заказа: #{order.id}
Дата заказа: {order.order_date.strftime('%d.%m.%Y %H:%M')}

ПОЗИЦИИ ЗАКАЗА:
================
{menu_item.name}
Количество: {quantity} шт.
Цена за единицу: {menu_item.price:.2f} руб.
Сумма: {total_price:.2f} руб.

Способ оплаты: Банковская карта

Статус заказа: {order.status}

Спасибо за покупку! Ваш заказ готовится.

С уважением,
Команда Столовой МПТ
        '''
        
        send_mail(
            subject,
            message.strip(),
            settings.DEFAULT_FROM_EMAIL,
            [order.customer.email],
            fail_silently=False,
        )
        print(f"Чек отправлен на email {order.customer.email} для заказа #{order.id}")
        
    except Exception as e:
        print(f"Ошибка отправки чека: {e}")

def send_pre_order_receipt_email(pre_order, menu_items):
    try:
        subject = f'Чек предзаказа #{pre_order.id} - Столовая МПТ'
        
        items_text = ""
        for item_id, item_data in menu_items.items():
            item = item_data['item']
            quantity = item_data['quantity']
            total = item.price * quantity
            items_text += f"""
{item.name}
Количество: {quantity} шт.
Цена за единицу: {item.price:.2f} руб.
Сумма: {total:.2f} руб.
----------------
"""
        
        message = f'''
Здравствуйте, {pre_order.customer.username}!

Спасибо за ваш предзаказ в столовой МПТ!

ДЕТАЛИ ПРЕДЗАКАЗА:
==================
Номер предзаказа: #{pre_order.id}
Дата оформления: {pre_order.order_date.strftime('%d.%m.%Y %H:%M')}
Время получения: {pre_order.pickup_time.strftime('%d.%m.%Y %H:%M')}

ПОЗИЦИИ ПРЕДЗАКАЗА:
======================
{items_text}
Общая сумма: {pre_order.total_price:.2f} руб.

Способ оплаты: Банковская карта

Статус предзаказа: {pre_order.status}

Пожалуйста, придите за заказом в указанное время.

С уважением,
Команда Столовой МПТ
        '''
        
        send_mail(
            subject,
            message.strip(),
            settings.DEFAULT_FROM_EMAIL,
            [pre_order.customer.email],
            fail_silently=False,
        )
        print(f"Чек предзаказа отправлен на email {pre_order.customer.email} для предзаказа #{pre_order.id}")
        
    except Exception as e:
        print(f"Ошибка отправки чека предзаказа: {e}")

@rate_limit(key_func=ip_key, rate=5, period_seconds=60, block=True)
def register(request):
    if request.method == 'POST':
        form = CustomerRegistrationForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            
            if CustomUser.objects.filter(email=email).exists():
                messages.error(request, 'Этот email уже используется. Пожалуйста, используйте другой email или войдите в существующий аккаунт.')
                return render(request, 'registration/register.html', {'form': form})
            
            user = form.save()
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(request, 'Регистрация успешна! Добро пожаловать в Столовую МПТ!')
            return redirect('menu')
    else:
        form = CustomerRegistrationForm()
    return render(request, 'registration/register.html', {'form': form})

def login_view(request):
    return render(request, 'registration/login.html')

@login_required
def pre_order_view(request):
    if request.method == 'POST':
        menu_items = {}
        total_price = 0
        
        for key, value in request.POST.items():
            if key.startswith('quantity_') and value:
                item_id = key.split('_')[1]
                try:
                    item = MenuItem.objects.get(id=item_id)
                    quantity = int(value)
                    if quantity > 0 and item.stock >= quantity:
                        menu_items[item_id] = {'item': item, 'quantity': quantity}
                        total_price += item.price * quantity
                except (MenuItem.DoesNotExist, ValueError):
                    continue
        
        if menu_items:
            pickup_time_str = request.POST.get('pickup_time', '')
            payment_method = request.POST.get('payment_method', 'cash')
            notes = request.POST.get('notes', '')
            
            try:
                pickup_time = datetime.strptime(pickup_time_str, '%Y-%m-%d %H:%M').replace(tzinfo=timezone.get_current_timezone())
                
                if pickup_time <= timezone.now():
                    messages.error(request, 'Время получения должно быть в будущем')
                else:
                    pre_order = PreOrder.objects.create(
                        customer=request.user,
                        pickup_time=pickup_time,
                        total_price=total_price,
                        payment_method=payment_method,
                        notes=notes,
                        status='pending'
                    )
                    
                    for item_id, item_data in menu_items.items():
                        PreOrderItem.objects.create(
                            pre_order=pre_order,
                            menu_item=item_data['item'],
                            quantity=item_data['quantity']
                        )
                    
                    if payment_method == 'card':
                        send_pre_order_receipt_email(pre_order, menu_items)
                    
                    messages.success(request, f'Предзаказ #{pre_order.id} успешно оформлен!')
                    return redirect('pre_orders')
                    
            except ValueError:
                messages.error(request, 'Неверный формат времени. Используйте ГГГГ-ММ-ДД ЧЧ:ММ')
        else:
            messages.error(request, 'Выберите хотя бы один товар')
    
    items = MenuItem.objects.filter(stock__gt=0)
    return render(request, 'orders/pre_order.html', {'items': items})

@login_required
def pre_orders_view(request):
    if request.user.user_type == 'canteen_admin':
        pre_orders = PreOrder.objects.all().prefetch_related('preorderitem_set__menu_item', 'customer').order_by('-order_date')
    else:
        pre_orders = PreOrder.objects.filter(customer=request.user).prefetch_related('preorderitem_set__menu_item', 'customer').order_by('-order_date')
    return render(request, 'orders/pre_orders.html', {'pre_orders': pre_orders})

@login_required
def toggle_favorite(request, item_id):
    item = get_object_or_404(MenuItem, id=item_id)
    if item in request.user.favorites.all():
        request.user.favorites.remove(item)
        messages.success(request, f"{item.name} удалено из избранного")
    else:
        request.user.favorites.add(item)
        messages.success(request, f"{item.name} добавлено в избранное")
    return redirect(request.META.get('HTTP_REFERER', 'menu'))

@login_required
def favorites_view(request):
    items = request.user.favorites.all()
    return render(request, 'orders/favorites.html', {'items': items})

@login_required
def menu_view(request):
    items = MenuItem.objects.all()

    search = request.GET.get('search', '').strip()
    if search:
        items = items.filter(
            Q(name__icontains=search) | Q(description__icontains=search)
        )

    if request.GET.get('in_stock') == '1':
        items = items.filter(stock__gt=0)

    sort = request.GET.get('sort', 'default')
    if sort == 'price_asc':
        items = items.order_by('price')
    elif sort == 'price_desc':
        items = items.order_by('-price')
    elif sort == 'name':
        items = items.order_by('name')

    favorite_ids = set()
    if request.user.is_authenticated:
        favorite_ids = set(request.user.favorites.values_list('id', flat=True))

    return render(request, 'orders/menu.html', {'items': items, 'search': search, 'sort': sort, 'in_stock': request.GET.get('in_stock') == '1', 'favorite_ids': favorite_ids})

@login_required
def profile_view(request):
    return render(request, 'orders/profile.html')

@login_required
def change_password_view(request):
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, 'Пароль успешно изменён!')
            return redirect('profile')
        else:
            messages.error(request, 'Пожалуйста, исправьте ошибки ниже.')
    else:
        form = PasswordChangeForm(request.user)
    return render(request, 'orders/change_password.html', {'form': form})

@login_required
def change_email_view(request):
    if request.method == 'POST':
        form = EmailChangeForm(request.user, request.POST)
        if form.is_valid():
            new_email = form.cleaned_data['new_email']
            old_email = request.user.email
            
            request.user.email = new_email
            request.user.save()
            
            messages.success(request, f'Email успешно изменён с {old_email} на {new_email}!')
            return redirect('profile')
        else:
            messages.error(request, 'Пожалуйста, исправьте ошибки ниже.')
    else:
        form = EmailChangeForm(request.user)
    
    return render(request, 'orders/change_email.html', {'form': form})

@login_required
def settings_view(request):
    return render(request, 'orders/settings.html')

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

        payment_method = request.POST.get('payment_method', 'cash')

        order, created = Order.objects.get_or_create(
            customer=request.user,
            status='ожидается'
        )
        order.payment_method = payment_method
        order.save()

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

        if payment_method == 'card':
            send_order_receipt_email(order, order_item, menu_item, quantity)

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

@login_required
def update_stock(request, item_id):
    if request.user.user_type != 'canteen_admin':
        return HttpResponseForbidden("Только администратор столовой может управлять остатками.")

    item = get_object_or_404(MenuItem, id=item_id)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'increase':
            item.stock += 1
        elif action == 'decrease' and item.stock > 0:
            item.stock -= 1
        item.save()
        messages.success(request, f'Остаток блюда "{item.name}" обновлён: {item.stock} шт.')

    return redirect('menu')

def superuser_required(view_func):
    return user_passes_test(
        lambda u: u.is_superuser,
        login_url='login'
    )(view_func)

@superuser_required
def db_admin_panel(request):
    return render(request, 'orders/db_admin_panel.html')

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

@login_required
def add_review(request, item_id):
    menu_item = get_object_or_404(MenuItem, id=item_id)
    
    has_ordered = OrderItem.objects.filter(
        order__customer=request.user,
        menu_item=menu_item
    ).exists() or PreOrderItem.objects.filter(
        pre_order__customer=request.user,
        menu_item=menu_item
    ).exists()
    
    if not has_ordered:
        messages.error(request, 'Вы можете оставить отзыв только на блюда, которые вы купили')
        return redirect('menu')
    
    if Review.objects.filter(user=request.user, menu_item=menu_item).exists():
        messages.error(request, 'Вы уже оставляли отзыв на это блюдо')
        return redirect('menu')
    
    if request.method == 'POST':
        rating = request.POST.get('rating')
        comment = request.POST.get('comment', '')
        
        if rating and int(rating) in range(1, 6):
            Review.objects.create(
                user=request.user,
                menu_item=menu_item,
                rating=int(rating),
                comment=comment
            )
            messages.success(request, 'Спасибо за ваш отзыв!')
        else:
            messages.error(request, 'Пожалуйста, выберите оценку')
    
    return redirect('menu')

@login_required
def delete_review(request, item_id):
    menu_item = get_object_or_404(MenuItem, id=item_id)
    review = get_object_or_404(Review, user=request.user, menu_item=menu_item)
    
    if request.method == 'POST':
        review.delete()
        messages.success(request, 'Отзыв удалён')
    
    return redirect('menu')

def error_500(request):
    return render(request, 'orders/500.html', status=500)


@login_required
def create_support_request(request):
    if request.user.user_type != 'customer':
        return redirect('menu')

    if request.method == 'POST':
        subject = request.POST.get('subject')
        message_text = request.POST.get('message')
        category = request.POST.get('category', 'other')

        if subject and message_text:
            support_request = SupportRequest.objects.create(
                customer=request.user,
                subject=subject,
                message=message_text,
                category=category
            )

            SupportMessage.objects.create(
                support_request=support_request,
                sender=request.user,
                message=message_text,
                is_from_support=False
            )

            messages.success(request, 'Ваш запрос в техподдержку отправлен!')
            return redirect('support_chat', request_id=support_request.id)
        else:
            messages.error(request, 'Пожалуйста, заполните все поля')

    return render(request, 'orders/create_support_request.html', {
        'categories': SupportRequest.CATEGORY_CHOICES
    })

@login_required
def customer_support_requests(request):
    if request.user.user_type != 'customer':
        return redirect('menu')
    
    requests = SupportRequest.objects.filter(customer=request.user).order_by('-created_at')
    
    return render(request, 'orders/customer_support_requests.html', {
        'requests': requests,
        'status_choices': SupportRequest.STATUS_CHOICES
    })

@login_required
def support_dashboard(request):
    if request.user.user_type != 'tech_support':
        return redirect('menu')
    
    requests = SupportRequest.objects.all().select_related('customer', 'support_staff').order_by('-created_at')
    
    status_filter = request.GET.get('status')
    if status_filter:
        requests = requests.filter(status=status_filter)
    
    return render(request, 'orders/support_dashboard.html', {
        'requests': requests,
        'status_choices': SupportRequest.STATUS_CHOICES,
        'category_choices': SupportRequest.CATEGORY_CHOICES,
        'current_status': status_filter,
    })

@login_required
def respond_support_request(request, request_id):
    if request.user.user_type != 'tech_support':
        return redirect('menu')

    support_request = get_object_or_404(SupportRequest, id=request_id)

    if request.method == 'POST':
        message = request.POST.get('message')
        new_status = request.POST.get('status')

        if message:
            SupportMessage.objects.create(
                support_request=support_request,
                sender=request.user,
                message=message,
                is_from_support=True
            )

            support_request.support_staff = request.user
            support_request.status = new_status
            if new_status == 'closed':
                support_request.responded_at = timezone.now()
            support_request.save()

            messages.success(request, 'Сообщение отправлено!')
            return redirect('respond_support_request', request_id=request_id)
        else:
            messages.error(request, 'Пожалуйста, введите сообщение')

    support_request.messages.filter(is_from_support=False, is_read=False).update(is_read=True)

    return render(request, 'orders/respond_support_request.html', {
        'support_request': support_request,
        'status_choices': SupportRequest.STATUS_CHOICES,
        'messages_list': support_request.messages.select_related('sender').all()
    })

@login_required
def send_support_message(request, request_id):
    support_request = get_object_or_404(SupportRequest, id=request_id)

    if request.user != support_request.customer and request.user.user_type != 'tech_support':
        return HttpResponseForbidden("У вас нет доступа к этому чату.")

    if request.method == 'POST':
        message_text = request.POST.get('message')

        if message_text:
            SupportMessage.objects.create(
                support_request=support_request,
                sender=request.user,
                message=message_text,
                is_from_support=(request.user.user_type == 'tech_support')
            )

            if request.user.user_type == 'tech_support':
                support_request.status = request.POST.get('status', 'in_progress')
            else:
                support_request.status = 'open'
            support_request.save()

            messages.success(request, 'Сообщение отправлено!')
        else:
            messages.error(request, 'Пожалуйста, введите сообщение')

    if request.user.user_type == 'tech_support':
        return redirect('respond_support_request', request_id=request_id)
    else:
        return redirect('support_chat', request_id=request_id)

@login_required
def support_chat(request, request_id):
    support_request = get_object_or_404(SupportRequest, id=request_id, customer=request.user)

    support_request.messages.filter(is_from_support=True, is_read=False).update(is_read=True)

    return render(request, 'orders/support_chat.html', {
        'support_request': support_request,
        'messages_list': support_request.messages.select_related('sender').all()
    })

@login_required
def sales_report(request):
    if request.user.user_type != 'canteen_admin':
        return redirect('menu')
    
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    orders = Order.objects.all()
    
    if start_date:
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
            orders = orders.filter(order_date__date__gte=start_date)
        except ValueError:
            pass
    
    if end_date:
        try:
            end_date = datetime.strptime(end_date, '%Y-%m-%d')
            orders = orders.filter(order_date__date__lte=end_date)
        except ValueError:
            pass
    
    order_items = OrderItem.objects.filter(order__in=orders).select_related('menu_item', 'order')
    
    total_orders = orders.count()
    total_revenue = 0
    total_items_sold = 0
    items_by_category = {}
    payment_stats = {'cash': 0, 'card': 0}
    
    for item in order_items:
        item_total = item.quantity * item.menu_item.price
        total_revenue += item_total
        total_items_sold += item.quantity
        
        if item.order.payment_method == 'cash':
            payment_stats['cash'] += item_total
        else:
            payment_stats['card'] += item_total
        
        category = 'Основное меню'
        if category not in items_by_category:
            items_by_category[category] = {'quantity': 0, 'revenue': 0}
        items_by_category[category]['quantity'] += item.quantity
        items_by_category[category]['revenue'] += item_total
    
    top_items = {}
    for item in order_items:
        item_name = item.menu_item.name
        if item_name not in top_items:
            top_items[item_name] = {'quantity': 0, 'revenue': 0}
        top_items[item_name]['quantity'] += item.quantity
        top_items[item_name]['revenue'] += item.quantity * item.menu_item.price
    
    top_items_sorted = sorted(top_items.items(), key=lambda x: x[1]['quantity'], reverse=True)[:10]
    
    orders_with_total = []
    for order in orders.order_by('-order_date')[:20]:
        order_total = 0
        for item in order.orderitem_set.all():
            order_total += item.quantity * item.menu_item.price
        orders_with_total.append({
            'order': order,
            'total': order_total
        })

    context = {
        'total_orders': total_orders,
        'total_revenue': total_revenue,
        'total_items_sold': total_items_sold,
        'average_order_value': total_revenue / total_orders if total_orders > 0 else 0,
        'items_by_category': items_by_category,
        'payment_stats': payment_stats,
        'top_items': top_items_sorted,
        'start_date': request.GET.get('start_date', ''),
        'end_date': request.GET.get('end_date', ''),
        'orders_with_total': orders_with_total
    }
    
    return render(request, 'orders/sales_report.html', context)

def error_500(request):
    return render(request, 'orders/500.html', status=500)

@rate_limit(key_func=ip_key, rate=3, period_seconds=300, block=True)
def password_reset_request(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        
        if not email:
            messages.error(request, 'Пожалуйста, введите email')
            return render(request, 'registration/password_reset_request.html')
        
        try:
            user = CustomUser.objects.filter(email=email).first()
            
            if not user:
                messages.success(request, 'Если email существует в системе, код будет отправлен')
                return redirect('password_reset_verify')
            
            reset_code = PasswordResetCode.generate_code(user)
            
            subject = 'Код восстановления пароля - Столовая МПТ'
            message = f'''
Здравствуйте, {user.username}!

Вы запросили восстановление пароля для вашего аккаунта в системе "Столовая МПТ".

Ваш код восстановления: {reset_code.code}

Код действителен в течение 15 минут.

Если вы не запрашивали восстановление пароля, просто проигнорируйте это сообщение.

С уважением,
Команда Столовой МПТ
            '''
            
            try:
                send_mail(
                    subject,
                    message.strip(),
                    settings.DEFAULT_FROM_EMAIL,
                    [email],
                    fail_silently=False,
                )
                messages.success(request, 'Код восстановления отправлен на ваш email')
                return redirect('password_reset_verify')
            except Exception as e:
                messages.error(request, 'Ошибка при отправке email. Попробуйте позже.')
                print(f"Email send error: {e}")
                
        except Exception as e:
            messages.error(request, 'Произошла ошибка. Попробуйте позже.')
            print(f"Password reset error: {e}")
        
    return render(request, 'registration/password_reset_request.html')

@rate_limit(key_func=ip_key, rate=5, period_seconds=300, block=True)
def password_reset_verify(request):
    if request.method == 'POST':
        code = request.POST.get('code')
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')
        
        if not code or not new_password or not confirm_password:
            messages.error(request, 'Пожалуйста, заполните все поля')
            return render(request, 'registration/password_reset_verify.html')
        
        if new_password != confirm_password:
            messages.error(request, 'Пароли не совпадают')
            return render(request, 'registration/password_reset_verify.html')
        
        if len(new_password) < 8:
            messages.error(request, 'Пароль должен быть не менее 8 символов')
            return render(request, 'registration/password_reset_verify.html')
        
        try:
            reset_code = PasswordResetCode.objects.get(code=code, is_used=False)
            
            if not reset_code.is_valid():
                messages.error(request, 'Код восстановления недействителен')
                return render(request, 'registration/password_reset_verify.html')
            
            user = reset_code.user
            user.set_password(new_password)
            user.save()
            
            reset_code.is_used = True
            reset_code.save()
            
            messages.success(request, 'Пароль успешно изменён! Теперь вы можете войти.')
            return redirect('login')
            
        except PasswordResetCode.DoesNotExist:
            messages.error(request, 'Код восстановления не найден')
            
    return render(request, 'registration/password_reset_verify.html')

@login_required
def recommendations_view(request):
    """Страница с персональными рекомендациями"""
    if request.user.user_type != 'customer':
        return redirect('menu')
    
    engine = RecommendationEngine()
    
    # Генерируем новые рекомендации
    recommendations = engine.generate_recommendations(request.user, limit=12)
    
    # Получаем популярные блюда для дополнения
    popular_items = engine.get_popular_items(limit=6)
    
    # Получаем тренды
    trending_items = engine.get_trending_items(days=3, limit=4)
    
    context = {
        'recommendations': recommendations,
        'popular_items': popular_items,
        'trending_items': trending_items,
    }
    
    return render(request, 'orders/recommendations.html', context)

@login_required
def update_recommendations(request):
    """Обновление рекомендаций (AJAX)"""
    if request.user.user_type != 'customer':
        return HttpResponseForbidden("Только клиенты могут получать рекомендации")
    
    if request.method == 'POST':
        engine = RecommendationEngine()
        
        # Обновляем статистику популярности
        engine.update_popularity_stats()
        
        # Генерируем новые рекомендации
        recommendations = engine.generate_recommendations(request.user, limit=8)
        
        # Формируем HTML для ответа
        html = ""
        for rec in recommendations:
            html += f"""
            <div class="recommendation-card">
                <div class="recommendation-score">{rec['score']:.2f}</div>
                <div class="recommendation-reason">{rec['reason']}</div>
                <img src="{rec['menu_item'].image.url if rec['menu_item'].image else '/static/images/no-image.png'}" 
                     alt="{rec['menu_item'].name}" class="recommendation-image">
                <h4>{rec['menu_item'].name}</h4>
                <p>{rec['menu_item'].description[:100]}...</p>
                <div class="recommendation-price">{rec['menu_item'].price:.2f} ₽</div>
                <a href="/order/{rec['menu_item'].id}/" class="btn btn-primary">Заказать</a>
            </div>
            """
        
        return HttpResponse(html)
    
    return HttpResponseBadRequest("Только POST запросы")

@login_required
def popular_items_view(request):
    """Страница с популярными блюдами"""
    engine = RecommendationEngine()
    
    # Получаем популярные блюда
    popular_items = engine.get_popular_items(limit=5)  # Только топ 5
    
    print(f"DEBUG: Получено {len(popular_items)} популярных блюд")
    
    # Добавляем статистику
    items_with_stats = []
    for popular in popular_items:
        reviews = Review.objects.filter(menu_item=popular.menu_item)
        avg_rating = reviews.aggregate(Avg('rating'))['rating__avg'] or 0
        
        item_data = {
            'popular': popular,
            'avg_rating': avg_rating,
            'review_count': reviews.count()
        }
        items_with_stats.append(item_data)
        print(f"DEBUG: {popular.menu_item.name} - {popular.order_count} заказов")
    
    context = {
        'items': items_with_stats,
        'has_next': False,
        'has_prev': False
    }
    
    print(f"DEBUG: Передано в шаблон {len(items_with_stats)} блюд")
    
    return render(request, 'orders/popular_items.html', context)

@login_required
def trending_items_view(request):
    """Страница с трендами"""
    engine = RecommendationEngine()
    
    days = int(request.GET.get('days', 7))
    trending_items = engine.get_trending_items(days=days, limit=20)
    
    # Добавляем информацию о росте популярности
    items_with_growth = []
    for item in trending_items:
        # Сравниваем с предыдущим периодом
        previous_orders = OrderItem.objects.filter(
            menu_item=item,
            order__order_date__gte=timezone.now() - timedelta(days=days*2),
            order__order_date__lt=timezone.now() - timedelta(days=days)
        ).count()
        
        current_orders = OrderItem.objects.filter(
            menu_item=item,
            order__order_date__gte=timezone.now() - timedelta(days=days)
        ).count()
        
        growth = 0
        if previous_orders > 0:
            growth = ((current_orders - previous_orders) / previous_orders) * 100
        
        items_with_growth.append({
            'item': item,
            'current_orders': current_orders,
            'previous_orders': previous_orders,
            'growth': growth
        })
    
    context = {
        'items': items_with_growth,
        'days': days,
        'growth_periods': [1, 3, 7, 14, 30]
    }
    
    return render(request, 'orders/trending_items.html', context)

# Административные функции для управления рекомендациями
@superuser_required
def admin_recommendations_settings(request):
    """Настройки рекомендательной системы"""
    if request.method == 'POST':
        # Здесь можно добавить сохранение весов и настроек
        messages.success(request, 'Настройки рекомендательной системы обновлены')
        return redirect('admin_recommendations_settings')
    
    engine = RecommendationEngine()
    
    # Получаем статистику
    total_recommendations = Recommendation.objects.count()
    unique_users = Recommendation.objects.values('user').distinct().count()
    
    context = {
        'weights': engine.weights,
        'total_recommendations': total_recommendations,
        'unique_users': unique_users,
        'popular_items_count': engine.get_popular_items(limit=100).count(),
        'high_rated_count': engine.get_high_rated_items(limit=100).count(),
    }
    
    return render(request, 'orders/admin_recommendations_settings.html', context)

@superuser_required
def admin_update_popularity(request):
    """Принудительное обновление статистики популярности"""
    if request.method == 'POST':
        engine = RecommendationEngine()
        engine.update_popularity_stats()
        
        messages.success(request, 'Статистика популярности обновлена')
        return redirect('admin_recommendations_settings')
    
    return redirect('admin_recommendations_settings')

