import os
from rest_framework import serializers
from .models import Document


class DocumentSerializer(serializers.ModelSerializer):
	chat_session_title = serializers.CharField(source='chat_session.title', read_only=True)
	project_id = serializers.IntegerField(source='chat_session.project_id', read_only=True)
	project_name = serializers.CharField(source='chat_session.project.name', read_only=True)
	uploaded_by_email = serializers.CharField(source='uploaded_by.email', read_only=True)
	file_url = serializers.SerializerMethodField()
	file_size = serializers.SerializerMethodField()
	access_source = serializers.SerializerMethodField()
	is_team_document = serializers.SerializerMethodField()
	is_shared_with_me = serializers.SerializerMethodField()
	can_share = serializers.SerializerMethodField()

	class Meta:
		model = Document
		fields = [
			'id', 'chat_session', 'chat_session_title', 'project_id', 'project_name', 'title', 'file', 'file_url',
			'file_size', 'access_source', 'is_team_document', 'is_shared_with_me', 'can_share',
			'file_type', 'extracted_text', 'summary', 'ocr_layout', 'extracted_fields', 'index_status',
			'indexed_chunks', 'index_error', 'indexed_at', 'uploaded_by',
			'uploaded_by_email', 'is_deleted', 'deleted_at', 'uploaded_at', 'updated_at'
		]
		read_only_fields = [
			'id', 'project_name', 'file_url', 'index_status', 'chat_session_title',
			'ocr_layout', 'extracted_fields', 'index_error', 'indexed_at', 'uploaded_by',
			'is_deleted', 'deleted_at', 'uploaded_at'
		]

	def get_file_url(self, obj):
		request = self.context.get('request')
		if not obj.file:
			return None
		url = obj.file.url
		if request is not None:
			return request.build_absolute_uri(url)
		return url

	def get_file_size(self, obj):
		try:
			return obj.file.size if obj.file else 0
		except Exception:
			return 0

	def _request_user(self):
		request = self.context.get('request')
		return getattr(request, 'user', None)

	def get_is_team_document(self, obj):
		try:
			return obj.team_links.exists()
		except Exception:
			return False

	def get_is_shared_with_me(self, obj):
		user = self._request_user()
		if not user or not user.is_authenticated:
			return False
		try:
			return obj.user_shares.filter(shared_with=user).exists() and obj.uploaded_by_id != user.id
		except Exception:
			return False

	def get_access_source(self, obj):
		chat_session_id = self.context.get('chat_session_id')
		if chat_session_id and obj.chat_session_id != int(chat_session_id):
			return 'team_attachment'
		if self.get_is_shared_with_me(obj):
			return 'shared_with_me'
		if self.get_is_team_document(obj):
			return 'team'
		return 'owned'

	def get_can_share(self, obj):
		user = self._request_user()
		if not user or not user.is_authenticated:
			return False
		if self.get_is_team_document(obj):
			return False
		return obj.uploaded_by_id == user.id or obj.chat_session.user_id == user.id or user.is_staff


class DocumentUploadSerializer(serializers.ModelSerializer):
	title = serializers.CharField(required=False, allow_blank=True)
	chat_session_id = serializers.IntegerField(required=True)

	class Meta:
		model = Document
		fields = ['chat_session_id', 'title', 'file']

	def validate_file(self, value):
		extension = os.path.splitext(value.name)[1].lower()
		allowed_extensions = {'.pdf', '.docx', '.txt', '.jpg', '.jpeg', '.png'}
		if extension not in allowed_extensions:
			raise serializers.ValidationError('Chỉ hỗ trợ file PDF, DOCX hoặc TXT.')
		return value

	def validate(self, attrs):
		file_obj = attrs.get('file')
		if not file_obj:
			raise serializers.ValidationError({'file': 'File là bắt buộc.'})

		chat_session_id = attrs.get('chat_session_id')
		from apps.chatbot.models import ChatSession
		request = self.context['request']
		chat_session = ChatSession.objects.filter(
			id=chat_session_id,
			user=request.user,
			is_deleted=False,
		).first()
		if not chat_session:
			raise serializers.ValidationError({'chat_session_id': 'Chat session không hợp lệ hoặc không thuộc user.'})
		attrs['chat_session'] = chat_session
		attrs.pop('chat_session_id', None)
		return attrs

	def create(self, validated_data):
		file_obj = validated_data['file']
		if not validated_data.get('title'):
			validated_data['title'] = os.path.splitext(file_obj.name)[0]

		file_ext = os.path.splitext(file_obj.name)[1].lower()
		if file_ext == '.pdf':
			validated_data['file_type'] = Document.FileType.PDF
		elif file_ext == '.docx':
			validated_data['file_type'] = Document.FileType.DOCX
		elif file_ext in ['.jpg', '.jpeg', '.png']:
			validated_data['file_type'] = Document.FileType.IMAGE
		else:
			validated_data['file_type'] = Document.FileType.TXT

		validated_data.setdefault('extracted_text', '')
		validated_data.setdefault('summary', '')
		validated_data.setdefault('index_status', Document.IndexStatus.PENDING)
		validated_data.setdefault('indexed_chunks', 0)
		validated_data.setdefault('index_error', '')
		validated_data['uploaded_by'] = self.context['request'].user
		return super().create(validated_data)
