from django.contrib import admin

from .models import Patient, Token


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'age', 'gender', 'user')
    search_fields = ('name', 'phone')


@admin.register(Token)
class TokenAdmin(admin.ModelAdmin):
    list_display = ('label', 'patient', 'department', 'date', 'status', 'is_priority')
    list_filter = ('status', 'is_priority', 'date', 'department__hospital')
    search_fields = ('patient__name', 'patient__phone')
