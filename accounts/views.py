from django.http import HttpResponse

def home(request):
    return HttpResponse("Student AI Platform")