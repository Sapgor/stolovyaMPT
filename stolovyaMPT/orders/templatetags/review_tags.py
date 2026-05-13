from django import template
from django.db.models import Avg
from ..models import OrderItem, PreOrderItem

register = template.Library()

@register.filter
def average_rating(reviews):
    if not reviews:
        return 0
    return reviews.aggregate(Avg('rating'))['rating__avg'] or 0

@register.filter
def has_ordered(item, user):
    if not user or not user.is_authenticated:
        return False
    
    ordered = OrderItem.objects.filter(
        order__customer=user,
        menu_item=item
    ).exists()
    
    pre_ordered = PreOrderItem.objects.filter(
        pre_order__customer=user,
        menu_item=item
    ).exists()
    
    return ordered or pre_ordered
