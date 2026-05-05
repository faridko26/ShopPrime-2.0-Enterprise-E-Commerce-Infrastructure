"""
main.py — ShopPrime Flask API entry point.

Run:
    python -m api.main
    or
    flask --app api.main run --port 8000
"""

import os
from flask import Flask, jsonify
from dotenv import load_dotenv

load_dotenv()

from api.routes.customers import customers_bp
from api.routes.products  import products_bp
from api.routes.orders    import orders_bp
from api.database         import close_pool


def create_app() -> Flask:
    app = Flask(__name__)

    # Register blueprints
    app.register_blueprint(customers_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(orders_bp)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "ShopPrime API"})

    @app.teardown_appcontext
    def teardown(_exc):
        pass  # Pool persists across requests; closed on shutdown

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("APP_PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=True)
