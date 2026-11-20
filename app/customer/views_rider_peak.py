"""Admin: peak-hour windows banana / band karna / hatana."""
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from ..models import RiderPeakWindow
from . import rider_peak
from .views_rider_portal import _admin_only


@_admin_only
def rider_peak_admin(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            name = (request.POST.get('name') or '').strip()[:60] or 'Peak'
            start = rider_peak.parse_time(request.POST.get('start'))
            end = rider_peak.parse_time(request.POST.get('end'))
            try:
                extra = Decimal((request.POST.get('extra') or '').strip())
            except (InvalidOperation, ValueError):
                extra = None
            days = sorted({int(d) for d in request.POST.getlist('days') if d.isdigit() and 0 <= int(d) <= 6})
            if not start or not end or start == end:
                messages.error(request, '❌ Choose a start and end time (they must be different).')
            elif extra is None or not extra.is_finite() or extra <= 0 or extra > rider_peak.MAX_EXTRA:
                messages.error(request, '❌ Enter an extra amount greater than 0.')
            else:
                RiderPeakWindow.objects.create(name=name, start_time=start, end_time=end,
                                               days=','.join(str(d) for d in days),
                                               extra_amount=extra.quantize(Decimal('0.01')))
                messages.success(request, f'🔥 Peak window "{name}" added.')
        elif action in ('toggle', 'delete'):
            w = get_object_or_404(RiderPeakWindow, pk=request.POST.get('window_id') or 0)
            if action == 'delete':
                w.delete()
                messages.success(request, 'Peak window deleted.')
            else:
                w.is_active = not w.is_active
                w.save(update_fields=['is_active'])
                messages.success(request, f'"{w.name}" is now {"ON" if w.is_active else "OFF"}.')
        else:
            messages.error(request, '❌ Invalid action.')
        return redirect('rider_peak_admin')
    rows = []
    for w in RiderPeakWindow.objects.all():
        days = rider_peak.parse_days(w.days)
        rows.append({'w': w, 'days_label': 'Every day' if not days else ', '.join(rider_peak.DAY_NAMES[d] for d in sorted(days))})
    return render(request, 'customer_portal/rider/peak_admin.html',
                  {'rows': rows, 'now_peak': rider_peak.current(), 'day_names': list(enumerate(rider_peak.DAY_NAMES))})
