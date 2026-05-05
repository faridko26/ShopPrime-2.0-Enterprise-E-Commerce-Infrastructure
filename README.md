# ShopPrime — Setup & Execution Guide

## Prerequisites

- Python 3.11+
- A Neon PostgreSQL database (or any PostgreSQL 15+ instance)
- `pip` to install dependencies

---

## Step 1 — Install Dependencies

```bash
pip install -r requirements.txt
```

Installs: `flask`, `psycopg2-binary`, `python-dotenv`, `faker`

---

## Step 2 — Configure Environment

Create a `.env` file in the project root (already present if you cloned this repo):

```
DATABASE_URL=postgresql://<user>:<password>@<host>/<db>?sslmode=require&channel_binding=require
```

Replace the placeholder with your actual Neon connection string.

---

## Step 3 — Apply Migrations (Run Once)

Migrations must be applied **in order**. The apply script handles this automatically.

```bash
python scripts/apply_migrations.py
```

This runs the following files sequentially:

| File | What it creates |
|------|----------------|
| `migrations/V1__schema.sql` | All 9 tables with constraints |
| `migrations/V2__rbac_triggers_procedures.sql` | Roles, audit trigger, `place_order` stored procedure |
| `migrations/V3__indexes_materialized_view.sql` | 13 indexes + `Vendor_Monthly_Rollup` materialized view |
| `migrations/V4__grader_readonly_role.sql` | Read-only `grader` role for verification |

**Expected output:** `Done. Applied 4 migration(s).`

---

## Step 4 — Seed the Database

Populates the database with realistic synthetic data.

```bash
python scripts/seed_data.py
```

What gets inserted:

| Table | Rows |
|-------|------|
| Suppliers | 10 |
| Categories | 20 |
| Products | 1,000 |
| Customers | 500 |
| Addresses | ~750 |
| Payment_Methods | 500 |
| Orders | 10,000 |
| Order_Items | ~30,000 |

Also refreshes the `Vendor_Monthly_Rollup` materialized view at the end.

**Expected time:** ~2-3 minutes (network-dependent with Neon).

---

## Step 5 — Run EXPLAIN ANALYZE (Performance Benchmark)

Drops all indexes, records query plans, recreates indexes, records plans again, and prints a before/after speedup report.

```bash
python scripts/explain_analyze.py
```

To save the output:

```bash
python scripts/explain_analyze.py > scripts/explain_analyze_output.txt
```

**What it benchmarks:**

1. All orders for a specific customer
2. Order details with items and product names
3. Top 10 products by total revenue
4. Monthly revenue by vendor
5. Top 5 customers by order count
6. Products with low stock (under 20 units)

**Example result:** Customer order history went from 24.6ms → 0.2ms (118.5x speedup).

---

## Step 6 — Run Concurrency Test (Flash Sale)

Simulates 50 concurrent users trying to buy the same item with only 10 units in stock.

```bash
python scripts/concurrency_test.py
```

To save the output:

```bash
python scripts/concurrency_test.py > scripts/concurrency_test_output.txt
```

**Expected result:**
- 10 successful purchases
- 40 rejected with "Insufficient Stock"
- `[PASS]` inventory integrity verified (stock goes from 10 → 0, never negative)

---

## Step 7 — Start the Flask API (Optional)

```bash
python -m flask --app api/main.py run
```

The API starts on `http://127.0.0.1:5000`.

### Key Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/customers/<id>` | Get customer by ID |
| POST | `/customers/` | Create customer |
| GET | `/customers/<id>/orders` | Customer order history |
| GET | `/products/` | List products (filterable) |
| GET | `/products/vendor-rollup` | Materialized view report |
| POST | `/orders/` | Place order (calls stored procedure) |
| PATCH | `/orders/<id>/status` | Update order status |

---

## File Reference

```
Project-Final/
├── .env                          # Database connection string
├── requirements.txt              # Python dependencies
├── migrations/
│   ├── V1__schema.sql            # Tables & constraints
│   ├── V2__rbac_triggers_procedures.sql  # Roles, triggers, procedures
│   ├── V3__indexes_materialized_view.sql # Indexes & materialized view
│   └── V4__grader_readonly_role.sql      # Read-only grader role
├── scripts/
│   ├── apply_migrations.py       # Runs all migrations in order
│   ├── seed_data.py              # Seeds synthetic data
│   ├── explain_analyze.py        # Before/after index benchmark
│   ├── explain_analyze_output.txt  # Saved benchmark output
│   ├── concurrency_test.py       # 50-thread flash sale simulation
│   └── concurrency_test_output.txt # Saved concurrency output
├── api/
│   ├── main.py                   # Flask app factory
│   ├── database.py               # Connection pool
│   └── routes/
│       ├── customers.py
│       ├── products.py
│       └── orders.py
└── SUBMISSION.md                 # Grading guide & ER diagram
```

---

## Execution Order Summary

```
1. pip install -r requirements.txt
2. python scripts/apply_migrations.py
3. python scripts/seed_data.py
4. python scripts/explain_analyze.py > scripts/explain_analyze_output.txt
5. python scripts/concurrency_test.py > scripts/concurrency_test_output.txt
6. python -m flask --app api/main.py run   (optional, for API testing)
```

Steps 4 and 5 are independent of each other and can be run in either order after seeding.
