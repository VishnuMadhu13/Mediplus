from django.test import TestCase


class PublicPagesSmokeTest(TestCase):
    """Minimal smoke tests so the CI 'Unit Tests' stage exercises the app."""

    def test_public_pages_render(self):
        for path in ("/index", "/home", "/services", "/contact", "/user_register"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_admin_listing_pages_render(self):
        for path in ("/userview", "/doctor_view", "/adminapp_view"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_logout_redirects(self):
        self.assertEqual(self.client.get("/logout").status_code, 302)
