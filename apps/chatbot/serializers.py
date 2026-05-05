from rest_framework import serializers
from .models import ChatMessage, ChatSession, ChatFeedback, MessageContext


class MessageContextSerializer(serializers.ModelSerializer):
	document_id = serializers.IntegerField(source='document.id', read_only=True)
	preview = serializers.CharField(source='content_preview', read_only=True)

	class Meta:
		model = MessageContext
		fields = ['id', 'document_id', 'chunk_id', 'score', 'preview', 'created_at']
		read_only_fields = fields


class ChatMessageSerializer(serializers.ModelSerializer):
	contexts = MessageContextSerializer(many=True, read_only=True)

	class Meta:
		model = ChatMessage
		fields = [
			'id', 'chat_session', 'role', 'content', 'sources',
			'model_name', 'temperature', 'tokens_used', 'metadata', 'created_at', 'contexts'
		]
		read_only_fields = ['id', 'created_at', 'sources', 'tokens_used', 'model_name', 'temperature', 'metadata']


class ChatSessionSerializer(serializers.ModelSerializer):
	message_count = serializers.SerializerMethodField()
	documents_count = serializers.SerializerMethodField()
	project_name = serializers.CharField(source='project.name', read_only=True)
	user_email = serializers.CharField(source='user.email', read_only=True)

	class Meta:
		model = ChatSession
		fields = [
			'id', 'project', 'project_name', 'user', 'user_email',
			'title', 'description', 'message_count', 'documents_count', 'created_at',
			'updated_at', 'last_message_at', 'is_archived'
		]
		read_only_fields = ['id', 'user', 'user_email', 'message_count', 'documents_count', 'created_at', 'updated_at', 'project_name']

	def get_message_count(self, obj):
		return obj.messages.count()

	def get_documents_count(self, obj):
		return obj.documents.filter(is_deleted=False).count()

	def create(self, validated_data):
		validated_data['user'] = self.context['request'].user
		return super().create(validated_data)


class ChatSessionDetailSerializer(ChatSessionSerializer):
	messages = ChatMessageSerializer(many=True, read_only=True)
	documents = serializers.SerializerMethodField()

	class Meta(ChatSessionSerializer.Meta):
		fields = ChatSessionSerializer.Meta.fields + ['messages', 'documents']

	def get_documents(self, obj):
		from apps.documents.serializers import DocumentSerializer
		return DocumentSerializer(obj.documents.filter(is_deleted=False).order_by('-uploaded_at'), many=True, context=self.context).data


class ChatMessageCreateSerializer(serializers.Serializer):
	content = serializers.CharField(max_length=10000)

	def validate_content(self, value):
		if not value or len(value.strip()) == 0:
			raise serializers.ValidationError("Content không được để trống.")
		return value


class ChatFeedbackSerializer(serializers.ModelSerializer):
	user_email = serializers.CharField(source='user.email', read_only=True)

	class Meta:
		model = ChatFeedback
		fields = ['id', 'message', 'user', 'user_email', 'feedback_type', 'comment', 'created_at']
		read_only_fields = ['id', 'user', 'user_email', 'created_at']

	def create(self, validated_data):
		validated_data['user'] = self.context['request'].user
		return super().create(validated_data)
