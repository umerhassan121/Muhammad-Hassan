"""python manage.py create_dark_store --name "Mart Lahore" --city Lahore --address "Shop 5, Gulberg" \
        --phone 03001234567 --lat 31.5204 --lng 74.3587 --areas "Gulberg, DHA, Johar Town"

Company ka apna dark store (Talabat Mart jaisa) banata hai: vendor login + approved store + is_dark_store.
Dobara chalane par (same --phone) usi store ko update karta hai, naya nahi banata.
Password na do to khud ek random password banta hai aur ek hi dafa screen par dikhta hai.
"""
import secrets
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from app.models import StoreCategory, Vendor, VendorProfile
from app.utils.phone_utils import find_by_phone, phone_key


class Command(BaseCommand):
    help = "Creates (or updates) a company-owned dark store (Mart): platform riders, auto-accept, fast delivery."

    def add_arguments(self, p):
        p.add_argument('--name', required=True, help='Store ka naam, jaise "Mart Lahore"')
        p.add_argument('--city', required=True)
        p.add_argument('--address', required=True)
        p.add_argument('--phone', required=True, help='Store ka login / contact number')
        p.add_argument('--email', default='')
        p.add_argument('--password', default='')
        p.add_argument('--lat', type=Decimal, default=None, help='Store ki latitude (rider dispatch ke liye zaroori)')
        p.add_argument('--lng', type=Decimal, default=None, help='Store ki longitude')
        p.add_argument('--areas', default='', help='Deliver wale areas, comma se alag')
        p.add_argument('--max-km', type=Decimal, default=Decimal('5'), help='Zyada se zyada delivery distance (km), default 5')
        p.add_argument('--time-min', type=int, default=10)
        p.add_argument('--time-max', type=int, default=20)
        p.add_argument('--min-order', type=Decimal, default=Decimal('0'))

    @transaction.atomic
    def handle(self, *a, **o):
        if o['time_min'] <= 0 or o['time_max'] < o['time_min']:
            raise CommandError('time-min / time-max theek nahi (time-max, time-min se chhota nahi ho sakta).')
        digits = phone_key(o['phone'])
        if len(digits) < 10:
            raise CommandError('Phone number theek nahi.')

        category, _ = StoreCategory.objects.get_or_create(
            name='Mart', defaults={'icon': '\u26a1', 'sort_order': 0, 'is_active': True})

        existing = find_by_phone(Vendor, o['phone'])
        password_shown = ''
        if existing:
            vendor = existing[0]
            profile = VendorProfile.objects.filter(vendor=vendor).first()
            if profile is None:
                raise CommandError(f'Is phone ka Vendor ({vendor.name}) maujood hai lekin us ka portal account nahi. '
                                   'Dusra phone do.')
            created = False
        else:
            username, n = f'vendor_{digits}', 1
            while User.objects.filter(username=username).exists():
                username, n = f'vendor_{digits}_{n}', n + 1
            password = o['password'] or secrets.token_urlsafe(10)
            password_shown = '' if o['password'] else password
            user = User.objects.create_user(username=username, email=o['email'], password=password,
                                            first_name=o['name'][:30])
            vendor = Vendor(name=o['name'], contact_number=o['phone'], address=f"{o['address']}, {o['city']}")
            vendor._skip_notify = True
            vendor.save()
            profile = VendorProfile(vendor=vendor, user=user, business_name=o['name'], city=o['city'],
                                    is_approved=True, approved_at=timezone.now(), last_login_at=timezone.now())
            created = True

        profile.business_name = o['name']
        profile.city = o['city']
        profile.store_category = category
        profile.is_dark_store = True               # save() delivery_by=platform, auto_accept, commission 0 khud lagata hai
        profile.is_approved = True
        profile.delivery_time_min, profile.delivery_time_max = o['time_min'], o['time_max']
        profile.max_delivery_km = o['max_km']
        profile.min_order_amount = o['min_order']
        if o['lat'] is not None and o['lng'] is not None:
            profile.lat, profile.lng = o['lat'], o['lng']
        if o['areas']:
            profile.delivery_areas = ', '.join(VendorProfile.clean_areas(o['areas']))
        profile.save()

        self.stdout.write(self.style.SUCCESS(f"{'Created' if created else 'Updated'} dark store: {profile.business_name}"))
        if created:
            self.stdout.write(f"  Login username: {profile.user.username}")
            if password_shown:
                self.stdout.write(f"  Password (sirf ab dikhta hai, note kar lein): {password_shown}")
        if profile.lat is None or profile.lng is None:
            self.stdout.write(self.style.WARNING(
                '  lat/lng nahi di: rider ki dispatch nazdeeki se nahi hogi. --lat / --lng ke saath dobara chalayein.'))
        self.stdout.write('  Ab is store ke login se products add karein (vendor portal), aur stock default warehouse mein rakhein.')
