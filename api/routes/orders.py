"""
COMP640 Group-6
routes/orders.py — Order placement and lookup endpoints.
place_order calls the PL/pgSQL stored procedure for atomic, validated,
concurrency-safe order creation.
"""

import json
from flask import Blueprint, request, jsonify
from api.database import get_cursor, get_conn
import psycopg2

orders_bp = Blueprint("orders", __name__, url_prefix="/orders")


@orders_bp.post("/")
def place_order():
    """
    Place a new order via the place_order stored procedure.

    Body:
    {
        "customer_id": 1,
        "address_id":  2,
        "payment_id":  3,
        "items": [
            {"product_id": 10, "quantity": 2},
            {"product_id": 22, "quantity": 1}
        ]
    }
    """
    data = request.get_json()
    required = ("customer_id", "address_id", "payment_id", "items")
    if not all(k in data for k in required):
        return jsonify({"error": f"Required fields: {required}"}), 400

    if not isinstance(data["items"], list) or len(data["items"]) == 0:
        return jsonify({"error": "items must be a non-empty list"}), 400

    items_json = json.dumps(data["items"])

    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=__import__("psycopg2.extras", fromlist=["RealDictCursor"]).RealDictCursor)
        try:
            cur.execute(
                "CALL place_order(%s, %s, %s, %s::jsonb)",
                (data["customer_id"], data["address_id"], data["payment_id"], items_json),
            )
            conn.commit()

            # Fetch the newly created order
            cur.execute(
                """
                SELECT o.*, COUNT(oi.Order_Item_ID) AS item_count
                FROM Orders o
                JOIN Order_Items oi ON oi.Order_ID = o.Order_ID
                WHERE o.Customer_ID = %s
                GROUP BY o.Order_ID
                ORDER BY o.Order_Date DESC
                LIMIT 1
                """,
                (data["customer_id"],),
            )
            order = cur.fetchone()
            return jsonify({"message": "Order placed successfully", "order": dict(order)}), 201

        except psycopg2.errors.RaiseException as e:
            conn.rollback()
            msg = str(e).split("\n")[0].replace("ERROR:  ", "")
            status = 409 if "Insufficient Stock" in msg else 400
            return jsonify({"error": msg}), status
        except Exception as e:
            conn.rollback()
            return jsonify({"error": str(e)}), 500
        finally:
            cur.close()


@orders_bp.get("/<int:order_id>")
def get_order(order_id):
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT o.*,
                   c.First_Name || ' ' || c.Last_Name AS customer_name,
                   a.City, a.State
            FROM Orders o
            JOIN Customers c ON c.Customer_ID = o.Customer_ID
            JOIN Addresses a ON a.Address_ID  = o.Shipping_Address_ID
            WHERE o.Order_ID = %s
            """,
            (order_id,),
        )
        order = cur.fetchone()

    if not order:
        return jsonify({"error": "Order not found"}), 404

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT oi.*, p.Product_Name, p.Product_Color, p.Product_Size
            FROM Order_Items oi
            JOIN Products p ON p.Product_ID = oi.Product_ID
            WHERE oi.Order_ID = %s
            """,
            (order_id,),
        )
        items = cur.fetchall()

    result = dict(order)
    result["items"] = [dict(i) for i in items]
    return jsonify(result)


@orders_bp.patch("/<int:order_id>/status")
def update_status(order_id):
    data = request.get_json()
    valid = ("pending", "processing", "shipped", "delivered", "cancelled")
    if data.get("status") not in valid:
        return jsonify({"error": f"status must be one of {valid}"}), 400

    with get_cursor() as cur:
        cur.execute(
            "UPDATE Orders SET Order_Status = %s WHERE Order_ID = %s RETURNING *",
            (data["status"], order_id),
        )
        row = cur.fetchone()

    if not row:
        return jsonify({"error": "Order not found"}), 404
    return jsonify(dict(row))
