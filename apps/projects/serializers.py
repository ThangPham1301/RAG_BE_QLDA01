from rest_framework import serializers
from .models import Project


class ProjectSerializer(serializers.ModelSerializer):
	owner_email = serializers.CharField(source='owner.email', read_only=True)
	documents_count = serializers.SerializerMethodField()
	chats_count = serializers.SerializerMethodField()

	class Meta:
		model = Project
		fields = [
			'id', 'name', 'description', 'owner', 'owner_email',
			'documents_count', 'chats_count', 'created_at', 'updated_at'
		]
		read_only_fields = ['id', 'owner', 'owner_email', 'created_at', 'updated_at']

	def get_documents_count(self, obj):
		from apps.documents.models import Document
		return Document.objects.filter(chat_session__project=obj, is_deleted=False).count()

	def get_chats_count(self, obj):
		return obj.chat_sessions.count()

	def create(self, validated_data):
		validated_data['owner'] = self.context['request'].user
		return super().create(validated_data)
