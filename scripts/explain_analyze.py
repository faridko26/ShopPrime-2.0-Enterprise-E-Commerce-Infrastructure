"""
explain_analyze.py  -  ShopPrime EXPLAIN ANALYZE Performance Report
Drops indexes, captures BEFORE plan, recreates indexes, captures AFTER plan,
then computes speedup for each query.

Run:
    python scripts/explain_analyze.py
    python scripts/explain_analyze.py > scripts/explain_analyze_output.txt
"""

import os
import re
from datetime import datetime, timezone
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

# ── Queries to benchmark ─────────────────────────────────────────────────────

QUERIES = [
    {
        "name": "All orders for a specific customer",
        "sql": """
            SELECT o.Order_ID, o.Order_Date, o.Total_Amount, o.Order_Status
            FROM Orders o
            WHERE o.Customer_ID = (SELECT Customer_ID FROM Customers LIMIT 1)
            ORDER BY o.Order_Date DESC;
        """,
    },
    {
        "name": "Order details with items and product names",
        "sql": """
            SELECT o.Order_ID, oi.Quantity, oi.Price_At_Purchase,
                   p.Product_Name, p.Product_Color
            FROM Orders o
            JOIN Order_Items oi ON oi.Order_ID = o.Order_ID
            JOIN Products p ON p.Product_ID = oi.Product_ID
            WHERE o.Order_ID = (SELECT Order_ID FROM Orders ORDER BY Order_ID LIMIT 1);
        """,
    },
    {
        "name": "Top 10 products by total revenue",
        "sql": """
            SELECT p.Product_ID, p.Product_Name,
                   SUM(oi.Quantity * oi.Price_At_Purchase) AS total_revenue
            FROM Products p
            JOIN Order_Items oi ON oi.Product_ID = p.Product_ID
            GROUP BY p.Product_ID, p.Product_Name
            ORDER BY total_revenue DESC
            LIMIT 10;
        """,
    },
    {
        "name": "Monthly revenue by vendor (raw aggregation vs materialized view)",
        "sql": """
            SELECT p.Supplier_ID,
                   TO_CHAR(o.Order_Date, 'YYYY-MM') AS month,
                   SUM(oi.Quantity * oi.Price_At_Purchase) AS revenue
            FROM Products p
            JOIN Order_Items oi ON oi.Product_ID = p.Product_ID
            JOIN Orders o      ON o.Order_ID    = oi.Order_ID
            WHERE o.Order_Status NOT IN ('cancelled')
            GROUP BY p.Supplier_ID, TO_CHAR(o.Order_Date, 'YYYY-MM')
            ORDER BY p.Supplier_ID, month;
        """,
    },
    {
        "name": "Top 5 customers by order count",
        "sql": """
            SELECT c.Customer_ID, c.First_Name, c.Last_Name,
                   COUNT(o.Order_ID) AS order_count
            FROM Customers c
            JOIN Orders o ON o.Customer_ID = c.Customer_ID
            GROUP BY c.Customer_ID, c.First_Name, c.Last_Name
            ORDER BY order_count DESC
            LIMIT 5;
        """,
    },
    {
        "name": "Products with low stock (under 20 units)",
        "sql": """
            SELECT Product_ID, Product_Name, Stock_Quantity, Price
            FROM Products
            WHERE Stock_Quantity < 20
            ORDER BY Stock_Quantity ASC;
        """,
    },
]

# ── Indexes to drop/recreate ─────────────────────────────────────────────────

