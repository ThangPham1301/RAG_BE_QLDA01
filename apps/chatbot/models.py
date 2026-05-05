from django.db import models
from django.utils import timezone
from django.conf import settings
from apps.projects.models import Project
from apps.documents.models import Document


class ChatSession(models.Model):
	"""Chat session - user-owned conversation history."""
	
	project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='chat_sessions')
	user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='chat_sessions')
	
	title = models.CharField(max_length=255, default='New Chat')
	description = models.TextField(blank=True)
	
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)
	last_message_at = models.DateTimeField(null=True, blank=True)
	
	is_archived = models.BooleanField(default=False)
	token_count = models.PositiveIntegerField(default=0)
	
	# Soft delete support
	deleted_at = models.DateTimeField(null=True, blank=True)
	is_deleted = models.BooleanField(default=False)
	
	class Meta:
		ordering = ['-updated_at']
		indexes = [
			models.Index(fields=['project', 'user', '-updated_at']),
			models.Index(fields=['user', '-created_at']),
			models.Index(fields=['is_archived']),
		]
	
	def __str__(self):
		return f'{self.title} ({self.user.email})'
	
	def update_title_from_first_message(self):
		"""Auto-generate title from first user message."""
		if self.title == 'New Chat':
			first_msg = self.messages.filter(role=ChatMessage.Role.USER).first()
			if first_msg:
				self.title = first_msg.content[:50]
				if len(first_msg.content) > 50:
					self.title += '...'
				self.save(update_fields=['title'])


class ChatMessage(models.Model):
	"""Chat message with sources and LLM metadata."""

	class Role(models.TextChoices):
		USER = 'user', 'User'
		ASSISTANT = 'assistant', 'Assistant'
		SYSTEM = 'system', 'System'
	
	chat_session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages')
	
	# Message content
	role = models.CharField(max_length=20, choices=Role.choices, default=Role.USER)
	content = models.TextField()
	
	# Sources & citations
	sources = models.JSONField(default=list, blank=True)
	
	# LLM metadata
	model_name = models.CharField(max_length=100, default='qwen3-vl:4b', blank=True)
	temperature = models.FloatField(default=0.0, blank=True)
	tokens_used = models.PositiveIntegerField(default=0, blank=True)
	
	# Additional metadata
	metadata = models.JSONField(default=dict, blank=True)
	
	# Timestamps
	created_at = models.DateTimeField(auto_now_add=True)
	
	class Meta:
		ordering = ['created_at']
		indexes = [
			models.Index(fields=['chat_session', 'created_at']),
			models.Index(fields=['created_at']),
		]
	
	def __str__(self):
		preview = self.content[:50]
		if len(self.content) > 50:
			preview += '...'
		return f'[{self.role}] {preview}'


class MessageContext(models.Model):
	"""Retrieved chunk trace per message for RAG observability."""

	message = models.ForeignKey(ChatMessage, on_delete=models.CASCADE, related_name='contexts')
	document = models.ForeignKey(Document, on_delete=models.CASCADE)
	chunk_id = models.CharField(max_length=255)
	score = models.FloatField(null=True, blank=True)
	content_preview = models.TextField(blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ['created_at']
		indexes = [
			models.Index(fields=['message', 'created_at']),
			models.Index(fields=['document']),
			models.Index(fields=['chunk_id']),
		]

	def __str__(self):
		return f'ctx(message={self.message_id}, document={self.document_id}, chunk={self.chunk_id})'


class ChatFeedback(models.Model):
	"""User feedback on chat messages."""
	
	FEEDBACK_CHOICES = [
		('helpful', 'Helpful'),
		('unhelpful', 'Unhelpful'),
		('incorrect', 'Incorrect'),
		('incomplete', 'Incomplete'),
	]
	
	message = models.OneToOneField(ChatMessage, on_delete=models.CASCADE, related_name='feedback')
	user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='message_feedbacks')
	
	feedback_type = models.CharField(max_length=20, choices=FEEDBACK_CHOICES)
	comment = models.TextField(blank=True)
	
	created_at = models.DateTimeField(auto_now_add=True)
	
	class Meta:
		ordering = ['-created_at']
	
	def __str__(self):
		return f"Feedback: {self.feedback_type} - {self.message.id}"
