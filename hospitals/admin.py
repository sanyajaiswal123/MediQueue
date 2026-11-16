from django.contrib import admin

from .models import Department, Doctor, Hospital


@admin.register(Hospital)
class HospitalAdmin(admin.ModelAdmin):
    list_display = ('name', 'area', 'phone', 'is_active')
    list_filter = ('is_active', 'area')
    search_fields = ('name', 'area')


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'hospital', 'avg_minutes', 'daily_limit', 'is_open')
    list_filter = ('hospital', 'is_open')
    search_fields = ('name', 'code')


@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'department', 'room')
    list_filter = ('department__hospital',)
    search_fields = ('user__username', 'user__first_name', 'user__last_name')
