from django.shortcuts import render, redirect
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordChangeForm, PasswordResetForm
from django.db.models import Q
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
from .models import CustomUser, MenuItem, Order, OrderItem, PreOrder, PreOrderItem, Review, SupportRequest
from django.utils import timezone
from datetime import datetime, time
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
        # Администратор видит все предзаказы
        pre_orders = PreOrder.objects.all().prefetch_related('preorderitem_set__menu_item', 'customer').order_by('-order_date')
    else:
        # Клиент видит только свои предзаказы
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

@login_required
def add_review(request, item_id):
    menu_item = get_object_or_404(MenuItem, id=item_id)
    
    # Проверяем, покупал ли пользователь это блюдо
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
    
    # Проверяем, не оставлял ли пользователь уже отзыв
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


# Техническая поддержка
@login_required
def create_support_request(request):
    if request.user.user_type != 'customer':
        return redirect('menu')
    
    if request.method == 'POST':
        subject = request.POST.get('subject')
        message = request.POST.get('message')
        category = request.POST.get('category', 'other')
        
        if subject and message:
            SupportRequest.objects.create(
                customer=request.user,
                subject=subject,
                message=message,
                category=category,
                priority='medium'
            )
            messages.success(request, 'Ваш запрос в техподдержку отправлен!')
            return redirect('menu')
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
    
    # Фильтрация по статусу
    status_filter = request.GET.get('status')
    if status_filter:
        requests = requests.filter(status=status_filter)
    
    # Фильтрация по приоритету
    priority_filter = request.GET.get('priority')
    if priority_filter:
        requests = requests.filter(priority=priority_filter)
    
    return render(request, 'orders/support_dashboard.html', {
        'requests': requests,
        'status_choices': SupportRequest.STATUS_CHOICES,
        'priority_choices': SupportRequest.PRIORITY_CHOICES,
        'category_choices': SupportRequest.CATEGORY_CHOICES,
        'current_status': status_filter,
        'current_priority': priority_filter
    })

@login_required
def respond_support_request(request, request_id):
    if request.user.user_type != 'tech_support':
        return redirect('menu')
    
    support_request = get_object_or_404(SupportRequest, id=request_id)
    
    if request.method == 'POST':
        response = request.POST.get('response')
        new_status = request.POST.get('status')
        
        if response:
            support_request.support_response = response
            support_request.support_staff = request.user
            support_request.status = new_status
            support_request.responded_at = timezone.now()
            support_request.save()
            
            messages.success(request, 'Ответ отправлен!')
            return redirect('support_dashboard')
        else:
            messages.error(request, 'Пожалуйста, введите ответ')
    
    return render(request, 'orders/respond_support_request.html', {
        'support_request': support_request,
        'status_choices': SupportRequest.STATUS_CHOICES
    })

