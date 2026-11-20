import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Bari gari bhi rider ki tarah: RiderProfile.rider_kind (bike / big_vehicle), gari ka number,
    aur order par chuna hua gari wala driver."""

    dependencies = [
        ('app', '0112_bigvehicleoffer'),
    ]

    operations = [
        migrations.AddField(
            model_name='riderprofile', name='rider_kind',
            field=models.CharField(choices=[('bike', 'Bike rider'), ('big_vehicle', 'Bari gari (Suzuki / Pickup / Loader...)')],
                                   db_index=True, default='bike', max_length=12)),
        migrations.AddField(
            model_name='riderprofile', name='vehicle_no',
            field=models.CharField(blank=True, default='', help_text='Gari ka number (bari gari ke liye)', max_length=30)),
        migrations.AlterField(
            model_name='riderprofile', name='vehicle',
            field=models.CharField(blank=True, default='', max_length=50,
                                   help_text='Bike ke liye optional; bari gari ke liye gari ki qism (Suzuki, Pickup, Loader...)')),
        migrations.AddField(
            model_name='saleorder', name='vehicle_no',
            field=models.CharField(blank=True, max_length=30, null=True, verbose_name='Big vehicle number')),
        migrations.AddField(
            model_name='saleorder', name='big_vehicle_driver',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name='big_vehicle_jobs', to='app.riderprofile')),
        migrations.AddField(
            model_name='bigvehicleoffer', name='driver',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name='+', to='app.riderprofile')),
    ]
