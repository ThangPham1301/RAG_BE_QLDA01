from rest_framework import serializers
from .models import ChatMessage, ChatSession, ChatFeedback, MessageContext, ConversationEvaluation


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
	evaluation_id = serializers.SerializerMethodField()
	project_name = serializers.CharField(source='project.name', read_only=True)
	user_email = serializers.CharField(source='user.email', read_only=True)

	class Meta:
		model = ChatSession
		fields = [
			'id', 'project', 'project_name', 'user', 'user_email',
			'title', 'description', 'message_count', 'documents_count', 'evaluation_id', 'created_at',
			'updated_at', 'last_message_at', 'is_archived'
		]
		read_only_fields = ['id', 'user', 'user_email', 'message_count', 'documents_count', 'evaluation_id', 'created_at', 'updated_at', 'project_name']

	def get_message_count(self, obj):
		return obj.messages.count()

	def get_documents_count(self, obj):
		try:
			from apps.teams.permissions import accessible_documents_for_session
			return accessible_documents_for_session(obj).count()
		except Exception:
			return obj.documents.filter(is_deleted=False).count()

	def get_evaluation_id(self, obj):
		try:
			return obj.evaluation.id
		except ConversationEvaluation.DoesNotExist:
			return None

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
		try:
			from apps.teams.permissions import accessible_documents_for_session
			documents = accessible_documents_for_session(obj).order_by('-uploaded_at')
		except Exception:
			documents = obj.documents.filter(is_deleted=False).order_by('-uploaded_at')
		context = dict(self.context)
		context['chat_session_id'] = obj.id
		return DocumentSerializer(documents, many=True, context=context).data


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


class ConversationEvaluationSerializer(serializers.ModelSerializer):
	user_email = serializers.CharField(source='user.email', read_only=True)
	chat_title = serializers.CharField(source='chat_session.title', read_only=True)
	project_name = serializers.CharField(source='chat_session.project.name', read_only=True)
	pinned_by_email = serializers.CharField(source='pinned_by.email', read_only=True)

	class Meta:
		model = ConversationEvaluation
		fields = [
			'id', 'chat_session', 'chat_title', 'project_name', 'user', 'user_email',
			'rating', 'accuracy_rating', 'usefulness_rating', 'grounding_rating', 'comment',
			'is_pinned', 'pinned_at', 'pinned_by', 'pinned_by_email', 'created_at', 'updated_at',
		]
		read_only_fields = [
			'id', 'user', 'user_email', 'chat_title', 'project_name',
			'is_pinned', 'pinned_at', 'pinned_by', 'pinned_by_email', 'created_at', 'updated_at',
		]

	def validate(self, attrs):
		request = self.context['request']
		chat_session = attrs.get('chat_session') or getattr(self.instance, 'chat_session', None)
		if not chat_session:
			raise serializers.ValidationError({'chat_session': 'This field is required.'})
		if chat_session.user_id != request.user.id:
			raise serializers.ValidationError({'chat_session': 'Chat session is not available.'})
		return attrs
