from django.db import models
from django.conf import settings


class Document(models.Model):
	"""Document with file upload and indexing support."""
	
	class FileType(models.TextChoices):
		PDF = 'pdf', 'PDF'
		DOCX = 'docx', 'DOCX'
		TXT = 'txt', 'TXT'
		IMAGE = 'image', 'Image'
		OTHER = 'other', 'Other'

	class IndexStatus(models.TextChoices):
		PENDING = 'pending', 'Pending'
		INDEXING = 'indexing', 'Indexing'
		INDEXED = 'indexed', 'Indexed'
		FAILED = 'failed', 'Failed'

	chat_session = models.ForeignKey('chatbot.ChatSession', on_delete=models.CASCADE, related_name='documents')
	uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='uploaded_documents')
	uploaded_chat_session = models.ForeignKey(
		'chatbot.ChatSession',
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name='uploaded_documents',
	)
	
	title = models.CharField(max_length=255)
	file = models.FileField(upload_to='documents/%Y/%m/')
	file_type = models.CharField(max_length=20, choices=FileType.choices)
	extracted_text = models.TextField(blank=True)
	summary = models.TextField(blank=True)
	
	index_status = models.CharField(max_length=20, choices=IndexStatus.choices, default=IndexStatus.PENDING)
	indexed_chunks = models.PositiveIntegerField(default=0)
	index_error = models.TextField(blank=True)
	indexed_at = models.DateTimeField(null=True, blank=True)
	
	# Soft delete support
	deleted_at = models.DateTimeField(null=True, blank=True)
	is_deleted = models.BooleanField(default=False)
	
	uploaded_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['-uploaded_at']
		indexes = [
			models.Index(fields=['chat_session', '-uploaded_at']),
			models.Index(fields=['uploaded_by', '-uploaded_at']),
			models.Index(fields=['index_status']),
		]

	def __str__(self):
		return f"{self.title} ({self.chat_session.title})"
