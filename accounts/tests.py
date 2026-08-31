from django.test import TestCase
from django.urls import reverse
from .models import CustomUser


class RoleBasedAccessTests(TestCase):
    def setUp(self):
        self.owner = CustomUser.objects.create_user(username='owner_test', password='testpass123', role='admin')
        self.staff = CustomUser.objects.create_user(username='staff_test', password='testpass123', role='staff')
        self.restricted_urls = [
            reverse('supplier_list'),
            reverse('expense_list'),
            reverse('advisor_list'),
            reverse('customer_insights:insights_dashboard'),
            reverse('blockchain:verify_ledger'),
            reverse('register'),
        ]
        self.staff_permitted_urls = [
            reverse('product_list'),
            reverse('category_list'),
            reverse('inventory_list'),
            reverse('sale_list'),
            reverse('zone_list'),
            reverse('delivery_order_list'),
            reverse('notification_list'),
        ]

    def test_owner_can_access_restricted_urls(self):
        self.client.login(username='owner_test', password='testpass123')
        for url in self.restricted_urls:
            response = self.client.get(url)
            self.assertIn(response.status_code, (200, 302), f"Owner should reach {url}, got {response.status_code}")

    def test_staff_forbidden_from_restricted_urls_by_direct_url(self):
        self.client.login(username='staff_test', password='testpass123')
        for url in self.restricted_urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 403, f"Staff should get 403 on {url}, got {response.status_code}")

    def test_staff_can_access_permitted_urls(self):
        self.client.login(username='staff_test', password='testpass123')
        for url in self.staff_permitted_urls:
            response = self.client.get(url)
            self.assertIn(response.status_code, (200, 302), f"Staff should reach {url}, got {response.status_code}")

    def test_anonymous_redirected_to_login_on_restricted_url(self):
        response = self.client.get(reverse('supplier_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_staff_cannot_register_new_accounts(self):
        self.client.login(username='staff_test', password='testpass123')
        response = self.client.get(reverse('register'))
        self.assertEqual(response.status_code, 403)

    def test_advisor_message_ajax_endpoint_blocked_for_staff(self):
        # Confirms the AJAX endpoint is protected, not just the page —
        # session id doesn't need to be real since the 403 fires before lookup.
        self.client.login(username='staff_test', password='testpass123')
        response = self.client.post(reverse('advisor_message', args=[1]), data='{}', content_type='application/json')
        self.assertEqual(response.status_code, 403)


class LoginFlowTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(username='logintest', password='correct-pass', role='staff')

    def test_valid_login_redirects_to_dashboard(self):
        response = self.client.post(reverse('login'), {'username': 'logintest', 'password': 'correct-pass'})
        self.assertRedirects(response, reverse('dashboard'))

    def test_invalid_login_shows_error_and_stays_on_page(self):
        response = self.client.post(reverse('login'), {'username': 'logintest', 'password': 'wrong-pass'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any('Invalid' in str(m) for m in response.context['messages']))

    def test_empty_fields_do_not_500(self):
        response = self.client.post(reverse('login'), {'username': '', 'password': ''})
        self.assertEqual(response.status_code, 200)

    def test_logout_redirects_to_login(self):
        self.client.login(username='logintest', password='correct-pass')
        response = self.client.get(reverse('logout'))
        self.assertRedirects(response, reverse('login'))
