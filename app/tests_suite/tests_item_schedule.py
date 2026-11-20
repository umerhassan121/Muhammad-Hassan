"""
Tests: item schedule (item sirf kuch ghanton / dinon ke liye available).

Run:  python manage.py test app.tests_suite.tests_item_schedule -v 2

Sirf hisaab ki jaanch (database ki zaroorat nahi). 2026-11-16 Monday hai.
Expected:
    schedule nahi                      -> hamesha available
    07:00-11:00                        -> 07:00 aur 11:00 available, 06:59 aur 11:01 nahi
    07:00-11:00, din Sat+Sun ('56')    -> Monday band, Saturday 08:00 available
    sirf din ('0', waqt nahi)          -> Monday poora din, Tuesday nahi
    raat 22:00-02:00, din Friday ('4') -> Fri 23:00 aur Sat 01:00 available; Sat 23:00 aur Fri 01:00 nahi
    clean_days: ['5','6'] -> '56'; sab 7 din -> ''; kharab -> ''
"""
from datetime import datetime, time

from django.test import SimpleTestCase

from app.customer import item_schedule as sched


class S:
    def __init__(self, f, t, d=''):
        self.avail_from, self.avail_to, self.days = f, t, d


def at(d, h, m=0):
    return datetime(2026, 11, d, h, m)


class AvailabilityTests(SimpleTestCase):
    def test_no_schedule(self):
        self.assertTrue(sched.is_available_at(None, at(16, 3)))

    def test_time_window(self):
        s = S(time(7), time(11))
        self.assertTrue(sched.is_available_at(s, at(16, 7, 0)))
        self.assertTrue(sched.is_available_at(s, at(16, 11, 0)))
        self.assertFalse(sched.is_available_at(s, at(16, 6, 59)))
        self.assertFalse(sched.is_available_at(s, at(16, 11, 1)))

    def test_days(self):
        weekend = S(time(7), time(11), '56')
        self.assertFalse(sched.is_available_at(weekend, at(16, 8)))
        self.assertTrue(sched.is_available_at(weekend, at(21, 8)))
        monday = S(None, None, '0')
        self.assertTrue(sched.is_available_at(monday, at(16, 23, 59)))
        self.assertFalse(sched.is_available_at(monday, at(17, 1)))

    def test_overnight(self):
        night = S(time(22), time(2), '4')
        self.assertTrue(sched.is_available_at(night, at(20, 23)))
        self.assertTrue(sched.is_available_at(night, at(21, 1)))
        self.assertFalse(sched.is_available_at(night, at(21, 23)))
        self.assertFalse(sched.is_available_at(night, at(20, 1)))


class HelperTests(SimpleTestCase):
    def test_clean_days(self):
        self.assertEqual(sched.clean_days(['5', '6']), '56')
        self.assertEqual(sched.clean_days(list('0123456')), '')
        self.assertEqual(sched.clean_days(['x', '9']), '')

    def test_describe(self):
        self.assertEqual(sched.describe(S(time(7), time(11))), '7:00 AM - 11:00 AM')
        self.assertEqual(sched.describe(S(time(7), time(11), '56')), '7:00 AM - 11:00 AM · Sat-Sun')
        self.assertEqual(sched.describe(None), '')

    def test_parse_time(self):
        self.assertEqual(sched.parse_time('07:30'), time(7, 30))
        self.assertIsNone(sched.parse_time(''))
        with self.assertRaises(ValueError):
            sched.parse_time('abc')
