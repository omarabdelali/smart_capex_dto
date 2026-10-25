from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0003_add_kpi_features')]

    operations = [
        migrations.CreateModel(
            name='FeatureSyncJob',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('mode', models.CharField(choices=[('features', 'Features only'), ('full', 'Full sync')], max_length=16)),
                ('status', models.CharField(choices=[('queued', 'Queued'), ('running', 'Running'), ('succeeded', 'Succeeded'), ('failed', 'Failed')], db_index=True, default='queued', max_length=16)),
                ('stage', models.CharField(default='queued', max_length=32)),
                ('processed', models.PositiveIntegerField(default=0)),
                ('total', models.PositiveIntegerField(default=0)),
                ('current_site', models.CharField(blank=True, default='', max_length=100)),
                ('result', models.JSONField(blank=True, null=True)),
                ('error', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={'db_table': 'feature_sync_jobs', 'ordering': ['-created_at']},
        ),
    ]
