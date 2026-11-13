import json
import unittest
from unittest.mock import MagicMock, patch

from app.core.config import settings
from app.services.email import EmailConfigurationError, send_password_reset_email


def _without_provider():
    return (
        patch.object(settings, "SMTP_HOST", None),
        patch.object(settings, "SMTP_FROM_EMAIL", None),
        patch.object(settings, "EMAILJS_SERVICE_ID", None),
        patch.object(settings, "EMAILJS_TEMPLATE_ID", None),
        patch.object(settings, "EMAILJS_PUBLIC_KEY", None),
    )


class PasswordResetEmailTests(unittest.TestCase):
    def test_missing_provider_raises_when_dev_mode_is_off(self):
        smtp_host, smtp_from, service, template, public_key = _without_provider()
        with (
            smtp_host,
            smtp_from,
            service,
            template,
            public_key,
            patch.object(settings, "EMAIL_DEV_MODE", False),
        ):
            with self.assertRaises(EmailConfigurationError):
                send_password_reset_email("customer@example.com", "Customer", "123456")

    def test_missing_provider_logs_the_code_when_dev_mode_is_on(self):
        smtp_host, smtp_from, service, template, public_key = _without_provider()
        with (
            smtp_host,
            smtp_from,
            service,
            template,
            public_key,
            patch.object(settings, "EMAIL_DEV_MODE", True),
            self.assertLogs("app.services.email", level="WARNING") as logs,
            patch("app.services.email.urlopen") as urlopen,
        ):
            send_password_reset_email("customer@example.com", "Customer", "123456")

        urlopen.assert_not_called()
        output = "\n".join(logs.output)
        self.assertIn("EMAIL_DEV_MODE", output)
        self.assertIn("123456", output)
        self.assertIn("customer@example.com", output)

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
