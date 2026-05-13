from django.db.models import Count, Avg, Q, F, Sum
from django.utils import timezone
from datetime import timedelta
from .models import MenuItem, Order, OrderItem, PreOrder, PreOrderItem, Review, Recommendation, PopularItem, CustomUser

class RecommendationEngine:
    def __init__(self):
        self.weights = {
            'popularity': 0.3,
            'rating': 0.25,
            'collaborative': 0.25,
            'content_based': 0.2
        }
    
    def update_popularity_stats(self):
        """Обновляет статистику популярности блюд"""
        PopularItem.objects.all().delete()
        
        # Анализ обычных заказов
        order_stats = OrderItem.objects.values('menu_item').annotate(
            order_count=Count('id'),
            total_quantity=Sum('quantity'),
            revenue=Sum(F('quantity') * F('menu_item__price'))
        ).order_by('-order_count')
        
        # Анализ предзаказов
        preorder_stats = PreOrderItem.objects.values('menu_item').annotate(
            order_count=Count('id'),
            total_quantity=Sum('quantity'),
            revenue=Sum(F('quantity') * F('menu_item__price'))
        )
        
        # Объединение статистики
        popular_items = {}
        for stat in order_stats:
            item_id = stat['menu_item']
            popular_items[item_id] = {
                'order_count': stat['order_count'],
                'total_quantity': stat['total_quantity'] or 0,
                'revenue': stat['revenue'] or 0
            }
        
        for stat in preorder_stats:
            item_id = stat['menu_item']
            if item_id in popular_items:
                popular_items[item_id]['order_count'] += stat['order_count']
                popular_items[item_id]['total_quantity'] += stat['total_quantity'] or 0
                popular_items[item_id]['revenue'] += stat['revenue'] or 0
            else:
                popular_items[item_id] = {
                    'order_count': stat['order_count'],
                    'total_quantity': stat['total_quantity'] or 0,
                    'revenue': stat['revenue'] or 0
                }
        
        # Сохранение в базу
        for item_id, stats in popular_items.items():
            PopularItem.objects.update_or_create(
                menu_item_id=item_id,
                defaults={
                    'order_count': stats['order_count'],
                    'total_quantity': stats['total_quantity'],
                    'revenue': stats['revenue']
                }
            )
    
    def get_popular_items(self, limit=10):
        """Возвращает самые популярные блюда"""
        return PopularItem.objects.select_related('menu_item').order_by('-order_count')[:limit]
    
    def get_high_rated_items(self, limit=10):
        """Возвращает блюда с высоким рейтингом"""
        return MenuItem.objects.filter(
            review__rating__gte=4
        ).annotate(
            avg_rating=Avg('review__rating'),
            review_count=Count('review')
        ).filter(
            review_count__gte=3
        ).order_by('-avg_rating')[:limit]
    
    def get_similar_users(self, user, limit=20):
        """Находит похожих пользователей на основе покупок"""
        user_items = set(OrderItem.objects.filter(
            order__customer=user
        ).values_list('menu_item_id', flat=True))
        
        user_items.update(PreOrderItem.objects.filter(
            pre_order__customer=user
        ).values_list('menu_item_id', flat=True))
        
        similar_users = []
        all_users = CustomUser.objects.filter(
            user_type='customer'
        ).exclude(id=user.id)
        
        for other_user in all_users:
            other_items = set(OrderItem.objects.filter(
                order__customer=other_user
            ).values_list('menu_item_id', flat=True))
            
            other_items.update(PreOrderItem.objects.filter(
                pre_order__customer=other_user
            ).values_list('menu_item_id', flat=True))
            
            # Расчет схожести (коэффициент Жаккара)
            intersection = len(user_items & other_items)
            union = len(user_items | other_items)
            
            if union > 0:
                similarity = intersection / union
                if similarity > 0.1:  # Минимальный порог схожести
                    similar_users.append((other_user, similarity))
        
        # Сортировка по схожести
        similar_users.sort(key=lambda x: x[1], reverse=True)
        return [user for user, _ in similar_users[:limit]]
    
    def get_collaborative_recommendations(self, user, limit=10):
        """Коллаборативная фильтрация на основе похожих пользователей"""
        similar_users = self.get_similar_users(user)
        
        # Получаем блюда, которые купили похожие пользователи
        user_items = set(OrderItem.objects.filter(
            order__customer=user
        ).values_list('menu_item_id', flat=True))
        
        user_items.update(PreOrderItem.objects.filter(
            pre_order__customer=user
        ).values_list('menu_item_id', flat=True))
        
        recommended_items = {}
        for similar_user in similar_users:
            similar_items = OrderItem.objects.filter(
                order__customer=similar_user
            ).exclude(menu_item_id__in=user_items)
            
            similar_items.update(PreOrderItem.objects.filter(
                pre_order__customer=similar_user
            ).exclude(menu_item_id__in=user_items))
            
            for item in similar_items:
                item_id = item.menu_item_id
                if item_id not in recommended_items:
                    recommended_items[item_id] = {
                        'count': 0,
                        'users': set()
                    }
                
                recommended_items[item_id]['count'] += item.quantity
                recommended_items[item_id]['users'].add(similar_user.id)
        
        # Расчет финального счета
        final_recommendations = []
        for item_id, data in recommended_items.items():
            score = data['count'] * len(data['users'])
            final_recommendations.append((item_id, score))
        
        final_recommendations.sort(key=lambda x: x[1], reverse=True)
        return [item_id for item_id, _ in final_recommendations[:limit]]
    
    def get_content_based_recommendations(self, user, limit=10):
        """Контент-основанные рекомендации на основе предпочтений"""
        # Анализируем предыдущие покупки пользователя
        user_orders = OrderItem.objects.filter(
            order__customer=user
        ).select_related('menu_item')
        
        user_preorders = PreOrderItem.objects.filter(
            pre_order__customer=user
        ).select_related('menu_item')
        
        # Определяем любимые категории (простая эвристика по названию)
        preferences = {}
        for order in user_orders:
            category = self._get_simple_category(order.menu_item.name)
            if category not in preferences:
                preferences[category] = {'count': 0, 'total_spent': 0}
            preferences[category]['count'] += order.quantity
            preferences[category]['total_spent'] += order.quantity * order.menu_item.price
        
        for preorder in user_preorders:
            category = self._get_simple_category(preorder.menu_item.name)
            if category not in preferences:
                preferences[category] = {'count': 0, 'total_spent': 0}
            preferences[category]['count'] += preorder.quantity
            preferences[category]['total_spent'] += preorder.quantity * preorder.menu_item.price
        
        # Определяем любимый ценовой диапазон
        all_prices = []
        for order in user_orders:
            all_prices.append(float(order.menu_item.price))
        for preorder in user_preorders:
            all_prices.append(float(preorder.menu_item.price))
        
        avg_price = sum(all_prices) / len(all_prices) if all_prices else 0
        min_price = avg_price * 0.7
        max_price = avg_price * 1.3
        
        # Находим блюда в любимых категориях и ценовом диапазоне
        favorite_categories = sorted(preferences.items(), key=lambda x: x[1]['count'], reverse=True)
        top_categories = [cat for cat, _ in favorite_categories[:3]]
        
        recommended = MenuItem.objects.filter(
            name__icontains__in=[cat for cat in top_categories],
            price__gte=min_price,
            price__lte=max_price,
            stock__gt=0
        ).exclude(
            id__in=user_orders.values('menu_item_id')
        ).exclude(
            id__in=user_preorders.values('menu_item_id')
        )[:limit]
        
        return recommended
    
    def _get_simple_category(self, item_name):
        """Простая категоризация по названию"""
        item_name_lower = item_name.lower()
        
        if any(word in item_name_lower for word in ['суп', 'борщ', 'уха', 'окрошка']):
            return 'супы'
        elif any(word in item_name_lower for word in ['котлета', 'мясо', 'курочка', 'гуляш', 'рыба']):
            return 'мясные блюда'
        elif any(word in item_name_lower for word in ['гарнир', 'картошка', 'гречка', 'рис', 'макароны']):
            return 'гарниры'
        elif any(word in item_name_lower for word in ['салат', 'овощи']):
            return 'салаты'
        elif any(word in item_name_lower for word in ['чай', 'кофе', 'сок', 'вода', 'напиток']):
            return 'напитки'
        elif any(word in item_name_lower for word in ['торт', 'пирог', 'конфет', 'мороженое']):
            return 'десерты'
        else:
            return 'основные блюда'
    
    def get_trending_items(self, days=7, limit=10):
        """Возвращает тренды за последние дни"""
        cutoff_date = timezone.now() - timedelta(days=days)
        
        recent_orders = OrderItem.objects.filter(
            order__order_date__gte=cutoff_date
        ).values('menu_item').annotate(
            recent_count=Count('id')
        )
        
        recent_preorders = PreOrderItem.objects.filter(
            pre_order__order_date__gte=cutoff_date
        ).values('menu_item').annotate(
            recent_count=Count('id')
        )
        
        trending = {}
        for item in recent_orders:
            item_id = item['menu_item']
            trending[item_id] = trending.get(item_id, 0) + item['recent_count']
        
        for item in recent_preorders:
            item_id = item['menu_item']
            trending[item_id] = trending.get(item_id, 0) + item['recent_count']
        
        # Сортировка и получение топ
        sorted_trending = sorted(trending.items(), key=lambda x: x[1], reverse=True)
        top_item_ids = [item_id for item_id, _ in sorted_trending[:limit]]
        
        return MenuItem.objects.filter(id__in=top_item_ids)
    
    def generate_recommendations(self, user, limit=10):
        """Генерирует персональные рекомендации для пользователя"""
        # Очищаем старые рекомендации
        Recommendation.objects.filter(user=user).delete()
        
        # Получаем разные типы рекомендаций
        popular_items = self.get_popular_items(limit * 2)
        high_rated_items = self.get_high_rated_items(limit * 2)
        collaborative_items = self.get_collaborative_recommendations(user, limit * 2)
        content_items = self.get_content_based_recommendations(user, limit * 2)
        trending_items = self.get_trending_items(days=7, limit=limit * 2)
        
        # Объединяем все рекомендации
        all_recommendations = []
        
        # Популярные блюда
        for i, popular in enumerate(popular_items[:limit]):
            score = self.weights['popularity'] * (1 - i * 0.1)  # Уменьшаем счет для менее популярных
            all_recommendations.append({
                'menu_item': popular.menu_item,
                'score': score,
                'reason': 'Популярно среди всех покупателей'
            })
        
        # Высокорейтинговые блюда
        for i, item in enumerate(high_rated_items[:limit]):
            score = self.weights['rating'] * (1 - i * 0.1)
            all_recommendations.append({
                'menu_item': item,
                'score': score,
                'reason': 'Высокий рейтинг от покупателей'
            })
        
        # Коллаборативные рекомендации
        for i, item_id in enumerate(collaborative_items[:limit]):
            try:
                item = MenuItem.objects.get(id=item_id)
                score = self.weights['collaborative'] * (1 - i * 0.1)
                all_recommendations.append({
                    'menu_item': item,
                    'score': score,
                    'reason': 'Покупают пользователи с похожими вкусами'
                })
            except MenuItem.DoesNotExist:
                continue
        
        # Контент-основанные рекомендации
        for i, item in enumerate(content_items[:limit]):
            score = self.weights['content_based'] * (1 - i * 0.1)
            all_recommendations.append({
                'menu_item': item,
                'score': score,
                'reason': 'Похоже на ваши предыдущие покупки'
            })
        
        # Тренды
        for i, item in enumerate(trending_items[:limit]):
            score = 0.15 * (1 - i * 0.1)  # Меньший вес для трендов
            all_recommendations.append({
                'menu_item': item,
                'score': score,
                'reason': 'Популярно в последнее время'
            })
        
        # Удаляем дубликаты и сортируем по счету
        seen_items = set()
        unique_recommendations = []
        
        for rec in all_recommendations:
            item_id = rec['menu_item'].id
            if item_id not in seen_items:
                seen_items.add(item_id)
                unique_recommendations.append(rec)
        
        unique_recommendations.sort(key=lambda x: x['score'], reverse=True)
        
        # Сохраняем рекомендации в базу
        final_recommendations = unique_recommendations[:limit]
        for rec in final_recommendations:
            Recommendation.objects.create(
                user=user,
                menu_item=rec['menu_item'],
                score=rec['score'],
                reason=rec['reason']
            )
        
        return final_recommendations
    
    def get_user_recommendations(self, user, limit=10):
        """Получает сохраненные рекомендации для пользователя"""
        return Recommendation.objects.filter(
            user=user
        ).select_related('menu_item').order_by('-score')[:limit]
