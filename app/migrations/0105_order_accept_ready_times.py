from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0104_rider_peak_hours'),
    ]

    operations = [
        migrations.AddField(
            model_name='saleorder',
            name='accepted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='saleorder',
            name='ready_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
