import mimetypes
from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.clickjacking import xframe_options_sameorigin

from .ai import ask_document_ai, generate_summary
from .forms import DocumentForm
from .models import Document
from .utils import TextExtractionError, extract_text_from_document, extract_text_from_pdf

@login_required(login_url='login')
def upload_document(request):
    if request.method == 'POST':
        form = DocumentForm(
            request.POST,
            request.FILES
        )

        if form.is_valid():
            document = form.save(
                commit=False
            )
            document.uploaded_by = request.user
            document.save()

            if document.file.name.endswith('.pdf'):
                text = extract_text_from_pdf(document.file.path)
                document.summary = generate_summary(text)
                document.ai_processed = True
                document.save()

            return redirect('dashboard')

    else:
        form = DocumentForm()

    return render(
        request,
        'documents/upload.html',
        {'form': form}
    )


@login_required(login_url='login')
def document_chat(request, document_id):
    document = get_object_or_404(
        Document,
        id=document_id,
        uploaded_by=request.user
    )

    answer = None
    question = ""

    if request.method == "POST":
        question = request.POST.get("question")

        text = extract_text_from_pdf(document.file.path)

        answer = ask_document_ai(text, question)

    return render(
        request,
        "documents/chat.html",
        {
            "document": document,
            "question": question,
            "answer": answer,
        }
    )


@login_required(login_url='login')
def document_detail(request, document_id):
    document = get_object_or_404(
        Document,
        id=document_id,
        uploaded_by=request.user
    )

    file_extension = document.file.name.rsplit('.', 1)[-1].lower()
    show_extracted_text = request.GET.get('view') == 'text'
    extracted_text = ''
    error_message = None

    if show_extracted_text:
        try:
            extracted_text = extract_text_from_document(document.file.path)
            if not extracted_text:
                error_message = 'Nuk u gjet tekst ne kete dokument.'
        except TextExtractionError as exc:
            error_message = str(exc)

    return render(
        request,
        'documents/detail.html',
        {
            'document': document,
            'file_extension': file_extension,
            'is_pdf': file_extension == 'pdf',
            'show_extracted_text': show_extracted_text,
            'extracted_text': extracted_text,
            'error_message': error_message
        }
    )


@login_required(login_url='login')
@xframe_options_sameorigin
def document_file(request, document_id):
    document = get_object_or_404(
        Document,
        id=document_id,
        uploaded_by=request.user
    )
    file_path = document.file.path
    if not Path(file_path).exists():
        raise Http404('Dokumenti nuk u gjet.')

    content_type, _ = mimetypes.guess_type(file_path)

    return FileResponse(
        open(file_path, 'rb'),
        as_attachment=False,
        filename=Path(document.file.name).name,
        content_type=content_type or 'application/octet-stream'
    )
