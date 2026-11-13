#!/usr/bin/env bash
# TECHNOVA end-to-end smoke test.
# Requires the backend on :8000 and the MySQL instance to be running.
#
#   ./scripts/smoke-test.sh
#
set -uo pipefail

API="${API:-http://127.0.0.1:8000}"
WEB="${WEB:-http://localhost:3000}"
JAR="$(mktemp)"
PASS=0
FAIL=0

cleanup() { rm -f "$JAR"; }
trap cleanup EXIT

ok()   { PASS=$((PASS + 1)); printf '  \033[32mPASS\033[0m  %s\n' "$1"; }
bad()  { FAIL=$((FAIL + 1)); printf '  \033[31mFAIL\033[0m  %s\n' "$1"; }

# check <name> <expected-code> <method> <url> [body]
check() {
  local name="$1" expected="$2" method="$3" url="$4" body="${5:-}"
  local args=(-s -o /dev/null -w '%{http_code}' -X "$method" -b "$JAR" -c "$JAR"
              -H 'X-Requested-With: TECHNOVA')
  if [ -n "$body" ]; then
    args+=(-H 'Content-Type: application/json' -d "$body")
  fi
  local code
  code="$(curl "${args[@]}" "$url")"
  if [ "$code" = "$expected" ]; then ok "$name (HTTP $code)"; else bad "$name (expected $expected, got $code)"; fi
}

login() {
  local email="$1" password="$2"
  curl -s -o /dev/null -b "$JAR" -c "$JAR" -X POST "$API/api/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"$email\",\"password\":\"$password\"}"
}

echo "== Health =="
check "API root"                  200 GET "$API/"
check "Database health"           200 GET "$API/api/health"

echo "== Public catalogue =="
check "Product list"              200 GET "$API/api/products"
check "Category list"             200 GET "$API/api/categories"

echo "== Admin session =="
login "admin@technova.lk" "Admin@12345"
check "Dashboard"                 200 GET "$API/api/admin/dashboard"
check "Users"                     200 GET "$API/api/users"
check "Customers"                 200 GET "$API/api/customers"
check "Orders"                    200 GET "$API/api/admin/orders"
check "Suppliers"                 200 GET "$API/api/admin/suppliers"
check "Purchase orders"           200 GET "$API/api/admin/purchase-orders"
check "Reports"                   200 GET "$API/api/admin/reports"
check "AI settings"               200 GET "$API/api/admin/ai/settings"
check "Inventory transactions"    200 GET "$API/api/admin/inventory/transactions"
check "POS sales"                 200 GET "$API/api/admin/pos/sales"

echo "== Admin write flow (POS sale) =="
check "Create POS sale"           201 POST "$API/api/admin/pos/sales" \
  '{"cashier_name":"Nimal Perera","items_count":2,"subtotal":12500.00,"payment_method":"Cash"}'

sale_id="$(curl -s -b "$JAR" "$API/api/admin/pos/sales" |
  grep -o '"id":[0-9]*' | head -1 | cut -d: -f2)"
if [ -n "${sale_id:-}" ]; then
  ok "POS sale is listed (id $sale_id)"
  check "Void POS sale"           200 POST "$API/api/admin/pos/sales/$sale_id/void"
else
  bad "POS sale is listed"
fi

echo "== CSRF protection =="
csrf_code="$(curl -s -o /dev/null -w '%{http_code}' -b "$JAR" -X POST \
  "$API/api/admin/pos/sales" -H 'Content-Type: application/json' \
  -d '{"cashier_name":"x","items_count":1,"subtotal":1,"payment_method":"Cash"}')"
if [ "$csrf_code" = "403" ]; then ok "Write without X-Requested-With is rejected"; else bad "Write without X-Requested-With is rejected (got $csrf_code)"; fi

echo "== Role separation =="
login "customer@technova.lk" "Technova@123"
check "Customer can read own orders" 200 GET "$API/api/orders"
admin_code="$(curl -s -o /dev/null -w '%{http_code}' -b "$JAR" "$API/api/admin/dashboard")"
if [ "$admin_code" = "403" ]; then ok "Customer blocked from admin dashboard"; else bad "Customer blocked from admin dashboard (got $admin_code)"; fi

echo "== Frontend pages =="
for path in / /login /register /cart /admin /cashier /customer /supplier; do
  code="$(curl -s -o /dev/null -w '%{http_code}' "$WEB$path")"
  if [ "$code" = "200" ]; then ok "Page $path"; else bad "Page $path (got $code)"; fi
done

echo
printf 'Result: %d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
