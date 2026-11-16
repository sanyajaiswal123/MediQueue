from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from hospitals.models import Department, Hospital
from opd import services
from opd.models import Patient, Token

S = Token.Status


def make_patient(n=1):
    return Patient.objects.create(name=f'P{n}', phone=f'90000000{n:02d}', age=30, gender='M')


class OpdBase(TestCase):
    def setUp(self):
        self.h = Hospital.objects.create(name='H', area='A')
        self.dept = Department.objects.create(hospital=self.h, name='Cardiology', code='CAR',
                                              avg_minutes=10, daily_limit=3)


class BookingTests(OpdBase):
    def test_numbers_are_sequential_per_department_per_day(self):
        t1 = services.book_token(make_patient(1), self.dept)
        t2 = services.book_token(make_patient(2), self.dept)
        self.assertEqual((t1.number, t2.number), (1, 2))
        self.assertEqual(t2.label, 'CAR-002')
        tomorrow = timezone.localdate() + timedelta(days=1)
        self.assertEqual(services.book_token(make_patient(1), self.dept, date=tomorrow).number, 1)

    def test_quota_exceeded(self):
        for i in range(3):
            services.book_token(make_patient(i), self.dept)
        with self.assertRaises(services.QuotaExceeded):
            services.book_token(make_patient(9), self.dept)

    def test_cancelled_tokens_free_quota(self):
        toks = [services.book_token(make_patient(i), self.dept) for i in range(3)]
        services.cancel(toks[0])
        self.assertEqual(services.book_token(make_patient(9), self.dept).number, 4)

    def test_closed_department(self):
        self.dept.is_open = False
        self.dept.save()
        with self.assertRaises(services.DepartmentClosed):
            services.book_token(make_patient(), self.dept)

    def test_duplicate_active_token_blocked_but_allowed_after_completion(self):
        p = make_patient()
        t = services.book_token(p, self.dept)
        with self.assertRaises(services.DuplicateToken):
            services.book_token(p, self.dept)
        services.call_next(self.dept)
        services.start_consultation(t)
        services.complete(t)
        self.assertEqual(services.book_token(p, self.dept).number, 2)


class QueueTests(OpdBase):
    def test_priority_jumps_ahead_of_normal(self):
        a = services.book_token(make_patient(1), self.dept)
        b = services.book_token(make_patient(2), self.dept, is_priority=True)
        self.assertEqual(list(services.waiting_queue(self.dept)), [b, a])
        self.assertEqual(services.call_next(self.dept), b)
        self.assertEqual(services.call_next(self.dept), a)

    def test_priority_keeps_number_order_among_themselves(self):
        a = services.book_token(make_patient(1), self.dept, is_priority=True)
        b = services.book_token(make_patient(2), self.dept, is_priority=True)
        self.assertEqual(list(services.waiting_queue(self.dept)), [a, b])

    def test_wait_estimate(self):
        a = services.book_token(make_patient(1), self.dept)
        b = services.book_token(make_patient(2), self.dept)
        c = services.book_token(make_patient(3), self.dept)
        self.assertEqual([services.estimated_wait_minutes(t) for t in (a, b, c)], [0, 10, 20])
        services.call_next(self.dept)  # a is now being served -> still ahead of everyone
        for t in (b, c):
            t.refresh_from_db()
        self.assertEqual([services.estimated_wait_minutes(t) for t in (b, c)], [10, 20])

    def test_call_next_on_empty_queue(self):
        self.assertIsNone(services.call_next(self.dept))


class LifecycleTests(OpdBase):
    def test_no_show_only_after_called(self):
        t = services.book_token(make_patient(), self.dept)
        with self.assertRaises(services.InvalidTransition):
            services.mark_no_show(t)
        services.call_next(self.dept)
        self.assertEqual(services.mark_no_show(t).status, S.NO_SHOW)
        # a no-show is never called again
        self.assertIsNone(services.call_next(self.dept))

    def test_late_cancel_rejected(self):
        t = services.book_token(make_patient(), self.dept)
        services.call_next(self.dept)
        with self.assertRaises(services.InvalidTransition):
            services.cancel(t)
        t.refresh_from_db()
        self.assertEqual(t.status, S.CALLED)

    def test_full_flow_and_call_count(self):
        t = services.book_token(make_patient(), self.dept)
        called = services.call_next(self.dept)
        self.assertEqual((called.status, called.call_count), (S.CALLED, 1))
        self.assertEqual(services.start_consultation(t).status, S.IN_CONSULT)
        self.assertEqual(services.complete(t).status, S.COMPLETED)
        with self.assertRaises(services.InvalidTransition):
            services.complete(t)
