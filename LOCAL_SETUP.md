# TECHNOVA — Local Development Setup

End-to-end instructions for running the TECHNOVA Computers POS and Inventory
Management System on a single machine.

| Layer    | Technology        | Address                 |
| -------- | ----------------- | ----------------------- |
| Frontend | Next.js + React   | http://localhost:3000   |
| Backend  | FastAPI (Python)  | http://127.0.0.1:8000   |
| Database | MySQL             | 127.0.0.1:3307          |

The frontend lives in a separate repository:
<https://github.com/dev-priyankara/technova-frontend>

## 1. Prerequisites

- Python 3.11 or newer
- Node.js 20 or newer
- MySQL 8 or newer (`mysql` and `mysqld` on `PATH`)

## 2. Database

The schema is shipped as `technova_db.sql`. If you already run a MySQL server
on port 3307, create the database and import:

```bash
mysql -u root -h 127.0.0.1 -P 3307 -e "CREATE DATABASE technova_db CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;"
mysql -u root -h 127.0.0.1 -P 3307 technova_db < technova_db.sql
```

If you do not have a server there, start an isolated instance that keeps its
data inside the project directory:

```bash
mkdir -p .devdata
mysqld --initialize-insecure --datadir="$PWD/.devdata/mysql"
mysqld --datadir="$PWD/.devdata/mysql" --port=3307 \
       --socket="$PWD/.devdata/mysql.sock" --mysqlx=OFF &
```

Apply the migrations that are not part of the dump:

```bash
for f in migrations/003_admin_dashboard.sql \
         migrations/004_auth_sessions.sql \
         migrations/005_password_reset_codes.sql; do
  mysql -u root -h 127.0.0.1 -P 3307 technova_db < "$f"
done
```

`001_create_suppliers.sql` and `002_supplier_dashboard.sql` are already
reflected in the dump's schema and must not be replayed.

## 3. Backend

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env      # then edit if your credentials differ
.venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

Check it is alive:

```bash
curl http://127.0.0.1:8000/api/health
```

Interactive API docs: <http://127.0.0.1:8000/docs>

### Environment variables

| Name             | Default                 | Purpose                          |
| ---------------- | ----------------------- | -------------------------------- |
| `DB_HOST`        | `127.0.0.1`             | MySQL host                       |
| `DB_PORT`        | `3307`                  | MySQL port                       |
| `DB_USER`        | `root`                  | MySQL user                       |
| `DB_PASSWORD`    | *(empty)*               | MySQL password                   |
| `DB_NAME`        | *(required)*            | Database name, `technova_db`     |
| `FRONTEND_ORIGIN`| `http://localhost:3000` | CORS origin and cookie audience  |
| `COOKIE_SECURE`  | `false`                 | Set `true` behind HTTPS          |

Password reset additionally needs either the `EMAILJS_*` variables or the
`SMTP_*` variables. Without them, reset requests return a configuration error.

## 4. Users

Create the first administrator (only works while no Admin exists):

```bash
.venv/bin/python scripts/create_admin.py
```

Load the demo catalogue, cashier, customer and supplier accounts:

```bash
.venv/bin/python scripts/seed_demo.py
```

| Role     | Email                  | Password        |
| -------- | ---------------------- | --------------- |
| Admin    | `admin@technova.lk`    | `Admin@12345`   |
| Cashier  | `cashier@technova.lk`  | `Technova@123`  |
| Customer | `customer@technova.lk` | `Technova@123`  |
| Supplier | `supplier@technova.lk` | `Technova@123`  |

Change these before any shared or public deployment.

## 5. Frontend

```bash
git clone https://github.com/dev-priyankara/technova-frontend.git frontend
cd frontend
npm install
npm run dev
```

Create `frontend/.env.local` when the API is not on the default address:

```text
NEXT_PUBLIC_API_URL=http://localhost:8000/api
```

Email verification and password reset use EmailJS in the browser:

```text
NEXT_PUBLIC_EMAILJS_SERVICE_ID=...
NEXT_PUBLIC_EMAILJS_TEMPLATE_ID=...
NEXT_PUBLIC_EMAILJS_PUBLIC_KEY=...
```

Open <http://localhost:3000>. Each role is routed to its own dashboard after
sign-in.

## 6. Verification

Automated backend tests (SQLite, no MySQL needed):

```bash
cd backend
.venv/bin/python -m unittest discover -v
```

Full stack smoke test (requires both servers running):

```bash
cd backend
./scripts/smoke_test.sh
```

The smoke test covers health, the public catalogue, every admin listing, a POS
sale being created and voided, CSRF rejection, role separation, and that all
eight frontend routes return `200`.

Production build check for the frontend:

```bash
cd frontend
npm run build
```

## 7. Troubleshooting

- **`Can't connect to MySQL server`** — confirm the server is listening:
  `lsof -nP -iTCP:3307 -sTCP:LISTEN`.
- **`Authentication required` on every API call** — the session cookie is
  `HttpOnly` and bound to `FRONTEND_ORIGIN`; sign in through the frontend, and
  make sure the API and UI use the same host name (`localhost` vs `127.0.0.1`).
- **`CSRF validation failed`** — every non-GET request needs the
  `X-Requested-With: TECHNOVA` header. The frontend client already sends it.
- **Catalogue is empty** — run `scripts/seed_demo.py`, then check
  `GET /api/products`.
