from documents.models import Document
from documents.notifications import get_latest_notifications


def navigation_context(request):
    if not request.user.is_authenticated:
        return {}

    documents = Document.objects.filter(
        uploaded_by=request.user
    ).order_by('-uploaded_at')
    recommended_document = documents.filter(summary__isnull=False).exclude(
        summary=''
    ).first() or documents.first()

    return {
        'nav_documents_count': documents.count(),
        'nav_recommended_document': recommended_document,
        'nav_latest_notifications': get_latest_notifications(request.user, 5),
    }
