import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


def backfill_offers(apps, schema_editor):
    """Pehle se maujood bari gari wale orders ka maujooda kiraya history mein daal do."""
    SaleOrder = apps.get_model('app', 'SaleOrder')
    Offer = apps.get_model('app', 'BigVehicleOffer')
    for o in SaleOrder.objects.exclude(big_vehicle_state='').iterator():
        Offer.objects.create(
            order=o, vehicle_type=o.big_vehicle_type or '-', fee=o.big_vehicle_fee,
            note=o.big_vehicle_note or '',
            outcome=o.big_vehicle_state if o.big_vehicle_state in ('proposed', 'approved', 'declined') else 'proposed',
            proposed_at=o.big_vehicle_proposed_at or django.utils.timezone.now())


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('app', '0111_saleorder_big_vehicle'),
    ]

    operations = [
        migrations.CreateModel(
            name='BigVehicleOffer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('vehicle_type', models.CharField(max_length=60)),
                ('fee', models.DecimalField(decimal_places=2, max_digits=10)),
                ('note', models.CharField(blank=True, default='', max_length=200)),
                ('outcome', models.CharField(choices=[('proposed', 'Waiting for the customer'), ('approved', 'Approved by the customer'), ('declined', 'Declined by the customer'), ('expired', 'Expired (no response)'), ('superseded', 'Replaced by a new fare')], default='proposed', max_length=12)),
                ('proposed_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('responded_at', models.DateTimeField(blank=True, null=True)),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='big_vehicle_offers', to='app.saleorder')),
                ('proposed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name_plural': '5.0.2 Big Vehicle Offers',
                'ordering': ['-proposed_at', '-id'],
                'indexes': [models.Index(fields=['order', 'outcome'], name='bigveh_order_outcome_idx')],
            },
        ),
        migrations.RunPython(backfill_offers, migrations.RunPython.noop),
    ]
