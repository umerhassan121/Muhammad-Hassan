from django.db import migrations, models


class Migration(migrations.Migration):
    """Bari gari: driver ka jawab (pending / accepted)."""

    dependencies = [
        ('app', '0113_bigvehicle_driver'),
    ]

    operations = [
        migrations.AddField(
            model_name='saleorder', name='big_vehicle_driver_state',
            field=models.CharField(blank=True, default='', max_length=10)),
    ]