# Отчёты о продажах и прибыли
@login_required
def sales_report(request):
    if request.user.user_type != 'canteen_admin':
        return redirect('menu')
    
    # Получаем параметры фильтрации
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    # Базовый запрос для заказов
    orders = Order.objects.all()
    
    # Применяем фильтры по дате
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
    
    # Получаем все позиции заказов
    order_items = OrderItem.objects.filter(order__in=orders).select_related('menu_item', 'order')
    
    # Считаем статистику
    total_orders = orders.count()
    total_revenue = 0
    total_items_sold = 0
    items_by_category = {}
    payment_stats = {'cash': 0, 'card': 0}
    
    for item in order_items:
        item_total = item.quantity * item.menu_item.price
        total_revenue += item_total
        total_items_sold += item.quantity
        
        # Статистика по способам оплаты
        if item.order.payment_method == 'cash':
            payment_stats['cash'] += item_total
        else:
            payment_stats['card'] += item_total
        
        # Можно добавить категории если нужно
        category = 'Основное меню'  # Можно расширить
        if category not in items_by_category:
            items_by_category[category] = {'quantity': 0, 'revenue': 0}
        items_by_category[category]['quantity'] += item.quantity
        items_by_category[category]['revenue'] += item_total
    
    # Топ популярных блюд
    top_items = {}
    for item in order_items:
        item_name = item.menu_item.name
        if item_name not in top_items:
            top_items[item_name] = {'quantity': 0, 'revenue': 0}
        top_items[item_name]['quantity'] += item.quantity
        top_items[item_name]['revenue'] += item.quantity * item.menu_item.price
    
    # Сортируем топ блюд
    top_items_sorted = sorted(top_items.items(), key=lambda x: x[1]['quantity'], reverse=True)[:10]
    
    # Добавляем подсчёт суммы для каждого заказа
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
 
 #   >AAB0=>2;5=85  ?0@>;O
 @ r a t e _ l i m i t ( k e y _ f u n c = i p _ k e y ,   r a t e = 3 ,   p e r i o d _ s e c o n d s = 3 0 0 ,   b l o c k = T r u e ) 
 d e f   p a s s w o r d _ r e s e t _ r e q u e s t ( r e q u e s t ) : 
         i f   r e q u e s t . m e t h o d   = =   ' P O S T ' : 
                 e m a i l   =   r e q u e s t . P O S T . g e t ( ' e m a i l ' ) 
                 
                 i f   n o t   e m a i l : 
                         m e s s a g e s . e r r o r ( r e q u e s t ,   ' >60;C9AB0,   22548B5  e m a i l ' ) 
                         r e t u r n   r e n d e r ( r e q u e s t ,   ' r e g i s t r a t i o n / p a s s w o r d _ r e s e t _ r e q u e s t . h t m l ' ) 
                 
                 t r y : 
                         u s e r   =   C u s t o m U s e r . o b j e c t s . g e t ( e m a i l = e m a i l ) 
                         
                         #   5=5@8@C5<  :>4  2>AAB0=>2;5=8O
                         r e s e t _ c o d e   =   P a s s w o r d R e s e t C o d e . g e n e r a t e _ c o d e ( u s e r ) 
                         
                         #   B?@02;O5<  e m a i l   A  :>4><
                         s u b j e c t   =   ' >4  2>AAB0=>2;5=8O  ?0@>;O  -   !B>;>20O  "' 
                         m e s s a g e   =   f ' ' ' 
 4@02AB2C9B5,   { u s e r . u s e r n a m e } ! 
 
 K  70?@>A8;8  2>AAB0=>2;5=85  ?0@>;O  4;O  20H53>  0::0C=B0  2  A8AB5<5   
 !B>;>20O 
 ". 
 
 0H  :>4  2>AAB0=>2;5=8O:   { r e s e t _ c o d e . c o d e } 
 
 >4  459AB28B5;5=  2  B5G5=85  1 5   <8=CB. 
 
 A;8  2K  =5  70?@0H820;8  2>AAB0=>2;5=85  ?0@>;O,   ?@>AB>  ?@>83=>@8@C9B5  MB>  A>>1I5=85. 
 
 !  C2065=85<, 
 ><0=40  !B>;>2>9  "
                         ' ' ' 
                         
                         t r y : 
                                 s e n d _ m a i l ( 
                                         s u b j e c t , 
                                         m e s s a g e . s t r i p ( ) , 
                                         s e t t i n g s . D E F A U L T _ F R O M _ E M A I L , 
                                         [ e m a i l ] , 
                                         f a i l _ s i l e n t l y = F a l s e , 
                                 ) 
                                 m e s s a g e s . s u c c e s s ( r e q u e s t ,   ' >4  2>AAB0=>2;5=8O  >B?@02;5=  =0  20H  e m a i l ' ) 
                                 r e t u r n   r e d i r e c t ( ' p a s s w o r d _ r e s e t _ v e r i f y ' ) 
                         e x c e p t   E x c e p t i o n   a s   e : 
                                 m e s s a g e s . e r r o r ( r e q u e s t ,   ' H81:0  ?@8  >B?@02:5  e m a i l .   >?@>1C9B5  ?>765. ' ) 
                                 p r i n t ( f E m a i l  
 s e n d  
 e r r o r :  
 e  
 ) 
                                 
                 e x c e p t   C u s t o m U s e r . D o e s N o t E x i s t : 
                         #   5  A>>1I05<  ?>;L7>20B5;N,   GB>  e m a i l   =5  =0945=  ( 157>?0A=>ABL) 
                         m e s s a g e s . s u c c e s s ( r e q u e s t ,   ' A;8  e m a i l   ACI5AB2C5B  2  A8AB5<5,   :>4  1C45B  >B?@02;5=' ) 
                         r e t u r n   r e d i r e c t ( ' p a s s w o r d _ r e s e t _ v e r i f y ' ) 
         
         r e t u r n   r e n d e r ( r e q u e s t ,   ' r e g i s t r a t i o n / p a s s w o r d _ r e s e t _ r e q u e s t . h t m l ' ) 
 
 @ r a t e _ l i m i t ( k e y _ f u n c = i p _ k e y ,   r a t e = 5 ,   p e r i o d _ s e c o n d s = 3 0 0 ,   b l o c k = T r u e ) 
 d e f   p a s s w o r d _ r e s e t _ v e r i f y ( r e q u e s t ) : 
         i f   r e q u e s t . m e t h o d   = =   ' P O S T ' : 
                 c o d e   =   r e q u e s t . P O S T . g e t ( ' c o d e ' ) 
                 n e w _ p a s s w o r d   =   r e q u e s t . P O S T . g e t ( ' n e w _ p a s s w o r d ' ) 
                 c o n f i r m _ p a s s w o r d   =   r e q u e s t . P O S T . g e t ( ' c o n f i r m _ p a s s w o r d ' ) 
                 
                 i f   n o t   c o d e   o r   n o t   n e w _ p a s s w o r d   o r   n o t   c o n f i r m _ p a s s w o r d : 
                         m e s s a g e s . e r r o r ( r e q u e s t ,   ' >60;C9AB0,   70?>;=8B5  2A5  ?>;O' ) 
                         r e t u r n   r e n d e r ( r e q u e s t ,   ' r e g i s t r a t i o n / p a s s w o r d _ r e s e t _ v e r i f y . h t m l ' ) 
                 
                 i f   n e w _ p a s s w o r d   ! =   c o n f i r m _ p a s s w o r d : 
                         m e s s a g e s . e r r o r ( r e q u e s t ,   ' 0@>;8  =5  A>2?040NB' ) 
                         r e t u r n   r e n d e r ( r e q u e s t ,   ' r e g i s t r a t i o n / p a s s w o r d _ r e s e t _ v e r i f y . h t m l ' ) 
                 
                 i f   l e n ( n e w _ p a s s w o r d )   <   8 : 
                         m e s s a g e s . e r r o r ( r e q u e s t ,   ' 0@>;L  4>;65=  A>45@60BL  <8=8<C<  8   A8<2>;>2' ) 
                         r e t u r n   r e n d e r ( r e q u e s t ,   ' r e g i s t r a t i o n / p a s s w o r d _ r e s e t _ v e r i f y . h t m l ' ) 
                 
                 t r y : 
                         r e s e t _ c o d e   =   P a s s w o r d R e s e t C o d e . o b j e c t s . g e t ( c o d e = c o d e ,   i s _ u s e d = F a l s e ) 
                         
                         i f   n o t   r e s e t _ c o d e . i s _ v a l i d ( ) : 
                                 m e s s a g e s . e r r o r ( r e q u e s t ,   ' >4  =5459AB28B5;5=  8;8  8ABQ:' ) 
                                 r e t u r n   r e n d e r ( r e q u e s t ,   ' r e g i s t r a t i o n / p a s s w o r d _ r e s e t _ v e r i f y . h t m l ' ) 
                         
                         #   5=O5<  ?0@>;L  ?>;L7>20B5;O
                         u s e r   =   r e s e t _ c o d e . u s e r 
                         u s e r . s e t _ p a s s w o r d ( n e w _ p a s s w o r d ) 
                         u s e r . s a v e ( ) 
                         
                         #   ><5G05<  :>4  :0:  8A?>;L7>20==K9
                         r e s e t _ c o d e . i s _ u s e d   =   T r u e 
                         r e s e t _ c o d e . s a v e ( ) 
                         
                         m e s s a g e s . s u c c e s s ( r e q u e s t ,   ' 0@>;L  CA?5H=>  87<5=Q=!   "5?5@L  2K  <>65B5  2>9B8. ' ) 
                         r e t u r n   r e d i r e c t ( ' l o g i n ' ) 
                         
                 e x c e p t   P a s s w o r d R e s e t C o d e . D o e s N o t E x i s t : 
                         m e s s a g e s . e r r o r ( r e q u e s t ,   ' 525@=K9  :>4' ) 
                         
         r e t u r n   r e n d e r ( r e q u e s t ,   ' r e g i s t r a t i o n / p a s s w o r d _ r e s e t _ v e r i f y . h t m l ' ) 
  
 