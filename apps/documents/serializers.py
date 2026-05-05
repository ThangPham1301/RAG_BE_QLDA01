import os
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from .models import Document


class DocumentSerializer(serializers.ModelSerializer):
	chat_session_title = serializers.CharField(source='chat_session.title', read_only=True)
	uploaded_chat_session_title = serializers.CharField(source='chat_session.title', read_only=True)
	project_id = serializers.IntegerField(source='chat_session.project_id', read_only=True)
	project_name = serializers.CharField(source='chat_session.project.name', read_only=True)
	uploaded_by_email = serializers.CharField(source='uploaded_by.email', read_only=True)
	uploaded_chat_session_title = serializers.CharField(source='uploaded_chat_session.title', read_only=True)
	file_url = serializers.SerializerMethodField()

	class Meta:
		model = Document
		fields = [
			'id', 'chat_session', 'chat_session_title', 'uploaded_chat_session_title', 'project_id', 'project_name', 'title', 'file', 'file_url',
			'file_type', 'extracted_text', 'summary', 'index_status',
			'indexed_chunks', 'index_error', 'indexed_at', 'uploaded_by',
			'uploaded_chat_session', 'uploaded_chat_session_title',
			'uploaded_by_email', 'is_deleted', 'deleted_at', 'uploaded_at', 'updated_at'
		]
		read_only_fields = [

    'id',
    'project_id',
    'project_name',
    'file_url',
    'index_status',
    'indexed_chunks',
    'chat_session_title',
    'uploaded_chat_session',
    'uploaded_chat_session_title',
    'index_error',
    'indexed_at',
    'uploaded_by',
    'uploaded_by_email',
    'is_deleted',
    'deleted_at',
    'uploaded_at',
    'updated_at'
]

	def get_file_url(self, obj):
		request = self.context.get('request')
		if not obj.file:
			return None
		url = obj.file.url
		if request is not None:
			return request.build_absolute_uri(url)
		return url


class DocumentUploadSerializer(serializers.ModelSerializer):
	title = serializers.CharField(required=False, allow_blank=True)
	uploaded_chat_session = serializers.IntegerField(required=False, allow_null=True)

	class Meta:
		model = Document
<<<<<<< HEAD
		fields = ['project', 'title', 'file', 'uploaded_chat_session']
=======
		fields = ['chat_session', 'title', 'file']
>>>>>>> 5f5f0ac (fix chat structure)

	def validate_file(self, value):
		extension = os.path.splitext(value.name)[1].lower()
		allowed_extensions = {'.pdf', '.docx', '.txt'}
		if extension not in allowed_extensions:
			raise serializers.ValidationError('Chỉ hỗ trợ file PDF, DOCX hoặc TXT.')
		return value

	def validate(self, attrs):
		file_obj = attrs.get('file')
		if not file_obj:
			raise serializers.ValidationError({'file': 'File là bắt buộc.'})

<<<<<<< HEAD
		chat_session_id = attrs.get('uploaded_chat_session')
		if chat_session_id is not None:
			from apps.chatbot.models import ChatSession
			request = self.context['request']
			project = attrs.get('project')
			chat_session = ChatSession.objects.filter(
				id=chat_session_id,
				user=request.user,
				project=project,
				is_deleted=False,
			).first()
			if not chat_session:
				raise serializers.ValidationError({'uploaded_chat_session': 'Chat session không hợp lệ cho project hiện tại.'})
			attrs['uploaded_chat_session'] = chat_session
=======
		chat_session = attrs.get('chat_session')
		if chat_session is None:
			raise serializers.ValidationError({'chat_session': 'chat_session là bắt buộc.'})

		request = self.context['request']
		if chat_session.user_id != request.user.id or chat_session.is_deleted:
			raise serializers.ValidationError({'chat_session': 'Chat session không hợp lệ.'})
>>>>>>> 5f5f0ac (fix chat structure)
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
		else:
			validated_data['file_type'] = Document.FileType.TXT

		validated_data.setdefault('extracted_text', '')
		validated_data.setdefault('summary', '')
		validated_data.setdefault('index_status', Document.IndexStatus.PENDING)
		validated_data.setdefault('indexed_chunks', 0)
		validated_data.setdefault('index_error', '')
		validated_data['uploaded_by'] = self.context['request'].user
		return super().create(validated_data)
