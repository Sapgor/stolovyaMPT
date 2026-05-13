from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _

class CustomUser(AbstractUser):
    USER_TYPE_CHOICES = (
        ('customer', 'Customer'),
        ('canteen_admin', 'Canteen Admin'),
        ('db_admin', 'DB Admin'),
        ('tech_support', 'Tech Support'),
    )
    email = models.EmailField(unique=True, verbose_name=_('Email'))
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES)
    favorites = models.ManyToManyField('MenuItem', blank=True, related_name='favorited_by', verbose_name=_('Избранное'))

class MenuItem(models.Model):
    name = models.CharField(
        max_length=255,
        verbose_name=_("Название"),
        help_text=_("Краткое название блюда")
    )
    description = models.TextField(
        verbose_name=_("Описание"),
        help_text=_("Подробное описание блюда")
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_("Цена"),
        help_text=_("Цена в рублях")
    )
    stock = models.IntegerField(
        default=0,
        verbose_name=_("Остаток"),
        help_text=_("Количество доступных порций")
    )
    image = models.ImageField(
        upload_to='menu_images/',
        blank=True,
        null=True,
        verbose_name=_("Изображение"),
        help_text=_("Фото блюда")
    )

    class Meta:
        verbose_name = _("Блюдо")
        verbose_name_plural = _("Блюда")

    def __str__(self):
        return self.name

    def is_available(self, quantity=1):
        return self.stock >= quantity


class Order(models.Model):
    STATUS_CHOICES = (
        ('ожидается', 'ожидается'),
        ('выдан', 'выдан'),
    )
    PAYMENT_CHOICES = (
        ('cash', 'Наличные'),
        ('card', 'Карта'),
    )

    customer = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    menu_items = models.ManyToManyField(MenuItem, through='OrderItem')
    order_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ожидается')
    payment_method = models.CharField(max_length=10, choices=PAYMENT_CHOICES, default='cash', verbose_name=_('Способ оплаты'))

    def __str__(self):
        return f"Order {self.id} by {self.customer.username}"

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    pickup_time = models.TimeField(null=True, blank=True, verbose_name=_('Время получения'))

class PreOrder(models.Model):
    STATUS_CHOICES = (
        ('pending', 'В ожидании'),
        ('confirmed', 'Подтверждён'),
        ('cancelled', 'Отменён'),
    )
    PAYMENT_CHOICES = (
        ('cash', 'Наличные'),
        ('card', 'Карта'),
    )
    
    customer = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    menu_items = models.ManyToManyField(MenuItem, through='PreOrderItem')
    order_date = models.DateTimeField(auto_now_add=True)
    pickup_time = models.DateTimeField(verbose_name=_('Время получения'))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_method = models.CharField(max_length=10, choices=PAYMENT_CHOICES, default='cash', verbose_name=_('Способ оплаты'))
    total_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_('Сумма'))
    notes = models.TextField(blank=True, null=True, verbose_name=_('Примечания'))

    class Meta:
        verbose_name = _('Предзаказ')
        verbose_name_plural = _('Предзаказы')

    def __str__(self):
        return f"PreOrder {self.id} by {self.customer.username}"

class PreOrderItem(models.Model):
    pre_order = models.ForeignKey(PreOrder, on_delete=models.CASCADE)
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = _('Позиция предзаказа')
        verbose_name_plural = _('Позиции предзаказов')

