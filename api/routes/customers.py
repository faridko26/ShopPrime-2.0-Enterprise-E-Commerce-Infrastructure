"""
COMP640 Group-6
routes/customers.py — Customer & address endpoints.
"""

from flask import Blueprint, request, jsonify
from api.database import get_cursor
import psycopg2

customers_bp = Blueprint("customers", __name__, url_prefix="/customers")


@customers_bp.get("/<int:customer_id>")
def get_customer(customer_id):
    with get_cursor() as cur:
        cur.execute(
            "SELECT * FROM Customers WHERE Customer_ID = %s", (customer_id,)
        )
        row = cur.fetchone()
    if not row:
        return jsonify({"error": "Customer not found"}), 404
    return jsonify(dict(row))


@customers_bp.post("/")
def create_customer():
    data = request.get_json()
    required = ("first_name", "last_name", "email")
    if not all(k in data for k in required):
        return jsonify({"error": f"Required fields: {required}"}), 400

    with get_cursor() as cur:
        try:
            cur.execute(
                """
                INSERT INTO Customers (First_Name, Last_Name, Email, Phone)
                VALUES (%s, %s, %s, %s)
                RETURNING *
                """,
                (data["first_name"], data["last_name"], data["email"], data.get("phone")),
            )
            row = cur.fetchone()
        except psycopg2.errors.UniqueViolation:
            return jsonify({"error": "Email already registered"}), 409
        except psycopg2.errors.CheckViolation as e:
            return jsonify({"error": str(e)}), 400

    return jsonify(dict(row)), 201


@customers_bp.get("/<int:customer_id>/orders")
def get_customer_orders(customer_id):
    with get_cursor() as cur:
        cur.execute(
            "SELECT * FROM get_customer_orders(%s)", (customer_id,)
        )
        rows = cur.fetchall()
    return jsonify([dict(r) for r in rows])


@customers_bp.get("/<int:customer_id>/addresses")
def get_addresses(customer_id):
    with get_cursor() as cur:
        cur.execute(
            "SELECT * FROM Addresses WHERE Customer_ID = %s", (customer_id,)
        )
        rows = cur.fetchall()
    return jsonify([dict(r) for r in rows])


@customers_bp.post("/<int:customer_id>/addresses")
def add_address(customer_id):
    data = request.get_json()
    required = ("address_line1", "city", "state", "zip_code", "address_type")
    if not all(k in data for k in required):
        return jsonify({"error": f"Required fields: {required}"}), 400

    with get_cursor() as cur:
        try:
            cur.execute(
                """
                INSERT INTO Addresses
                    (Customer_ID, Address_Line1, Address_Line2, City, State, Zip_Code, Address_Type)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    customer_id,
                    data["address_line1"],
                    data.get("address_line2"),
                    data["city"],
                    data["state"],
                    data["zip_code"],
                    data["address_type"],
                ),
            )
            row = cur.fetchone()
        except psycopg2.errors.CheckViolation as e:
            return jsonify({"error": str(e)}), 400

    return jsonify(dict(row)), 201
