from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import IncomeSourceForm
from .models import IncomeSource


@login_required
def source_list(request):
    sources = IncomeSource.objects.filter(owner=request.user)
    return render(request, 'income/source_list.html', {
        'sources': sources,
        'active_count': sources.filter(is_active=True).count(),
        'total_count': sources.count(),
    })


@login_required
def source_add(request):
    if request.method == 'POST':
        form = IncomeSourceForm(request.POST, owner=request.user)
        if form.is_valid():
            source = form.save(commit=False)
            source.owner = request.user
            source.save()
            messages.success(request, 'Income source "%s" added.' % source.name)
            return redirect('income:source_list')
    else:
        form = IncomeSourceForm(owner=request.user)
    return render(request, 'income/source_form.html', {'form': form})
