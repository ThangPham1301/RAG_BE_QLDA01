from django.db.models import Q

from apps.documents.models import Document
from .models import ChatDocumentAttachment, DocumentShare, TeamDocument, TeamMembership


def user_is_team_member(user, team_id):
    if not user or not user.is_authenticated:
        return False
    return TeamMembership.objects.filter(team_id=team_id, user=user).exists()


def user_can_access_document(user, document):
    if not user or not user.is_authenticated or not document or document.is_deleted:
        return False
    if user.is_staff:
        return True
    if document.chat_session.user_id == user.id or document.uploaded_by_id == user.id:
        return True
    if TeamDocument.objects.filter(document=document, team__memberships__user=user).exists():
        return True
    return DocumentShare.objects.filter(document=document, shared_with=user).exists()


def accessible_documents_for_user(user):
    if user.is_staff:
        return Document.objects.filter(is_deleted=False)
    return Document.objects.filter(
        Q(chat_session__user=user)
        | Q(uploaded_by=user)
        | Q(team_links__team__memberships__user=user)
        | Q(user_shares__shared_with=user),
        is_deleted=False,
    ).distinct()


def accessible_documents_for_session(session):
    attached_ids = ChatDocumentAttachment.objects.filter(chat_session=session).values_list('document_id', flat=True)
    return Document.objects.filter(
        Q(chat_session=session) | Q(id__in=attached_ids),
        is_deleted=False,
    ).distinct()
