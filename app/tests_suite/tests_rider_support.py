from django.test import SimpleTestCase

from app.customer import rider_support as s


class SupportTextTests(SimpleTestCase):
    def test_clean_text_trims(self):
        self.assertEqual(s.clean_text('  hello  '), 'hello')

    def test_empty_rejected(self):
        for bad in ('', '   ', None):
            with self.assertRaises(s.SupportError):
                s.clean_text(bad)

    def test_too_long_rejected(self):
        with self.assertRaises(s.SupportError):
            s.clean_text('x' * (s.MAX_LEN + 1))
        self.assertEqual(len(s.clean_text('x' * s.MAX_LEN)), s.MAX_LEN)
