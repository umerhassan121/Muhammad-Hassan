"""Frontend views: notifications (bell + full page).

Features: priority, categories, search/filters, pin / archive / snooze, bulk actions, grouping (model mein),
live count (latest_id). Rules (filters, snooze, ids ki safai) app/utils/notification_rules.py mein pure hain.
Security: mark-read / delete / archive wagera sirf apni notifications par (user=None wali sab ki shared hain:
unhein sirf 'read' kiya ja sakta hai).
"""
import json
from datetime import datetime, time as dtime

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import models
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_POST

from ...models import CompanyInfo, Notification
from ...utils import notification_rules as nr

BELL_LIMIT = 50
PAGE_SIZE = 25


# ---------------------------------------------------------------- helpers
def _nt_mine(user):
    """Apni + shared (user=None) notifications."""
    return Notification.objects.filter(models.Q(user=user) | models.Q(user__isnull=True))


def _nt_active(qs, now=None):
    """Archive nahi aur snooze nahi (snooze khatam ho gayi to wapas)."""
    now = now or timezone.now()
    return qs.filter(is_archived=False).filter(models.Q(snoozed_until__isnull=True) | models.Q(snoozed_until__lte=now))


def _nt_apply_filters(qs, f, now=None):
    now = now or timezone.now()
    if f['state'] == 'archived':
        qs = qs.filter(is_archived=True)
    elif f['state'] == 'snoozed':
        qs = qs.filter(is_archived=False, snoozed_until__gt=now)
    else:
        qs = _nt_active(qs, now)
    if f['category'] != 'all':
        qs = qs.filter(category=f['category'])
    if f['unread']:
        qs = qs.filter(is_read=False)
    if f['priority']:
        qs = qs.filter(priority=f['priority'])
    if f['type']:
        qs = qs.filter(notification_type=f['type'])
    if f['q']:
        qs = qs.filter(models.Q(title__icontains=f['q']) | models.Q(message__icontains=f['q']))
    tz = timezone.get_current_timezone()
    if f['date_from']:
        d = datetime.strptime(f['date_from'], '%Y-%m-%d')
        qs = qs.filter(created_at__gte=timezone.make_aware(datetime.combine(d, dtime.min), tz))
    if f['date_to']:
        d = datetime.strptime(f['date_to'], '%Y-%m-%d')
        qs = qs.filter(created_at__lte=timezone.make_aware(datetime.combine(d, dtime.max), tz))
    return qs


def _nt_order(qs):
    """Pinned pehle, phir unread Critical, phir naye."""
    crit = models.Case(models.When(priority='critical', is_read=False, then=1),
                       default=0, output_field=models.IntegerField())
    return qs.annotate(crit_rank=crit).order_by('-is_pinned', '-crit_rank', '-created_at', '-id')


def _nt_time_ago(created_at, now=None):
    diff = (now or timezone.now()) - created_at
    if diff.days > 0:
        return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
    if diff.seconds >= 3600:
        h = diff.seconds // 3600
        return f"{h} hour{'s' if h > 1 else ''} ago"
    if diff.seconds >= 60:
        m = diff.seconds // 60
        return f"{m} minute{'s' if m > 1 else ''} ago"
    return 'Just now'


def _nt_json(n, now):
    return {
        'id': n.id, 'title': n.title, 'message': n.message,
        'notification_type': n.notification_type, 'category': n.category,
        'category_label': n.get_category_display(),
        'priority': n.priority, 'is_pinned': n.is_pinned, 'is_archived': n.is_archived,
        'group_count': n.group_count, 'is_read': n.is_read, 'link': n.link,
        'snoozed_until': timezone.localtime(n.snoozed_until).strftime('%d %b, %I:%M %p') if n.snoozed_until else '',
        'time_ago': _nt_time_ago(n.created_at, now),
        'created_at': n.created_at.strftime('%Y-%m-%d %H:%M:%S'),
    }


def _nt_category_counts(user, now=None):
    """Active (archive/snooze ke bina) notifications ki ginti, category-wise - ek hi query mein."""
    rows = _nt_active(_nt_mine(user), now).order_by().values('category').annotate(n=models.Count('id'))
    counts = {r['category']: r['n'] for r in rows}
    out = {cid: counts.get(cid, 0) for cid in nr.CATEGORY_KEYS if cid != 'all'}
    out['all'] = sum(counts.values())
    return out


def _nt_body(request):
    try:
        return json.loads(request.body or b'{}')
    except (ValueError, UnicodeDecodeError):
        return {}


# ---------------------------------------------------------------- bell API
@login_required
def get_notifications_api(request):
    """Bell ki list: category / q / unread / priority / type filters ke saath."""
    f = nr.parse_filters(request.GET)
    now = timezone.now()
    qs = _nt_order(_nt_apply_filters(_nt_mine(request.user), f, now))[:BELL_LIMIT]
    data = [_nt_json(n, now) for n in qs]
    unread = _nt_active(_nt_mine(request.user), now).filter(is_read=False).count()
    return JsonResponse({
        'success': True, 'notifications': data, 'unread_count': unread,
        'category_counts': _nt_category_counts(request.user, now),
        'current_category': f['category'], 'total': len(data),
    })


