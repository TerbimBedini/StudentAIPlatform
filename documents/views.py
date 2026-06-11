from django.shortcuts import render, redirect
from .forms import DocumentForm


def upload_document(request):
    if not request.user.is_authenticated:
        return redirect('login')

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
            return redirect(
                'dashboard'
            )

    else:
        form = DocumentForm()

    return render(
        request,
        'documents/upload.html',
        {'form': form}
    )
