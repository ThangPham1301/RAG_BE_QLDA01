from django.contrib import admin
from .models import ChatSession, ChatMessage, ChatFeedback, ConversationEvaluation


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ['title', 'user', 'project', 'created_at', 'is_archived']
    list_filter = ['is_archived', 'created_at', 'project']
    search_fields = ['title', 'user__email', 'project__name']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ['id', 'chat_session', 'role', 'created_at']
    list_filter = ['role', 'created_at', 'model_name']
    search_fields = ['content', 'chat_session__title']
    readonly_fields = ['created_at']


@admin.register(ChatFeedback)
class ChatFeedbackAdmin(admin.ModelAdmin):
    list_display = ['message', 'user', 'feedback_type', 'created_at']
    list_filter = ['feedback_type', 'created_at']
    search_fields = ['comment', 'user__email']
    readonly_fields = ['created_at']


@admin.register(ConversationEvaluation)
class ConversationEvaluationAdmin(admin.ModelAdmin):
    list_display = ['chat_session', 'user', 'rating', 'is_pinned', 'updated_at']
    list_filter = ['rating', 'is_pinned', 'created_at', 'updated_at']
    search_fields = ['comment', 'user__email', 'chat_session__title', 'chat_session__project__name']
    readonly_fields = ['created_at', 'updated_at', 'pinned_at']
