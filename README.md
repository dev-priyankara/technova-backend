# TECHNOVA backend setup

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

## Tests

Run backend tests from the backend directory:

```powershell
python -m unittest discover -v
```
