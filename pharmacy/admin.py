from django.contrib import admin

from .models import Medicine, Prescription, PrescriptionItem, StockMovement


@admin.register(Medicine)
class MedicineAdmin(admin.ModelAdmin):
    list_display = ('name', 'hospital', 'category', 'quantity', 'reorder_level', 'expiry_date', 'unit_price')
    list_filter = ('hospital', 'category')
    search_fields = ('name',)


class PrescriptionItemInline(admin.TabularInline):
    model = PrescriptionItem
    extra = 0


@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'doctor', 'status', 'created_at')
    list_filter = ('status',)
    inlines = [PrescriptionItemInline]


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ('medicine', 'change', 'reason', 'performed_by', 'created_at')
    list_filter = ('reason',)
