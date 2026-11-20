from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0103_rider_sos'),
    ]

    operations = [
        migrations.AddField(
            model_name='deliveryinfo',
            name='peak_bonus',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Peak-hour extra jo order lete waqt tay hua (rider_fee mein shamil hota hai)', max_digits=10),
        ),
        migrations.CreateModel(
            name='RiderPeakWindow',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=60)),
                ('start_time', models.TimeField()),
                ('end_time', models.TimeField()),
                ('days', models.CharField(blank=True, default='', max_length=20)),
                ('extra_amount', models.DecimalField(decimal_places=2, max_digits=8)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name_plural': '\U0001F525 Peak hours',
                'ordering': ['start_time', 'id'],
            },
        ),
    ]
