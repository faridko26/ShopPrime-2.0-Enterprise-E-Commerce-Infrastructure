"""
COMP640 Group-6
concurrency_test.py — ShopPrime Flash Sale Concurrency Demo
Phase 3: 50 concurrent users attempt to buy the same limited-stock item.

The place_order stored procedure uses SELECT ... FOR UPDATE (row-level locking),
so only as many users succeed as there is stock available. All others receive
"Insufficient Stock" — no negative inventory, no phantom orders.

Setup before running:
    1. Pick a product_id with limited stock (e.g. 10 units).
    2. Set FLASH_PRODUCT_ID and FLASH_STOCK below.
    3. Ensure at least 50 customers with valid addresses & payment methods exist
       (seed_data.py creates 500).

Run:
    python scripts/concurrency_test.py
"""

import os
import json
import random
import threading
import time
from datetime import datetime, timezone
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

load_dotenv()

DATABASE_URL   = os.getenv("DATABASE_URL")
NUM_THREADS    = 50          # concurrent "users"
FLASH_STOCK    = 10          # units we'll set for the flash product


# ── Helpers ──────────────────────────────────────────────────

def connect():
    return psycopg2.connect(DATABASE_URL)


def pick_flash_product(cur) -> int:
    """Choose a real product and set its stock to FLASH_STOCK."""
    cur.execute("SELECT Product_ID FROM Products ORDER BY Product_ID LIMIT 1")
    row = cur.fetchone()
    pid = row["product_id"]
    cur.execute(
        "UPDATE Products SET Stock_Quantity = %s WHERE Product_ID = %s",
        (FLASH_STOCK, pid),
    )
    return pid


def get_customers(cur, n=50):
    """Return n customers that each have at least one address and payment method."""
    cur.execute(
        """
        SELECT DISTINCT c.Customer_ID,
               a.Address_ID,
               pm.Payment_ID
        FROM Customers c
        JOIN Addresses       a  ON a.Customer_ID  = c.Customer_ID
        JOIN Payment_Methods pm ON pm.Customer_ID = c.Customer_ID
        LIMIT %s
        """,
        (n,),
    )
    return cur.fetchall()


# ── Worker ────────────────────────────────────────────────────

results_lock = threading.Lock()
results      = {"success": 0, "insufficient_stock": 0, "other_error": 0, "details": []}


def attempt_purchase(customer_id, address_id, payment_id, product_id, thread_num):
    """Each thread opens its own connection and calls place_order."""
    conn = connect()
    conn.autocommit = False
    cur  = conn.cursor(cursor_factory=RealDictCursor)
    status = None
    msg    = ""

    try:
        items_json = json.dumps([{"product_id": product_id, "quantity": 1}])
        cur.execute(
            "CALL place_order(%s, %s, %s, %s::jsonb)",
            (customer_id, address_id, payment_id, items_json),
        )
        conn.commit()
        status = "SUCCESS"

    except psycopg2.Error as e:
        conn.rollback()
        raw = str(e)
        if "Insufficient Stock" in raw:
            status = "INSUFFICIENT_STOCK"
            msg    = "Insufficient Stock"
        else:
            status = "OTHER_ERROR"
            msg    = raw[:120]
    finally:
        cur.close()
        conn.close()

    with results_lock:
        if status == "SUCCESS":
            results["success"] += 1
        elif status == "INSUFFICIENT_STOCK":
            results["insufficient_stock"] += 1
        else:
            results["other_error"] += 1
        results["details"].append({
            "thread":      thread_num,
            "customer_id": customer_id,
            "status":      status,
            "message":     msg,
        })


# ── Main ──────────────────────────────────────────────────────

def run_flash_sale():
    conn = connect()
    cur  = conn.cursor(cursor_factory=RealDictCursor)

    # Setup
    flash_product = pick_flash_product(cur)
    conn.commit()

    cur.execute("SELECT Stock_Quantity FROM Products WHERE Product_ID = %s", (flash_product,))
    stock_before = cur.fetchone()["stock_quantity"]

    customers = get_customers(cur, NUM_THREADS)
    if len(customers) < NUM_THREADS:
        print(f"Warning: only {len(customers)} eligible customers found. Adjusting thread count.")

    cur.close()
    conn.close()

    print("=" * 60)
    print("  ShopPrime — Flash Sale Concurrency Test")
    print("=" * 60)
    print(f"  Product ID    : {flash_product}")
    print(f"  Stock Before  : {stock_before}  (timestamp: {datetime.now(timezone.utc).isoformat()}Z)")
    print(f"  Concurrent Users: {len(customers)}")
    print(f"  Each user wants : 1 unit")
    print("=" * 60)
    print()

    # Launch threads simultaneously
    threads = []
    for i, row in enumerate(customers):
        t = threading.Thread(
            target=attempt_purchase,
            args=(row["customer_id"], row["address_id"], row["payment_id"], flash_product, i + 1),
            daemon=True,
        )
        threads.append(t)

    start = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.perf_counter() - start

    # Final stock check
    conn2 = connect()
    cur2  = conn2.cursor(cursor_factory=RealDictCursor)
    cur2.execute("SELECT Stock_Quantity FROM Products WHERE Product_ID = %s", (flash_product,))
    stock_after = cur2.fetchone()["stock_quantity"]
    cur2.close()
    conn2.close()

    # Results
    print(f"\nResults  (timestamp: {datetime.now(timezone.utc).isoformat()}Z)")
    print("-" * 60)
    print(f"  Successful purchases    : {results['success']}")
    print(f"  Rejected (no stock)     : {results['insufficient_stock']}")
    print(f"  Other errors            : {results['other_error']}")
    print(f"  Stock BEFORE            : {stock_before}")
    print(f"  Stock AFTER             : {stock_after}")
    print(f"  Elapsed                 : {elapsed:.3f}s")
    print("-" * 60)

    # Integrity check
    expected_stock = stock_before - results["success"]
    if stock_after == expected_stock:
        print(f"\n  [PASS] Inventory integrity verified: {stock_before} - {results['success']} = {stock_after}")
    else:
        print(f"\n  [FAIL] Inventory mismatch! Expected {expected_stock}, got {stock_after}")

    print("\nPer-thread detail (first 20):")
    for d in sorted(results["details"], key=lambda x: x["thread"])[:20]:
        print(f"  Thread {d['thread']:>2} | Customer {d['customer_id']:>4} | {d['status']}", end="")
        if d["message"]:
            print(f" | {d['message']}", end="")
        print()


if __name__ == "__main__":
    run_flash_sale()
