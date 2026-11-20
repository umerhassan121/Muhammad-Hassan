from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0094_hybrid_delivery'),
    ]

    operations = [
        migrations.AddField(
            model_name='notification',
            name='priority',
            field=models.CharField(choices=[('critical', 'Critical'), ('high', 'High'), ('normal', 'Normal'), ('low', 'Low')], db_index=True, default='normal', max_length=10),
        ),
        migrations.AddField(
            model_name='notification',
            name='is_pinned',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='notification',
            name='is_archived',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='notification',
            name='snoozed_until',
            field=models.DateTimeField(blank=True, help_text='Is waqt tak bell se chhupi rahegi', null=True),
        ),
        migrations.AddField(
            model_name='notification',
            name='group_key',
            field=models.CharField(blank=True, db_index=True, default='', max_length=80),
        ),
        migrations.AddField(
            model_name='notification',
            name='group_count',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name='notification',
            name='event',
            field=models.CharField(blank=True, default='', max_length=40),
        ),
        migrations.AlterField(
            model_name='notification',
            name='category',
            field=models.CharField(choices=[('all', 'All'), ('orders', 'Orders'), ('vendors', 'Vendors'), ('riders', 'Riders'), ('disputes', 'Disputes'), ('payments', 'Payments'), ('sales', 'Sales'), ('installments', 'Installments'), ('stock', 'Stock'), ('security', 'Security'), ('marketing', 'Marketing'), ('system', 'System')], default='all', max_length=20),
        ),
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(fields=['is_archived'], name='notif_is_archived_idx'),
        ),
    ]
