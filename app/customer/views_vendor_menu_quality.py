"""Vendor portal: Menu quality score.

- vendor_menu_quality : /shop/vendor/menu-quality/   score, 'menu X% complete', aur har kamzor item ka fix link
Hisaab products ki maujooda fields (photo, description, naam) se; koi naya data / migration nahi.
"""
from django.contrib import messages
from django.shortcuts import redirect, render

from ..decorators import vendor_login_required
from ..models import Product
from ..utils import menu_quality_rules as rules
from .vendor_access import get_vendor_profile

MAX_ROWS = 500          # ek page par kitne items tak (sab se kamzor pehle)


def menu_quality(profile):
    """-> (summary dict, items list). items sab se kamzor pehle; sirf wo jin mein koi kami hai."""
    qs = (Product.objects.filter(vendor=profile.vendor).exclude(approval_status='rejected')
          .select_related('category').only('id', 'name', 'description', 'image', 'category', 'category__name', 'is_active')
          .order_by('name'))
    checked = []
    for p in qs:
        res = rules.item_check(p.name, p.description, bool(p.image))
        checked.append({'product': p, **res, 'issue_text': [rules.ISSUE_TEXT[i] for i in res['issues']]})
    summary = rules.summarize(checked)
    if summary['score'] is not None:
        summary['label'], summary['tone'] = rules.label(summary['score'])
    weak = sorted((c for c in checked if c['issues']), key=lambda c: (c['score'], c['product'].name.lower()))
    return summary, weak[:MAX_ROWS]


@vendor_login_required
def vendor_menu_quality(request):
    profile = get_vendor_profile(request.user)
    if not profile.is_approved:
        messages.warning(request, '⏳ Your account has not been approved yet.')
        return redirect('vendor_dashboard')
    summary, weak = menu_quality(profile)
    return render(request, 'customer_portal/vendor/menu_quality.html', {
        'profile': profile, 'summary': summary, 'weak': weak,
        'weights': {'photo': rules.W_PHOTO, 'desc': rules.W_DESC, 'name': rules.W_NAME},
    })
