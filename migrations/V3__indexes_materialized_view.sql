-- ============================================================
-- V3__indexes_materialized_view.sql  |  ShopPrime Performance Layer
-- Phase 3: Indexes for 10k+ orders, materialized view for reporting
-- ============================================================

-- ════════════════════════════════════════════════════════════
-- SECTION 1: INDEXES
-- Strategy: target FK columns, filter columns, and sort columns
-- used by the most common query patterns.
-- ════════════════════════════════════════════════════════════

-- Orders: filter by customer (order history lookup)
CREATE INDEX IF NOT EXISTS idx_orders_customer_id
    ON Orders (Customer_ID);

-- Orders: filter by status (dashboard / fulfillment queries)
CREATE INDEX IF NOT EXISTS idx_orders_status
    ON Orders (Order_Status);

-- Orders: range scans on date (reporting, analytics)
CREATE INDEX IF NOT EXISTS idx_orders_date
    ON Orders (Order_Date DESC);

-- Order_Items: join from orders down to items (most frequent join)
CREATE INDEX IF NOT EXISTS idx_order_items_order_id
    ON Order_Items (Order_ID);

-- Order_Items: join from products up to items (inventory reporting)
CREATE INDEX IF NOT EXISTS idx_order_items_product_id
    ON Order_Items (Product_ID);

-- Products: filter by supplier (vendor dashboard)
CREATE INDEX IF NOT EXISTS idx_products_supplier_id
    ON Products (Supplier_ID);

-- Products: filter by category (browse / search)
CREATE INDEX IF NOT EXISTS idx_products_category_id
    ON Products (Category_ID);

-- Products: low-stock alerts (partial index)
CREATE INDEX IF NOT EXISTS idx_products_stock
    ON Products (Stock_Quantity)
    WHERE Stock_Quantity < 10;

-- Addresses: FK lookup from Orders
CREATE INDEX IF NOT EXISTS idx_addresses_customer_id
    ON Addresses (Customer_ID);

-- Payment_Methods: FK lookup from Orders
CREATE INDEX IF NOT EXISTS idx_payment_customer_id
    ON Payment_Methods (Customer_ID);

-- Audit_Log: time-series scan (most recent changes first)
CREATE INDEX IF NOT EXISTS idx_audit_log_changed_at
    ON Audit_Log (Changed_At DESC);

-- Audit_Log: filter by table (e.g. "show all Products changes")
CREATE INDEX IF NOT EXISTS idx_audit_log_table_name
    ON Audit_Log (Table_Name);

-- Categories: self-join for hierarchy traversal
CREATE INDEX IF NOT EXISTS idx_categories_parent
    ON Categories (Parent_Category_ID);


-- ════════════════════════════════════════════════════════════
-- SECTION 2: MATERIALIZED VIEW — Vendor_Monthly_Rollup
-- Aggregates revenue and units sold per supplier per month.
-- Refresh with: REFRESH MATERIALIZED VIEW CONCURRENTLY Vendor_Monthly_Rollup;
-- ════════════════════════════════════════════════════════════

CREATE MATERIALIZED VIEW IF NOT EXISTS Vendor_Monthly_Rollup AS
SELECT
    p.Supplier_ID                                        AS Vendor_ID,
    TO_CHAR(o.Order_Date, 'YYYY-MM')                    AS Month_Year,
    SUM(oi.Price_At_Purchase * oi.Quantity)             AS Total_Revenue,
    SUM(oi.Quantity)                                    AS Total_Units_Sold
FROM Order_Items oi
JOIN Orders   o ON o.Order_ID   = oi.Order_ID
JOIN Products p ON p.Product_ID = oi.Product_ID
WHERE o.Order_Status NOT IN ('cancelled')
GROUP BY p.Supplier_ID, TO_CHAR(o.Order_Date, 'YYYY-MM')
ORDER BY p.Supplier_ID, Month_Year;

-- Unique index on the MV enables CONCURRENTLY refresh (no table lock)
CREATE UNIQUE INDEX IF NOT EXISTS idx_vendor_rollup_unique
    ON Vendor_Monthly_Rollup (Vendor_ID, Month_Year);


-- ════════════════════════════════════════════════════════════
-- SECTION 3: EXPLAIN ANALYZE TEMPLATE
-- Run after seeding to compare before/after index performance.
-- ════════════════════════════════════════════════════════════

-- Example query that benefits from the indexes above:
-- EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
-- SELECT
--     o.Order_ID,
--     o.Order_Date,
--     o.Total_Amount,
--     COUNT(oi.Order_Item_ID) AS items
-- FROM Orders o
-- JOIN Order_Items oi ON oi.Order_ID = o.Order_ID
-- WHERE o.Customer_ID = 42
--   AND o.Order_Status = 'delivered'
-- GROUP BY o.Order_ID, o.Order_Date, o.Total_Amount
-- ORDER BY o.Order_Date DESC;