class Review(models.Model):
    RATING_CHOICES = (
        (1, '⭐'),
        (2, '⭐⭐'),
        (3, '⭐⭐⭐'),
        (4, '⭐⭐⭐⭐'),
        (5, '⭐⭐⭐⭐⭐'),
    )
    
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, verbose_name=_('Пользователь'))
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, verbose_name=_('Блюдо'))
    rating = models.IntegerField(choices=RATING_CHOICES, verbose_name=_('Оценка'))
    comment = models.TextField(blank=True, null=True, verbose_name=_('Комментарий'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Дата создания'))
    
    class Meta:
        verbose_name = _('Отзыв')
        verbose_name_plural = _('Отзывы')
        unique_together = ['user', 'menu_item']
    
    def __str__(self):
        return f"Отзыв от {self.user.username} на {self.menu_item.name}"

class SupportRequest(models.Model):
    PRIORITY_CHOICES = (
        ('low', 'Низкий'),
        ('medium', 'Средний'),
        ('high', 'Высокий'),
        ('urgent', 'Срочный'),
    )
    
    STATUS_CHOICES = (
        ('open', 'Открыт'),
        ('in_progress', 'В работе'),
        ('answered', 'Отвечен'),
        ('closed', 'Закрыт'),
    )
    
    CATEGORY_CHOICES = (
        ('technical', 'Техническая проблема'),
        ('payment', 'Проблема с оплатой'),
        ('order', 'Проблема с заказом'),
        ('account', 'Проблема с аккаунтом'),
        ('other', 'Другое'),
    )
    
    customer = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='support_requests', verbose_name=_('Клиент'))
    subject = models.CharField(max_length=200, verbose_name=_('Тема'))
    message = models.TextField(verbose_name=_('Сообщение'))
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other', verbose_name=_('Категория'))
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium', verbose_name=_('Приоритет'))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open', verbose_name=_('Статус'))
    support_response = models.TextField(blank=True, null=True, verbose_name=_('Ответ поддержки'))
    support_staff = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='handled_requests', verbose_name=_('Сотрудник поддержки'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Дата создания'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Дата обновления'))
    responded_at = models.DateTimeField(null=True, blank=True, verbose_name=_('Дата ответа'))
    
    class Meta:
        verbose_name = _('Запрос в поддержку')
        verbose_name_plural = _('Запросы в поддержку')
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Support Request #{self.id}: {self.subject}"

class SupportMessage(models.Model):
    support_request = models.ForeignKey(SupportRequest, on_delete=models.CASCADE, related_name='messages', verbose_name=_('Запрос в поддержку'))
    sender = models.ForeignKey(CustomUser, on_delete=models.CASCADE, verbose_name=_('Отправитель'))
    message = models.TextField(verbose_name=_('Сообщение'))
    is_from_support = models.BooleanField(default=False, verbose_name=_('От поддержки'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Дата отправки'))
    is_read = models.BooleanField(default=False, verbose_name=_('Прочитано'))

    class Meta:
        verbose_name = _('Сообщение поддержки')
        verbose_name_plural = _('Сообщения поддержки')
        ordering = ['created_at']

    def __str__(self):
        return f"Message #{self.id} in Request #{self.support_request.id}"

class PasswordResetCode(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, verbose_name=_('Пользователь'))
    code = models.CharField(max_length=6, verbose_name=_('Код восстановления'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Дата создания'))
    is_used = models.BooleanField(default=False, verbose_name=_('Использован'))
    
    class Meta:
        verbose_name = _('Код восстановления пароля')
        verbose_name_plural = _('Коды восстановления пароля')
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Reset code for {self.user.username}: {self.code}"
    
    def is_valid(self):
        from django.utils import timezone
        import datetime
        return (not self.is_used and 
                (timezone.now() - self.created_at) < datetime.timedelta(minutes=15))
    
    @classmethod
    def generate_code(cls, user):
        import random
        import string

        cls.objects.filter(user=user, is_used=False).update(is_used=True)

        code = ''.join(random.choices(string.digits, k=6))
        return cls.objects.create(user=user, code=code)

class Recommendation(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, verbose_name=_('Пользователь'))
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, verbose_name=_('Рекомендуемое блюдо'))
    score = models.DecimalField(max_digits=5, decimal_places=2, verbose_name=_('Оценка релевантности'))
    reason = models.CharField(max_length=50, verbose_name=_('Причина рекомендации'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Дата создания'))
    
    class Meta:
        verbose_name = _('Рекомендация')
        verbose_name_plural = _('Рекомендации')
        unique_together = ['user', 'menu_item']
        ordering = ['-score']
    
    def __str__(self):
        return f"Рекомендация для {self.user.username}: {self.menu_item.name}"

class PopularItem(models.Model):
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, verbose_name=_('Блюдо'))
    order_count = models.IntegerField(default=0, verbose_name=_('Количество заказов'))
    total_quantity = models.IntegerField(default=0, verbose_name=_('Общее количество'))
    revenue = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name=_('Доход'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Дата обновления'))
    
    class Meta:
        verbose_name = _('Популярное блюдо')
        verbose_name_plural = _('Популярные блюда')
        unique_together = ['menu_item']
    
    def __str__(self):
        return f"{self.menu_item.name} - {self.order_count} заказов"