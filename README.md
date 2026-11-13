# TECHNOVA backend setup

For the complete local stack (MySQL, database import, demo accounts, frontend
and smoke tests) see [LOCAL_SETUP.md](LOCAL_SETUP.md).

## Database migrations

Apply only migrations whose schema changes are not already present. In
particular, `001_create_suppliers.sql` and `002_supplier_dashboard.sql` contain
non-idempotent DDL and should not be replayed blindly.

The configured MySQL database has already had `003_admin_dashboard.sql` and
`004_auth_sessions.sql` applied. They add the admin profile/report extensions
and the `auth_sessions` table.

## Create the first administrator

From the backend directory, run:

```powershell
python scripts\create_admin.py
```

The command prompts for the administrator name, email, and password. Password
input is hidden; the password is hashed before it is stored. The command only
works when no Admin account exists yet.

Sign in at `/login` with that account. Admin, cashier, supplier, and customer
roles are routed to their corresponding dashboards. Admin API routes require
an active Admin session.

## Demo data

`scripts/seed_demo.py` fills an empty database with a catalogue of sixteen
products across six categories plus one cashier, one customer and one supplier
account. It is idempotent and can be re-run safely:

```bash
python scripts/seed_demo.py
```

## Local smoke test

With the API on port 8000 and the frontend on port 3000:

```bash
./scripts/smoke_test.sh
```

## Cookie security

Sessions use expiring, revocable HttpOnly cookies. For local development,
`COOKIE_SECURE` defaults to `false`. Set `COOKIE_SECURE=true` when serving the
frontend and API over HTTPS, and configure `FRONTEND_ORIGIN` to the exact
frontend origin. Authenticated write requests also require the frontend's
`X-Requested-With: TECHNOVA` header.

Customer registration currently does not enforce email verification on the
backend. The frontend verification step is not an authorization boundary; add
a trusted server-side mail verification provider before relying on verified
email addresses.

## Password reset email

Password reset codes are generated and validated by the backend, expire after
10 minutes, and allow at most five attempts. For local development, the backend
also reads the EmailJS public configuration from `../frontend/.env.local` when
started from the backend directory.
For deployment, configure EmailJS in the backend environment:

```text
EMAILJS_SERVICE_ID=your-emailjs-service-id
EMAILJS_TEMPLATE_ID=your-emailjs-template-id
EMAILJS_PUBLIC_KEY=your-emailjs-public-key
```

The configured template should use `to_email` as its recipient and include
`to_name`, `name`, `verification_code`, and `expiry_minutes`.

Alternatively, configure SMTP in the backend environment:

```text
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=your-smtp-username
SMTP_PASSWORD=your-smtp-password
SMTP_FROM_EMAIL=no-reply@example.com
SMTP_USE_TLS=true
SMTP_USE_SSL=false
```

For implicit TLS providers, use their SSL port (usually 465), set
`SMTP_USE_SSL=true`, and set `SMTP_USE_TLS=false`. Apply
`migrations/005_password_reset_codes.sql` before using password reset.

## Tests

Run backend tests from the backend directory:

```powershell
python -m unittest discover -v
```
