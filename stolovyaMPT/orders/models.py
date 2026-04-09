from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db import models
from django.utils.translation import gettext_lazy as _

class CustomUser(AbstractUser):
    USER_TYPE_CHOICES = (
        ('customer', 'Customer'),
        ('canteen_admin', 'Canteen Admin'),
        ('db_admin', 'DB Admin'),
    )
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES)

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

    customer = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    menu_items = models.ManyToManyField(MenuItem, through='OrderItem')
    order_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ожидается')

    def __str__(self):
        return f"Order {self.id} by {self.customer.username}"

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)