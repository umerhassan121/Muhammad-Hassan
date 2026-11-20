"""
Tests: dark store (Mart) - VendorProfile.is_dark_store.

Run:  python manage.py test app.tests_suite.tests_dark_store -v 2

NOTE: written by reading the code, without a Django project to run it in. If a fixture line fails on
a field name, fix it in setUp - the assertions are what matter.
"""
from decimal import Decimal
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase

from app.models import Vendor, VendorProfile


def make_profile(name='Shop', phone='03001110000', **kw):
    user = User.objects.create_user(username=f'u_{phone}', password='x-Strong-pass-1')
    vendor = Vendor(name=name, contact_number=phone)
    vendor._skip_notify = True
    vendor.save()
    return VendorProfile.objects.create(vendor=vendor, user=user, business_name=name, is_approved=True, **kw)


class DarkStoreModelTests(TestCase):
    def test_flag_forces_platform_delivery_and_auto_accept(self):
        p = make_profile(is_dark_store=True)
        p.refresh_from_db()
        self.assertEqual(p.delivery_by, 'platform')
        self.assertTrue(p.auto_accept)
        self.assertEqual(p.commission_percent, Decimal('0'))

    def test_own_commission_is_kept(self):
        p = make_profile(phone='03001110001', is_dark_store=True, commission_percent=Decimal('4'))
        p.refresh_from_db()
        self.assertEqual(p.commission_percent, Decimal('4'))

    def test_normal_store_is_untouched(self):
        p = make_profile(phone='03001110002')
        p.refresh_from_db()
        self.assertEqual(p.delivery_by, 'vendor')
        self.assertFalse(p.auto_accept)
        self.assertIsNone(p.commission_percent)

    def test_dark_store_uses_its_own_delivery_time(self):
        p = make_profile(phone='03001110003', is_dark_store=True, delivery_time_min=10, delivery_time_max=20)
        self.assertEqual((p.eff_time_min, p.eff_time_max), (10, 20))

    def test_update_fields_save_still_applies_rules(self):
        p = make_profile(phone='03001110004')
        p.is_dark_store = True
        p.save(update_fields=['is_dark_store'])
        p.refresh_from_db()
        self.assertEqual(p.delivery_by, 'platform')
        self.assertTrue(p.auto_accept)


class CreateDarkStoreCommandTests(TestCase):
    ARGS = dict(name='Mart Lahore', city='Lahore', address='Shop 5, Gulberg', phone='03001234567',
                lat='31.5204', lng='74.3587', areas='Gulberg, DHA')

    def run_cmd(self):
        out = StringIO()
        call_command('create_dark_store', stdout=out, **self.ARGS)
        return out.getvalue()

    def test_creates_dark_store(self):
        out = self.run_cmd()
        self.assertIn('Created dark store', out)
        p = VendorProfile.objects.get(business_name='Mart Lahore')
        self.assertTrue(p.is_dark_store and p.is_approved)
        self.assertEqual(p.delivery_by, 'platform')
        self.assertEqual((p.delivery_time_min, p.delivery_time_max), (10, 20))
        self.assertEqual(p.store_category.name, 'Mart')

    def test_second_run_updates_instead_of_duplicating(self):
        self.run_cmd()
        out = self.run_cmd()
        self.assertIn('Updated dark store', out)
        self.assertEqual(VendorProfile.objects.filter(business_name='Mart Lahore').count(), 1)
