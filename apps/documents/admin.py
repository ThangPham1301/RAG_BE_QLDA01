from django.contrib import admin
from .models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ['title', 'project', 'uploaded_by', 'index_status', 'uploaded_at']
    list_filter = ['index_status', 'file_type', 'uploaded_at', 'project']
    search_fields = ['title', 'project__name']
    readonly_fields = ['uploaded_at', 'updated_at', 'indexed_at']
