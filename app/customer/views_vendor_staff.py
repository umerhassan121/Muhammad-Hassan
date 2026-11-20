"""Vendor portal: store ka staff (manager / orders-only login). Sirf owner dekh sakta hai.

- vendor_staff        : /shop/vendor/staff/  (list + naya staff)
- vendor_staff_action : toggle (band/chalu), password reset, delete
"""
import logging

from django.contrib import messages
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ..decorators import vendor_login_required
from ..models import Vendor, VendorProfile, VendorStaff
from .views_customer_auth import is_valid_phone, normalize_phone
from .vendor_access import get_vendor_profile

logger = logging.getLogger(__name__)

MAX_STAFF = 30


def _pw_error(password, hints):
    from ..utils.password_policy import first_error
    return first_error(password, hints)


def _owner_stores(owner):
    """Owner ke saare stores: main + branches."""
    return [owner] + list(owner.branches.all())


def _owner_staff(owner):
    return (VendorStaff.objects.filter(Q(store=owner) | Q(store__parent=owner))
            .select_related('user', 'store').prefetch_related('extra_stores'))


def _chosen_stores(post, owner):
    """Form se chune hue stores (sirf is owner ke). -> list, pehla = staff ka apna store."""
    allowed = {str(p.pk): p for p in _owner_stores(owner)}
    out = []
    for v in post.getlist('stores'):
        if v in allowed and allowed[v] not in out:
            out.append(allowed[v])
    return out


def _set_stores(rec, stores):
    """Pehla store primary, baqi extra_stores."""
    if rec.store_id not in [p.pk for p in stores]:
        rec.store = stores[0]
        rec.save(update_fields=['store'])
    rec.extra_stores.set([p for p in stores if p.pk != rec.store_id])


def _phone_taken(phone):
    return (VendorStaff.objects.filter(phone=phone).exists()
            or Vendor.objects.filter(contact_number=phone).exists())


def _create(request, owner):
    post = request.POST
    stores = _chosen_stores(post, owner)
    name = post.get('name', '').strip()[:80]
    phone_raw = post.get('phone', '').strip()[:20]
    role = post.get('role', '')
    password = post.get('password', '')

    if len(name) < 2:
        return '❌ Enter the staff name'
    if role not in dict(VendorStaff.ROLE_CHOICES):
        return '❌ Choose a role'
    if not phone_raw or not is_valid_phone(phone_raw):
        return '❌ Enter a valid phone number'
    phone = normalize_phone(phone_raw)
    if _phone_taken(phone):
        return '❌ This phone number is already used by another account'
    err = _pw_error(password, (name, phone))
    if err:
        return f'❌ {err}'
    if not stores:
        return '❌ Choose at least one store where the staff will work'
    if _owner_staff(owner).count() >= MAX_STAFF:
        return f'❌ You can have at most {MAX_STAFF} staff'

    with transaction.atomic():
        user = User.objects.create_user(
            username=f'vstaff_{owner.pk}_{phone.lstrip("+")}', password=password,
            first_name=name[:150])
        rec = VendorStaff.objects.create(store=stores[0], user=user, name=name, phone=phone, role=role)
        rec.extra_stores.set(stores[1:])
    messages.success(request, f'✅ Login created for {name}. They will log in with {phone} and their own password.')
    return None


@vendor_login_required
def vendor_staff(request):
    owner = request.user.vendor_profile
    if request.method == 'POST':
        try:
            err = _create(request, owner)
            if err:
                messages.error(request, err)
        except Exception:
            logger.exception('Vendor staff create error')
            messages.error(request, '❌ Something went wrong. Please try again')
        return redirect('vendor_staff')

    stores = _owner_stores(owner)
    staff = list(_owner_staff(owner))
    for s_ in staff:
        s_.store_ids = {s_.store_id} | {p.pk for p in s_.extra_stores.all()}
    return render(request, 'customer_portal/vendor/staff.html', {
        'profile': owner,
        'stores': stores,
        'multi': len(stores) > 1,
        'staff': staff,
        'roles': VendorStaff.ROLE_CHOICES,
        'max_staff': MAX_STAFF,
    })


@vendor_login_required
@require_POST
def vendor_staff_action(request, pk, action):
    owner = request.user.vendor_profile
    rec = get_object_or_404(_owner_staff(owner), pk=pk)

    if action == 'toggle':
        rec.is_active = not rec.is_active
        rec.save(update_fields=['is_active'])
        messages.success(request, f'✅ {rec.name} ' + ('turned on.' if rec.is_active else 'turned off (they cannot log in).'))
    elif action == 'password':
        password = request.POST.get('password', '')
        err = _pw_error(password, (rec.name, rec.phone))
        if err:
            messages.error(request, f'❌ {err}')
        else:
            rec.user.set_password(password)
            rec.user.save(update_fields=['password'])
            messages.success(request, f'✅ A new password was set for {rec.name}.')
    elif action == 'role':
        role = request.POST.get('role', '')
        if role in dict(VendorStaff.ROLE_CHOICES):
            rec.role = role
            rec.save(update_fields=['role'])
            messages.success(request, f'✅ {rec.name} ka role badal diya.')
    elif action == 'stores':
        stores = _chosen_stores(request.POST, owner)
        if not stores:
            messages.error(request, '❌ Choose at least one store.')
        else:
            _set_stores(rec, stores)
            messages.success(request, f'✅ {rec.name} ke stores update ho gaye.')
    elif action == 'delete':
        user = rec.user
        name = rec.name
        with transaction.atomic():
            rec.delete()
            user.delete()
        messages.success(request, f'🗑️ {name} ka login hata diya.')
    else:
        messages.error(request, '❌ Galat action.')
    return redirect('vendor_staff')


@vendor_login_required
@require_POST
def vendor_switch_store(request):
    """Owner ya multi-store staff: kaam ka store badlo (dashboard ke switcher se)."""
    from .vendor_access import SESSION_KEY, accessible_profiles
    profiles = accessible_profiles(request.user)
    try:
        wanted = int(request.POST.get('store', 0))
    except (TypeError, ValueError):
        wanted = 0
    target = next((p for p in profiles if p.pk == wanted), None)
    if target is None:
        messages.error(request, '❌ You do not have access to this store.')
        return redirect('vendor_dashboard')
    if target.pk == profiles[0].pk:
        request.session.pop(SESSION_KEY, None)      # apna asal (main) store
    else:
        request.session[SESSION_KEY] = target.pk
    messages.success(request, f'🏪 You are now managing "{target.business_name}".')
    return redirect('vendor_dashboard')