DROP_INDEXES = [
    "idx_orders_customer_id",
    "idx_orders_status",
    "idx_orders_date",
    "idx_order_items_order_id",
    "idx_order_items_product_id",
    "idx_products_supplier_id",
    "idx_products_category_id",
    "idx_products_stock",
    "idx_addresses_customer_id",
    "idx_payment_customer_id",
    "idx_audit_log_changed_at",
    "idx_audit_log_table_name",
    "idx_categories_parent",
]

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_orders_customer_id    ON Orders (Customer_ID)",
    "CREATE INDEX IF NOT EXISTS idx_orders_status         ON Orders (Order_Status)",
    "CREATE INDEX IF NOT EXISTS idx_orders_date           ON Orders (Order_Date DESC)",
    "CREATE INDEX IF NOT EXISTS idx_order_items_order_id  ON Order_Items (Order_ID)",
    "CREATE INDEX IF NOT EXISTS idx_order_items_product_id ON Order_Items (Product_ID)",
    "CREATE INDEX IF NOT EXISTS idx_products_supplier_id  ON Products (Supplier_ID)",
    "CREATE INDEX IF NOT EXISTS idx_products_category_id  ON Products (Category_ID)",
    "CREATE INDEX IF NOT EXISTS idx_products_stock        ON Products (Stock_Quantity) WHERE Stock_Quantity < 10",
    "CREATE INDEX IF NOT EXISTS idx_addresses_customer_id ON Addresses (Customer_ID)",
    "CREATE INDEX IF NOT EXISTS idx_payment_customer_id   ON Payment_Methods (Customer_ID)",
    "CREATE INDEX IF NOT EXISTS idx_audit_log_changed_at  ON Audit_Log (Changed_At DESC)",
    "CREATE INDEX IF NOT EXISTS idx_audit_log_table_name  ON Audit_Log (Table_Name)",
    "CREATE INDEX IF NOT EXISTS idx_categories_parent     ON Categories (Parent_Category_ID)",
]

# ── Helpers ──────────────────────────────────────────────────────────────────

def extract_exec_time(plan_lines: list[str]) -> float | None:
    """Pull the Execution Time value (ms) from an EXPLAIN ANALYZE output."""
    for line in plan_lines:
        m = re.search(r'Execution Time:\s+([\d.]+)\s+ms', line)
        if m:
            return float(m.group(1))
    return None


def run_explain(cur, sql: str) -> list[str]:
    cur.execute(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) {sql}")
    return [row[0] for row in cur.fetchall()]


def drop_indexes(cur):
    for idx in DROP_INDEXES:
        cur.execute(f"DROP INDEX IF EXISTS {idx}")


def create_indexes(cur):
    for stmt in CREATE_INDEXES:
        cur.execute(stmt)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur  = conn.cursor()

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    sep_heavy = "=" * 80
    sep_light = "-" * 80

    lines = []
    lines.append(sep_heavy)
    lines.append("EXPLAIN ANALYZE Performance Report - ShopPrime")
    lines.append(f"Generated: {now}")
    lines.append(sep_heavy)

    # ── Drop all custom indexes (BEFORE state) ────────────────────────────
    print("Dropping indexes for BEFORE measurements...")
    drop_indexes(cur)

    results = []
    for q in QUERIES:
        before_plan = run_explain(cur, q["sql"])
        results.append({"q": q, "before": before_plan})

    # ── Recreate all indexes (AFTER state) ───────────────────────────────
    print("Recreating indexes for AFTER measurements...")
    create_indexes(cur)

    for entry in results:
        after_plan = run_explain(cur, entry["q"]["sql"])
        entry["after"] = after_plan

    cur.close()
    conn.close()

    # ── Format report ─────────────────────────────────────────────────────
    for entry in results:
        q           = entry["q"]
        before_plan = entry["before"]
        after_plan  = entry["after"]
        before_ms   = extract_exec_time(before_plan)
        after_ms    = extract_exec_time(after_plan)

        lines.append("")
        lines.append(sep_light)
        lines.append(f"QUERY: {q['name']}")
        lines.append(sep_light)
        lines.append("")
        lines.append("SQL:")

        # Indent the SQL block
        for sql_line in q["sql"].strip().splitlines():
            lines.append(sql_line)

        lines.append("")
        lines.append(">>> BEFORE INDEXES <<<")
        lines.extend(before_plan)

        lines.append("")
        lines.append(">>> AFTER INDEXES <<<")
        lines.extend(after_plan)

        if before_ms is not None and after_ms is not None:
            if after_ms > 0:
                speedup = before_ms / after_ms
            else:
                speedup = float("inf")
            lines.append("")
            lines.append(
                f"PERFORMANCE: {before_ms:.3f}ms -> {after_ms:.3f}ms ({speedup:.1f}x speedup)"
            )

    lines.append("")
    lines.append(sep_heavy)
    lines.append("END OF REPORT")
    lines.append(sep_heavy)

    report = "\n".join(lines)
    print(report)


if __name__ == "__main__":
    main()
