from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Profile
from accounts.permissions import user_role
from hospitals.models import Department, Hospital
from opd import services as opd_services
from opd.models import Token
from pharmacy import services as pharmacy_services
from wards import services as ward_services
from wards.models import Admission, Bed

from .serializers import TokenCreateSerializer, TokenSerializer


class IsPatient(BasePermission):
    """Only logged-in users with the Patient role may book / view / cancel tokens."""

    def has_permission(self, request, view):
        return user_role(request.user) == Profile.Role.PATIENT


class CityHospitalsView(APIView):
    """GET /api/city/hospitals/ - public, aggregate numbers per hospital (feeds the City Dashboard)."""

    permission_classes = [AllowAny]

    def get(self, request):
        data = []
        for hospital in Hospital.objects.filter(is_active=True):
            depts = list(hospital.departments.filter(is_open=True))
            loads = [opd_services.department_load(d) for d in depts]
            data.append({
                'id': hospital.id,
                'name': hospital.name,
                'area': hospital.area,
                'beds': ward_services.bed_counts(hospital),
                'opd': {
                    'open_departments': len(depts),
                    'waiting_tokens': sum(load['waiting'] for load in loads),
                    'shortest_wait_minutes': min((load['estimated_wait_minutes'] for load in loads), default=None),
                },
                'pharmacy': {'low_stock_items': pharmacy_services.low_stock(hospital).count()},
            })
        return Response(data)


class HospitalDepartmentsView(APIView):
    """GET /api/hospitals/<id>/departments/ - public queue load per department."""

    permission_classes = [AllowAny]

    def get(self, request, pk):
        hospital = get_object_or_404(Hospital, pk=pk, is_active=True)
        data = [{'id': d.id, 'name': d.name, 'code': d.code, 'is_open': d.is_open,
                 **opd_services.department_load(d)} for d in hospital.departments.all()]
        return Response(data)


class HospitalBedsView(APIView):
    """GET /api/hospitals/<id>/beds/ - public bed availability, overall and per ward."""

    permission_classes = [AllowAny]

    def get(self, request, pk):
        hospital = get_object_or_404(Hospital, pk=pk, is_active=True)
        wards = []
        for ward in hospital.wards.all():
            beds = ward.beds.all()
            wards.append({
                'id': ward.id, 'name': ward.name, 'type': ward.ward_type,
                'total': beds.count(), 'available': beds.filter(status=Bed.Status.AVAILABLE).count(),
                'waiting': ward.admissions.filter(status=Admission.Status.WAITING).count(),
            })
        return Response({'hospital': hospital.name, **ward_services.bed_counts(hospital), 'wards': wards})


class TokenCreateView(APIView):
    """POST /api/tokens/ - a patient books a token for themselves."""

    permission_classes = [IsAuthenticated, IsPatient]

    def post(self, request):
        ser = TokenCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        department = get_object_or_404(Department, pk=ser.validated_data['department'])
        try:
            patient = opd_services.patient_for_user(
                request.user, ser.validated_data.get('age'), ser.validated_data.get('gender'))
            token = opd_services.book_token(patient, department)
        except opd_services.ProfileIncomplete as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except opd_services.QueueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(TokenSerializer(token).data, status=status.HTTP_201_CREATED)


def _own_token_or_404(request, pk):
    """Tokens of other patients are indistinguishable from missing ones (404, no existence leak)."""
    return get_object_or_404(Token.objects.select_related('department__hospital'), pk=pk,
                             patient__user=request.user)


class TokenDetailView(APIView):
    """GET /api/tokens/<id>/ - owner only."""

    permission_classes = [IsAuthenticated, IsPatient]

    def get(self, request, pk):
        return Response(TokenSerializer(_own_token_or_404(request, pk)).data)


class TokenCancelView(APIView):
    """POST /api/tokens/<id>/cancel/ - owner only, WAITING tokens only."""

    permission_classes = [IsAuthenticated, IsPatient]

    def post(self, request, pk):
        token = _own_token_or_404(request, pk)
        try:
            token = opd_services.cancel(token)
        except opd_services.QueueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(TokenSerializer(token).data)
