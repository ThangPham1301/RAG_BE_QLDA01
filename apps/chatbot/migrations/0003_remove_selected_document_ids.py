from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('chatbot', '0002_messagecontext'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='chatsession',
            name='selected_document_ids',
        ),
    ]