@login_required
def get_unread_count(request):
    """Count + latest_id (live update ke liye) + kitni unread Critical/High hain."""
    base = _nt_active(_nt_mine(request.user)).filter(is_read=False)
    agg = base.aggregate(
        n=models.Count('id'), latest=models.Max('id'),
        crit=models.Count('id', filter=models.Q(priority='critical')),
        high=models.Count('id', filter=models.Q(priority='high')))
    return JsonResponse({'unread_count': agg['n'], 'latest_id': agg['latest'] or 0,
                         'critical_unread': agg['crit'], 'high_unread': agg['high']})


@login_required
def get_notification_categories(request):
    counts = _nt_category_counts(request.user)
    return JsonResponse({'success': True, 'categories': [
        {'id': cid, 'name': name, 'icon': icon, 'count': counts.get(cid, 0)} for cid, name, icon in nr.CATEGORIES]})


# ---------------------------------------------------------------- actions
@login_required
@require_POST
def mark_notification_read(request, pk):
    n = _nt_mine(request.user).filter(pk=pk).update(is_read=True)
    return JsonResponse({'success': bool(n), **({} if n else {'message': 'Notification not found'})})


@login_required
@require_POST
def mark_all_notifications_read(request):
    _nt_active(_nt_mine(request.user)).filter(is_read=False).update(is_read=True)
    return JsonResponse({'success': True})


@login_required
@require_POST
def mark_category_read(request):
    category = _nt_body(request).get('category', '')
    qs = _nt_active(_nt_mine(request.user)).filter(is_read=False)
    if category and category != 'all':
        if category not in nr.CATEGORY_KEYS:
            return JsonResponse({'success': False, 'message': 'Unknown category'}, status=400)
        qs = qs.filter(category=category)
    qs.update(is_read=True)
    return JsonResponse({'success': True})


@login_required
@require_POST
def delete_notification(request, pk):
    n, _ = Notification.objects.filter(pk=pk, user=request.user).delete()     # sirf apni
    return JsonResponse({'success': bool(n), **({} if n else {'message': 'Notification not found'})})


@login_required
@require_POST
def delete_all_notifications(request):
    category = _nt_body(request).get('category', 'all')
    qs = Notification.objects.filter(user=request.user)
    if category != 'all':
        if category not in nr.CATEGORY_KEYS:
            return JsonResponse({'success': False, 'message': 'Unknown category'}, status=400)
        qs = qs.filter(category=category)
    qs.delete()
    return JsonResponse({'success': True})


@login_required
@require_POST
def notification_bulk_action(request):
    """Ek ya kai notifications par action. JSON: {ids: [..], action: read|unread|archive|unarchive|pin|unpin|
    delete|snooze|unsnooze, option: '1h'|'3h'|'tomorrow'|'1w'|minutes (snooze ke liye)}."""
    body = _nt_body(request)
    action = body.get('action')
    ids = nr.clean_ids(body.get('ids'))
    if action not in nr.ACTIONS:
        return JsonResponse({'success': False, 'message': 'Unknown action'}, status=400)
    if not ids:
        return JsonResponse({'success': False, 'message': 'Nothing selected'}, status=400)

    qs = Notification.objects.filter(pk__in=ids)
    qs = qs.filter(user=request.user) if action in nr.OWN_ONLY_ACTIONS else qs.filter(
        models.Q(user=request.user) | models.Q(user__isnull=True))

    if action == 'delete':
        n, _ = qs.delete()
    elif action == 'read':
        n = qs.update(is_read=True)
    elif action == 'unread':
        n = qs.update(is_read=False)
    elif action == 'archive':
        n = qs.update(is_archived=True, is_pinned=False, is_read=True)
    elif action == 'unarchive':
        n = qs.update(is_archived=False)
    elif action == 'pin':
        n = qs.update(is_pinned=True, is_archived=False)
    elif action == 'unpin':
        n = qs.update(is_pinned=False)
    elif action == 'snooze':
        until = nr.snooze_deadline(timezone.localtime(), str(body.get('option', '')))
        if until is None:
            return JsonResponse({'success': False, 'message': 'Invalid snooze time'}, status=400)
        n = qs.update(snoozed_until=until)
    else:  # unsnooze
        n = qs.update(snoozed_until=None)
    return JsonResponse({'success': True, 'changed': n})


# ---------------------------------------------------------------- full page
@login_required
def notification_list_page(request):
    f = nr.parse_filters(request.GET)
    now = timezone.now()
    qs = _nt_order(_nt_apply_filters(_nt_mine(request.user), f, now))
    page_obj = Paginator(qs, PAGE_SIZE).get_page(request.GET.get('page', 1))
    counts = _nt_category_counts(request.user, now)
    mine = _nt_mine(request.user)
    # page ke links mein filters bane rahen (page chhod kar)
    keep = {k: v for k, v in request.GET.items() if k != 'page' and v}
    from urllib.parse import urlencode
    return render(request, 'notifications/list.html', {
        'company_name': CompanyInfo.objects.first().name if CompanyInfo.objects.exists() else 'ERP System',
        'page_obj': page_obj, 'notifications': page_obj,
        'categories': [{'id': cid, 'name': name, 'icon': icon, 'count': counts.get(cid, 0)}
                       for cid, name, icon in nr.CATEGORIES],
        'current_category': f['category'], 'f': f,
        'priorities': nr.PRIORITIES,
        'archived_count': mine.filter(is_archived=True).count(),
        'snoozed_count': mine.filter(is_archived=False, snoozed_until__gt=now).count(),
        'qs_keep': urlencode(keep),
        'qs_no_category': urlencode({k: v for k, v in keep.items() if k != 'category'}),
    })
