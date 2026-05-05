"""
seed_data.py — ShopPrime Data Generation Script
Generates:
  - 10 suppliers, 5 top-level + 15 sub-categories
  - 1,000 products
  - 500 customers, each with 1–2 addresses and 1 payment method
  - 10,000 orders (multi-item)

Run:
    python scripts/seed_data.py
"""

import os
import random
import time
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import execute_values
from faker import Faker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
fake = Faker()
random.seed(42)
Faker.seed(42)

# ── Helpers ─────────────────────────────────────────────────

def connect():
    return psycopg2.connect(DATABASE_URL)


def random_past_date(days_back=730):
    delta = timedelta(
        days=random.randint(0, days_back),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
    )
    return datetime.now(timezone.utc) - delta


COLORS = ["Red", "Blue", "Green", "Black", "White", "Yellow", "Purple", "Orange", "Gray", "Pink"]
SIZES  = ["XS", "S", "M", "L", "XL", "XXL", "One Size", "6", "7", "8", "9", "10", "11"]
STATUS_WEIGHTS = [
    ("delivered",  60),
    ("shipped",    15),
    ("processing", 10),
    ("pending",     8),
    ("cancelled",   7),
]
STATUSES    = [s for s, w in STATUS_WEIGHTS for _ in range(w)]
PAY_TYPES   = ["credit_card", "debit_card", "paypal", "apple_pay", "google_pay"]
PROVIDERS   = ["Visa", "Mastercard", "Amex", "Discover", "PayPal", "Apple", "Google"]
ADDR_TYPES  = ["home", "work", "shipping", "billing"]


# ── Main seeding logic ───────────────────────────────────────

