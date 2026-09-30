from django.contrib import admin

from .models import Attachment, Category, Comment, ServiceRequest

admin.site.register(Category)
admin.site.register(Comment)
admin.site.register(Attachment)


@admin.register(ServiceRequest)
class ServiceRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "citizen", "category", "priority", "status", "officer")
    list_filter = ("status", "priority", "category")
