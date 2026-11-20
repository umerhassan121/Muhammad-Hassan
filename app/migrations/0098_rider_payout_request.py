import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('app', '0097_rider_tips'),
    ]

    operations = [
        migrations.CreateModel(
            name='RiderPayoutRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('method', models.CharField(choices=[('bank', 'Bank transfer (IBAN)'), ('benefitpay', 'BenefitPay'), ('cash', 'Cash')], default='bank', max_length=12)),
                ('account_title', models.CharField(blank=True, default='', max_length=100)),
                ('account_no', models.CharField(blank=True, default='', max_length=50)),
                ('note', models.CharField(blank=True, default='', max_length=200)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('paid', 'Paid'), ('rejected', 'Rejected'), ('cancelled', 'Cancelled by rider')], db_index=True, default='pending', max_length=10)),
                ('reject_reason', models.CharField(blank=True, default='', max_length=200)),
                ('reference_no', models.CharField(blank=True, default='', max_length=100)),
                ('requested_at', models.DateTimeField(auto_now_add=True)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('rider', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='payout_requests', to='app.riderprofile')),
                ('settlement', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='payout_request', to='app.ridersettlement')),
            ],
            options={'ordering': ['-requested_at', '-id']},
        ),
        migrations.AddConstraint(
            model_name='riderpayoutrequest',
            constraint=models.UniqueConstraint(condition=models.Q(('status', 'pending')), fields=('rider',), name='one_pending_rider_payout_request'),
        ),
    ]
