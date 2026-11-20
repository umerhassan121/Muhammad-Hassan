from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0110_saleorder_delivery_address'),
    ]

    operations = [
        migrations.AddField(model_name='saleorder', name='big_vehicle_state',
            field=models.CharField(blank=True, default='', max_length=10,
                help_text="'' = aam order | proposed = customer ki manzoori baqi | approved | declined")),
        migrations.AddField(model_name='saleorder', name='big_vehicle_type',
            field=models.CharField(blank=True, default='', max_length=60)),
        migrations.AddField(model_name='saleorder', name='big_vehicle_fee',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=10)),
        migrations.AddField(model_name='saleorder', name='big_vehicle_note',
            field=models.CharField(blank=True, default='', max_length=200)),
        migrations.AddField(model_name='saleorder', name='big_vehicle_driver_phone',
            field=models.CharField(blank=True, default='', max_length=20)),
        migrations.AddField(model_name='saleorder', name='big_vehicle_proposed_at',
            field=models.DateTimeField(blank=True, null=True)),
    ]
