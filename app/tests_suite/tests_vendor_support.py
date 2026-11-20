"""
Tests: vendor support tickets (ticket kholna -> admin jawab -> vendor jawab -> band / dobara khulna).

Run:  python manage.py test app.tests_suite.tests_vendor_support -v 2

NOTE: written by reading the code, without a Django project to run it in. If a fixture line fails on a
field name, fix it in setUp - the assertions are what matter.

Expected:
    create_ticket                 -> status 'open', 1 message (vendor), number 'T-<id>'
    empty subject or body         -> SupportError
    6th open ticket               -> SupportError (limit 5)
    admin_reply                   -> status 'answered', vendor_unread True, 2nd message is_admin
    admin_reply(close=True)       -> status 'closed', closed_at set
    vendor_reply on answered      -> status 'open'
    vendor_reply on closed        -> SupportError
    reopen closed                 -> status 'open', closed_at None
    mark_seen                     -> vendor_unread False
"""
from django.contrib.auth.models import User
from django.test import TestCase

from app.customer import vendor_support as vs
from app.models import Vendor, VendorProfile


class SupportBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('vend', 'v@x.com', 'pw12345!')
        self.vendor = Vendor.objects.create(name='Pizza Hub')
        self.profile = VendorProfile.objects.create(
            vendor=self.vendor, user=self.user, business_name='Pizza Hub', is_approved=True)
        self.admin = User.objects.create_superuser('boss', 'b@x.com', 'x')

    def new(self, subject='Payout late'):
        return vs.create_ticket(self.profile, self.user, subject, 'payments', 'Mera payout nahi aaya')


class TicketFlowTests(SupportBase):
    def test_create(self):
        t = self.new()
        self.assertEqual(t.status, 'open')
        self.assertEqual(t.messages.count(), 1)
        self.assertFalse(t.messages.first().is_admin)
        self.assertEqual(t.number, f'T-{t.pk}')

    def test_blank_rejected(self):
        with self.assertRaises(vs.SupportError):
            vs.create_ticket(self.profile, self.user, '  ', 'other', 'x')
        with self.assertRaises(vs.SupportError):
            vs.create_ticket(self.profile, self.user, 'x', 'other', '')

    def test_open_limit(self):
        for i in range(vs.MAX_OPEN_TICKETS):
            self.new(f'T{i}')
        with self.assertRaises(vs.SupportError):
            self.new('one too many')

    def test_admin_reply_then_vendor_reply(self):
        t = self.new()
        vs.admin_reply(t, self.admin, 'Kal tak ho jayega')
        t.refresh_from_db()
        self.assertEqual(t.status, 'answered')
        self.assertTrue(t.vendor_unread)
        self.assertTrue(t.messages.last().is_admin)
        vs.vendor_reply(t, self.user, 'Shukriya')
        t.refresh_from_db()
        self.assertEqual(t.status, 'open')
        self.assertEqual(t.messages.count(), 3)

    def test_admin_close_and_reopen(self):
        t = self.new()
        vs.admin_reply(t, self.admin, 'Hal ho gaya', close=True)
        t.refresh_from_db()
        self.assertEqual(t.status, 'closed')
        self.assertIsNotNone(t.closed_at)
        with self.assertRaises(vs.SupportError):
            vs.vendor_reply(t, self.user, 'aur ek baat')
        vs.reopen_ticket(t)
        t.refresh_from_db()
        self.assertEqual(t.status, 'open')
        self.assertIsNone(t.closed_at)

    def test_mark_seen(self):
        t = self.new()
        vs.admin_reply(t, self.admin, 'ok')
        t.refresh_from_db()
        vs.mark_seen(t)
        t.refresh_from_db()
        self.assertFalse(t.vendor_unread)

    def test_other_store_cannot_see_ticket(self):
        t = self.new()
        other_user = User.objects.create_user('v2', 'v2@x.com', 'pw12345!')
        other = VendorProfile.objects.create(
            vendor=Vendor.objects.create(name='Burger Hub'), user=other_user,
            business_name='Burger Hub', is_approved=True)
        self.assertFalse(other.support_tickets.filter(pk=t.pk).exists())
