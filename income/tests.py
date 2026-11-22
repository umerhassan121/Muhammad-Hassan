from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import IncomeSource


class IncomeSourceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.u1 = User.objects.create_user(username='u1', password='pass12345')
        self.u2 = User.objects.create_user(username='u2', password='pass12345')

    def test_login_required(self):
        r = self.client.get(reverse('income:source_list'))
        self.assertEqual(r.status_code, 302)

    def test_add_and_list(self):
        self.client.login(username='u1', password='pass12345')
        r = self.client.post(reverse('income:source_add'), {'name': 'Shop sales', 'source_type': 'business', 'notes': ''})
        self.assertRedirects(r, reverse('income:source_list'))
        self.assertEqual(IncomeSource.objects.filter(owner=self.u1).count(), 1)
        self.assertContains(self.client.get(reverse('income:source_list')), 'Shop sales')

    def test_duplicate_name_rejected_case_insensitive(self):
        self.client.login(username='u1', password='pass12345')
        IncomeSource.objects.create(owner=self.u1, name='Rent')
        r = self.client.post(reverse('income:source_add'), {'name': 'rent', 'source_type': 'rent', 'notes': ''})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(IncomeSource.objects.filter(owner=self.u1).count(), 1)

    def test_each_user_sees_only_own(self):
        IncomeSource.objects.create(owner=self.u2, name='Secret')
        self.client.login(username='u1', password='pass12345')
        self.assertNotContains(self.client.get(reverse('income:source_list')), 'Secret')

    def test_same_name_allowed_for_other_user(self):
        IncomeSource.objects.create(owner=self.u2, name='Salary')
        self.client.login(username='u1', password='pass12345')
        r = self.client.post(reverse('income:source_add'), {'name': 'Salary', 'source_type': 'salary', 'notes': ''})
        self.assertRedirects(r, reverse('income:source_list'))
