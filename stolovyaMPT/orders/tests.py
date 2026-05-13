from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from .models import MenuItem, Order, OrderItem

User = get_user_model()


class ModelTests(TestCase):

    def test_menu_item_creation(self):
        item = MenuItem.objects.create(
            name='Борщ',
            description='Свекольный суп',
            price=150,
            stock=10
        )
        self.assertEqual(item.name, 'Борщ')
        self.assertEqual(item.price, 150)
        self.assertTrue(item.is_available(1))

    def test_menu_item_unavailable(self):
        item = MenuItem.objects.create(
            name='Суп',
            description='Овощной суп',
            price=100,
            stock=0
        )
        self.assertFalse(item.is_available(1))


class ViewTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            user_type='customer'
        )
        self.admin = User.objects.create_superuser(
            username='admin',
            password='adminpass123'
        )

    def test_login_page_loads(self):
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'registration/login.html')

    def test_user_can_login(self):
        response = self.client.post(reverse('login'), {
            'username': 'testuser',
            'password': 'testpass123'
        })
        self.assertEqual(response.status_code, 302)

    def test_menu_requires_login(self):
        response = self.client.get(reverse('menu'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_menu_loads_for_authenticated_user(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('menu'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'orders/menu.html')


class OrderTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='customer1',
            password='pass123',
            user_type='customer'
        )
        self.item = MenuItem.objects.create(
            name='Пицца',
            description='Вкусная пицца',
            price=350,
            stock=20
        )

    def test_order_creation(self):
        self.client.login(username='customer1', password='pass123')

        response = self.client.post(
            reverse('place_order', kwargs={'item_id': self.item.id}),
            {'quantity': 2}
        )

        self.assertEqual(response.status_code, 302)

        order = Order.objects.filter(customer=self.user).first()
        self.assertIsNotNone(order)
        self.assertEqual(order.orderitem_set.first().quantity, 2)

    def test_stock_decreases_after_order(self):
        initial_stock = self.item.stock

        self.client.login(username='customer1', password='pass123')
        self.client.post(
            reverse('place_order', kwargs={'item_id': self.item.id}),
            {'quantity': 3}
        )

        self.item.refresh_from_db()
        self.assertEqual(self.item.stock, initial_stock - 3)

    def test_cannot_order_more_than_stock(self):
        self.item.stock = 2
        self.item.save()

        self.client.login(username='customer1', password='pass123')
        response = self.client.post(
            reverse('place_order', kwargs={'item_id': self.item.id}),
            {'quantity': 10}
        )

        self.assertEqual(response.status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock, 2)


class SecurityTests(TestCase):

    def test_csrf_protection(self):
        self.client.login(username='testuser', password='testpass123')

        response = self.client.post('/order/1/', {'quantity': 1})
        self.assertEqual(response.status_code, 403)

    def test_xss_protection_in_search(self):
        self.client.login(username='testuser', password='testpass123')

        xss_payload = "<script>alert('XSS')</script>"
        response = self.client.get(reverse('menu'), {'search': xss_payload})

        self.assertNotContains(response, "<script>alert('XSS')</script>")
        self.assertContains(response, "&lt;script&gt