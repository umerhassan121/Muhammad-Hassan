import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0106_vendor_support'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProductSchedule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('avail_from', models.TimeField(blank=True, help_text='Khali = poora din', null=True)),
                ('avail_to', models.TimeField(blank=True, help_text='Khali = poora din. Raat paar (22:00 -> 02:00) bhi chalta hai', null=True)),
                ('days', models.CharField(blank=True, default='', help_text='Din ke number (0=Mon ... 6=Sun), jaise 56 = Sat+Sun. Khali = har din', max_length=7)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('product', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='schedule', to='app.product')),
            ],
            options={
                'verbose_name': 'Item Schedule',
                'verbose_name_plural': '3.7 Item Schedules',
            },
        ),
    ]
