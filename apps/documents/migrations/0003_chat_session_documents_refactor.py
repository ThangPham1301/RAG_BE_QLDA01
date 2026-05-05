from django.db import migrations, models
import django.db.models.deletion


def delete_orphan_documents(apps, schema_editor):
    Document = apps.get_model('documents', 'Document')
    Document.objects.filter(uploaded_chat_session__isnull=True).delete()


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ('chatbot', '0003_remove_selected_document_ids'),
        ('documents', '0002_document_uploaded_chat_session'),
    ]

    operations = [
        migrations.RunPython(delete_orphan_documents, migrations.RunPython.noop),
        migrations.RenameField(
            model_name='document',
            old_name='uploaded_chat_session',
            new_name='chat_session',
        ),
        migrations.RemoveIndex(
            model_name='document',
            name='documents_d_project_215c6e_idx',
        ),
        migrations.RemoveField(
            model_name='document',
            name='project',
        ),
        migrations.AlterField(
            model_name='document',
            name='chat_session',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='documents', to='chatbot.chatsession'),
        ),
        migrations.AddIndex(
            model_name='document',
            index=models.Index(fields=['chat_session', '-uploaded_at'], name='documents_d_chat_se_idx'),
        ),
    ]
