from django.contrib import admin

from .models import ChatDocumentAttachment, DocumentShare, InAppNotification, Team, TeamDocument, TeamInvitation, TeamMembership


admin.site.register(Team)
admin.site.register(TeamMembership)
admin.site.register(TeamInvitation)
admin.site.register(InAppNotification)
admin.site.register(TeamDocument)
admin.site.register(DocumentShare)
admin.site.register(ChatDocumentAttachment)