def seed():
    conn = connect()
    cur  = conn.cursor()

    print("Clearing existing data...")
    cur.execute("""
        TRUNCATE TABLE Audit_Log, Order_Items, Orders,
                       Payment_Methods, Addresses,
                       Products, Customers,
                       Suppliers, Categories
        RESTART IDENTITY CASCADE;
    """)
    conn.commit()

    # ── 1. Suppliers ─────────────────────────────────────────
    print("Seeding suppliers...")
    supplier_data = [
        (fake.company(), fake.company_email(), fake.country())
        for _ in range(10)
    ]
    rows = execute_values(
        cur,
        "INSERT INTO Suppliers (Supplier_Name, Contact_Email, Location_Country) VALUES %s RETURNING Supplier_ID",
        supplier_data,
        fetch=True,
    )
    supplier_ids = [r[0] for r in rows]
    conn.commit()

    # ── 2. Categories ────────────────────────────────────────
    print("Seeding categories...")
    top_cats = ["Electronics", "Clothing", "Home & Garden", "Sports", "Books"]
    sub_cats = {
        "Electronics": ["Phones", "Laptops", "Tablets", "Accessories"],
        "Clothing":    ["Men", "Women", "Kids", "Shoes"],
        "Home & Garden": ["Furniture", "Kitchen", "Outdoor"],
        "Sports":      ["Fitness", "Team Sports"],
        "Books":       ["Fiction", "Non-Fiction"],
    }

    top_ids = {}
    for name in top_cats:
        cur.execute(
            "INSERT INTO Categories (Category_Name) VALUES (%s) RETURNING Category_ID", (name,)
        )
        top_ids[name] = cur.fetchone()[0]

    category_ids = list(top_ids.values())
    for parent_name, children in sub_cats.items():
        parent_id = top_ids[parent_name]
        for child in children:
            cur.execute(
                "INSERT INTO Categories (Category_Name, Parent_Category_ID) VALUES (%s, %s) RETURNING Category_ID",
                (child, parent_id),
            )
            category_ids.append(cur.fetchone()[0])
    conn.commit()

    # ── 3. Products (1,000) ──────────────────────────────────
    print("Seeding 1,000 products...")
    product_rows = []
    for _ in range(1000):
        product_rows.append((
            random.choice(supplier_ids),
            random.choice(category_ids),
            fake.catch_phrase(),
            fake.text(max_nb_chars=200),
            round(random.uniform(4.99, 999.99), 2),
            random.randint(50, 500),   # start with healthy stock
            random.choice(COLORS),
            random.choice(SIZES),
        ))
    rows = execute_values(
        cur,
        """INSERT INTO Products
               (Supplier_ID, Category_ID, Product_Name, Product_Description,
                Price, Stock_Quantity, Product_Color, Product_Size)
           VALUES %s RETURNING Product_ID, Price""",
        product_rows,
        fetch=True,
    )
    product_ids    = [r[0] for r in rows]
    price_cache    = {r[0]: float(r[1]) for r in rows}   # {product_id: price}
    conn.commit()

    # ── 4. Customers (500) ───────────────────────────────────
    print("Seeding 500 customers...")
    customer_rows = []
    seen_emails   = set()
    while len(customer_rows) < 500:
        email = fake.unique.email()
        if email in seen_emails:
            continue
        seen_emails.add(email)
        customer_rows.append((
            fake.first_name(),
            fake.last_name(),
            email,
            fake.phone_number()[:20],
            random_past_date(1000),
        ))
    rows = execute_values(
        cur,
        "INSERT INTO Customers (First_Name, Last_Name, Email, Phone, Created_At) VALUES %s RETURNING Customer_ID",
        customer_rows,
        fetch=True,
    )
    customer_ids = [r[0] for r in rows]
    conn.commit()

    # ── 5. Addresses ─────────────────────────────────────────
    print("Seeding addresses...")
    addr_rows   = []
    addr_cid_order = []   # track which cid each row belongs to

    for cid in customer_ids:
        for _ in range(random.randint(1, 2)):
            addr_rows.append((
                cid,
                fake.street_address(),
                fake.secondary_address() if random.random() < 0.3 else None,
                fake.city(),
                fake.state_abbr(),
                fake.zipcode()[:5],
                random.choice(ADDR_TYPES),
            ))
            addr_cid_order.append(cid)

    rows = execute_values(
        cur,
        """INSERT INTO Addresses
               (Customer_ID, Address_Line1, Address_Line2, City, State, Zip_Code, Address_Type)
           VALUES %s RETURNING Address_ID, Customer_ID""",
        addr_rows,
        fetch=True,
    )
    address_map: dict[int, list[int]] = {}
    for addr_id, cid in rows:
        address_map.setdefault(cid, []).append(addr_id)
    conn.commit()

    # ── 6. Payment Methods ───────────────────────────────────
    print("Seeding payment methods...")
    pay_rows = []
    for cid in customer_ids:
        pay_rows.append((
            cid,
            random.choice(PAY_TYPES),
            random.choice(PROVIDERS),
            f"****{random.randint(1000, 9999)}",
            fake.future_date(end_date="+5y"),
            True,
        ))
    rows = execute_values(
        cur,
        """INSERT INTO Payment_Methods
               (Customer_ID, Payment_Type, Provider, Account_Number_Masked, Expiry_Date, Is_Default)
           VALUES %s RETURNING Payment_ID, Customer_ID""",
        pay_rows,
        fetch=True,
    )
    payment_map = {cid: pay_id for pay_id, cid in rows}
    conn.commit()

    # Verify all customers have addresses and payments
    missing = [cid for cid in customer_ids if cid not in address_map or not address_map[cid]]
    if missing:
        raise RuntimeError(f"{len(missing)} customers have no address. Aborting.")

    # ── 7. Orders (10,000) ───────────────────────────────────
    print("Seeding 10,000 orders...")
    order_rows = []
    for _ in range(10000):
        cid    = random.choice(customer_ids)
        addr   = random.choice(address_map[cid])
        pay    = payment_map[cid]
        status = random.choice(STATUSES)
        odate  = random_past_date(730)
        order_rows.append((cid, addr, pay, odate, 0.01, status))

    rows = execute_values(
        cur,
        """INSERT INTO Orders
               (Customer_ID, Shipping_Address_ID, Payment_Method_ID, Order_Date, Total_Amount, Order_Status)
           VALUES %s RETURNING Order_ID""",
        order_rows,
        fetch=True,
    )
    order_ids = [r[0] for r in rows]
    conn.commit()

    # ── 8. Order Items ───────────────────────────────────────
    print("Seeding order items...")
    item_rows = []
    total_map = {oid: 0.0 for oid in order_ids}

    for oid in order_ids:
        num_items = random.randint(1, 5)
        chosen    = random.sample(product_ids, min(num_items, len(product_ids)))
        for pid in chosen:
            qty   = random.randint(1, 3)
            price = price_cache[pid]
            item_rows.append((oid, pid, qty, price))
            total_map[oid] += price * qty

    execute_values(
        cur,
        "INSERT INTO Order_Items (Order_ID, Product_ID, Quantity, Price_At_Purchase) VALUES %s",
        item_rows,
        page_size=5000,
    )

    # Bulk-update order totals in a single SQL statement via a temp VALUES table
    totals_data = [(oid, round(total_map[oid], 2)) for oid in order_ids]
    execute_values(
        cur,
        """
        UPDATE Orders AS o
        SET Total_Amount = v.total
        FROM (VALUES %s) AS v(order_id, total)
        WHERE o.Order_ID = v.order_id
        """,
        totals_data,
        template="(%s, %s::numeric)",
        page_size=5000,
    )
    conn.commit()

    # ── 9. Refresh materialized view ─────────────────────────
    print("Refreshing Vendor_Monthly_Rollup...")
    cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY Vendor_Monthly_Rollup;")
    conn.commit()

    cur.close()
    conn.close()

    print("\n=== Seeding complete ===")
    print(f"  Suppliers  : 10")
    print(f"  Categories : {len(category_ids)}")
    print(f"  Products   : 1,000")
    print(f"  Customers  : 500")
    print(f"  Orders     : 10,000")
    print(f"  Order Items: {len(item_rows)}")


if __name__ == "__main__":
    start = time.time()
    seed()
    print(f"\nTotal time: {time.time() - start:.1f}s")
