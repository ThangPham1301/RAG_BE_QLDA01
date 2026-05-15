import os
from rest_framework import serializers
from .models import Document


class DocumentSerializer(serializers.ModelSerializer):
	chat_session_title = serializers.CharField(source='chat_session.title', read_only=True)
	project_id = serializers.IntegerField(source='chat_session.project_id', read_only=True)
	project_name = serializers.CharField(source='chat_session.project.name', read_only=True)
	uploaded_by_email = serializers.CharField(source='uploaded_by.email', read_only=True)
	file_url = serializers.SerializerMethodField()

	class Meta:
		model = Document
		fields = [
			'id', 'chat_session', 'chat_session_title', 'project_id', 'project_name', 'title', 'file', 'file_url',
			'file_type', 'extracted_text', 'summary', 'index_status',
			'indexed_chunks', 'index_error', 'indexed_at', 'uploaded_by',
			'uploaded_by_email', 'is_deleted', 'deleted_at', 'uploaded_at', 'updated_at'
		]
		read_only_fields = [
			'id', 'project_name', 'file_url', 'index_status', 'chat_session_title',
			'index_error', 'indexed_at', 'uploaded_by', 'is_deleted', 'deleted_at', 'uploaded_at'
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
	chat_session_id = serializers.IntegerField(required=True)

	class Meta:
		model = Document
		fields = ['chat_session_id', 'title', 'file']

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
		else:
			validated_data['file_type'] = Document.FileType.TXT

		validated_data.setdefault('extracted_text', '')
		validated_data.setdefault('summary', '')
		validated_data.setdefault('index_status', Document.IndexStatus.PENDING)
		validated_data.setdefault('indexed_chunks', 0)
		validated_data.setdefault('index_error', '')
		validated_data['uploaded_by'] = self.context['request'].user
		return super().create(validated_data)
