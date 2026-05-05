from django.contrib import admin
from .models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ['title', 'chat_session', 'uploaded_by', 'index_status', 'uploaded_at']
    list_filter = ['index_status', 'file_type', 'uploaded_at', 'chat_session']
    search_fields = ['title', 'chat_session__title', 'chat_session__project__name']
    readonly_fields = ['uploaded_at', 'updated_at', 'indexed_at']
