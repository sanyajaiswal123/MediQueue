"""Serializers. Public ones expose aggregate numbers only, never patient data."""
from rest_framework import serializers

from opd import services as opd_services
from opd.models import Patient, Token
from pharmacy.models import Prescription


class TokenCreateSerializer(serializers.Serializer):
    """Input for POST /api/tokens/. Priority cannot be self-assigned by patients."""

    department = serializers.IntegerField()
    age = serializers.IntegerField(required=False, min_value=0, max_value=120)
    gender = serializers.ChoiceField(choices=Patient.Gender.choices, required=False)


class TokenSerializer(serializers.ModelSerializer):
    """A patient's own token, including live position and wait estimate."""

    label = serializers.CharField(read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True)
    hospital_name = serializers.CharField(source='department.hospital.name', read_only=True)
    people_ahead = serializers.SerializerMethodField()
    estimated_wait_minutes = serializers.SerializerMethodField()
    room = serializers.CharField(source='doctor.room', default=None, read_only=True)
    department_code = serializers.CharField(source='department.code', read_only=True)
    hospital_area = serializers.CharField(source='department.hospital.area', read_only=True)
    prescription = serializers.SerializerMethodField()

    class Meta:
        model = Token
        fields = ('id', 'label', 'number', 'date', 'status', 'is_priority', 'department', 'department_name',
                  'hospital_name', 'people_ahead', 'estimated_wait_minutes', 'room', 'call_count', 'created_at',
                  'department_code', 'hospital_area', 'prescription')
        read_only_fields = fields

    def get_prescription(self, token):
        """Status of the latest prescription (PENDING / DISPENSED) or None. Never the medicines themselves."""
        latest = token.prescriptions.exclude(status=Prescription.Status.CANCELLED).first()
        return latest.status if latest else None

    def get_people_ahead(self, token):
        return opd_services.people_ahead(token)

    def get_estimated_wait_minutes(self, token):
        return opd_services.estimated_wait_minutes(token)
