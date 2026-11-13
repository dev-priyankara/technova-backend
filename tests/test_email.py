import json
import unittest
from unittest.mock import MagicMock, patch

from app.core.config import settings
from app.services.email import send_password_reset_email


class PasswordResetEmailTests(unittest.TestCase):
    def test_password_reset_uses_configured_emailjs_template(self):
        response = MagicMock()
        response.status = 200
        response.__enter__.return_value = response

        with (
            patch.object(settings, "SMTP_HOST", None),
            patch.object(settings, "SMTP_FROM_EMAIL", None),
            patch.object(settings, "EMAILJS_SERVICE_ID", "service"),
            patch.object(settings, "EMAILJS_TEMPLATE_ID", "template"),
            patch.object(settings, "EMAILJS_PUBLIC_KEY", "public-key"),
            patch("app.services.email.urlopen", return_value=response) as urlopen,
        ):
            send_password_reset_email("customer@example.com", "Customer", "123456")

        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.emailjs.com/api/v1.0/email/send")
        payload = json.loads(request.data)
        self.assertEqual(payload["service_id"], "service")
        self.assertEqual(payload["template_id"], "template")
        self.assertEqual(payload["user_id"], "public-key")
        self.assertEqual(
            payload["template_params"],
            {
                "to_email": "customer@example.com",
                "to_name": "Customer",
                "name": "Customer",
                "verification_code": "123456",
                "expiry_minutes": "10",
            },
        )
