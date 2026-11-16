from django.contrib import admin

from .models import Admission, Bed, Ward


class BedInline(admin.TabularInline):
    model = Bed
    extra = 0


@admin.register(Ward)
class WardAdmin(admin.ModelAdmin):
    list_display = ('name', 'hospital', 'ward_type')
    list_filter = ('hospital', 'ward_type')
    inlines = [BedInline]


@admin.register(Bed)
class BedAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'status')
    list_filter = ('status', 'ward__hospital')


@admin.register(Admission)
class AdmissionAdmin(admin.ModelAdmin):
    list_display = ('patient', 'ward', 'bed', 'status', 'priority', 'requested_at')
    list_filter = ('status', 'priority', 'ward__hospital')
