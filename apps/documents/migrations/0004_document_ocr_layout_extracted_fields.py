from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0003_chat_session_documents_refactor'),
    ]

    operations = [
        migrations.AddField(
            model_name='document',
            name='ocr_layout',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='document',
            name='extracted_fields',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
