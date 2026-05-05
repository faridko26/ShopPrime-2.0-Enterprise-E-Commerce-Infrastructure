"""
COMP640 Group-6
routes/products.py — Product catalog endpoints.
"""

from flask import Blueprint, request, jsonify
from api.database import get_cursor

products_bp = Blueprint("products", __name__, url_prefix="/products")


@products_bp.get("/")
def list_products():
    category_id = request.args.get("category_id", type=int)
    supplier_id = request.args.get("supplier_id", type=int)
    limit  = request.args.get("limit",  default=50,  type=int)
    offset = request.args.get("offset", default=0,   type=int)

    query = """
        SELECT p.*, s.Supplier_Name, c.Category_Name
        FROM Products p
        JOIN Suppliers s ON s.Supplier_ID = p.Supplier_ID
        JOIN Categories c ON c.Category_ID = p.Category_ID
        WHERE (%s IS NULL OR p.Category_ID = %s)
          AND (%s IS NULL OR p.Supplier_ID = %s)
        ORDER BY p.Product_ID
        LIMIT %s OFFSET %s
    """
    with get_cursor() as cur:
        cur.execute(query, (category_id, category_id, supplier_id, supplier_id, limit, offset))
        rows = cur.fetchall()
    return jsonify([dict(r) for r in rows])


@products_bp.get("/<int:product_id>")
def get_product(product_id):
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT p.*, s.Supplier_Name, c.Category_Name
            FROM Products p
            JOIN Suppliers s ON s.Supplier_ID = p.Supplier_ID
            JOIN Categories c ON c.Category_ID = p.Category_ID
            WHERE p.Product_ID = %s
            """,
            (product_id,),
        )
        row = cur.fetchone()
    if not row:
        return jsonify({"error": "Product not found"}), 404
    return jsonify(dict(row))


@products_bp.post("/")
def create_product():
    data = request.get_json()
    required = ("supplier_id", "category_id", "product_name", "price", "stock_quantity")
    if not all(k in data for k in required):
        return jsonify({"error": f"Required fields: {required}"}), 400

    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO Products
                (Supplier_ID, Category_ID, Product_Name, Product_Description,
                 Price, Stock_Quantity, Product_Color, Product_Size)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                data["supplier_id"],
                data["category_id"],
                data["product_name"],
                data.get("product_description"),
                data["price"],
                data["stock_quantity"],
                data.get("product_color"),
                data.get("product_size"),
            ),
        )
        row = cur.fetchone()
    return jsonify(dict(row)), 201


@products_bp.put("/<int:product_id>/price")
def update_price(product_id):
    """Update product price — triggers audit log automatically."""
    data = request.get_json()
    if "price" not in data or float(data["price"]) <= 0:
        return jsonify({"error": "price must be a positive number"}), 400

    with get_cursor() as cur:
        cur.execute(
            "UPDATE Products SET Price = %s WHERE Product_ID = %s RETURNING *",
            (data["price"], product_id),
        )
        row = cur.fetchone()
    if not row:
        return jsonify({"error": "Product not found"}), 404
    return jsonify(dict(row))


@products_bp.get("/vendor-rollup")
def vendor_rollup():
    """Query the materialized view for vendor monthly revenue."""
    vendor_id  = request.args.get("vendor_id",  type=int)
    month_year = request.args.get("month_year")

    query = """
        SELECT * FROM Vendor_Monthly_Rollup
        WHERE (%s IS NULL OR Vendor_ID = %s)
          AND (%s IS NULL OR Month_Year = %s)
        ORDER BY Vendor_ID, Month_Year
    """
    with get_cursor() as cur:
        cur.execute(query, (vendor_id, vendor_id, month_year, month_year))
        rows = cur.fetchall()
    return jsonify([dict(r) for r in rows])
