from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from documents.views import document_study

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('accounts.urls')),
    path('study/<int:document_id>/', document_study, name='document_study'),
    path('documents/', include('documents.urls')),
]
if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )
