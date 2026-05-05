-- ============================================================
-- V2__rbac_triggers_procedures.sql  |  ShopPrime Security Layer
-- Phase 1 & 2: RBAC roles, audit trigger, place_order procedure
-- ============================================================

-- ════════════════════════════════════════════════════════════
-- SECTION 1: ROLE-BASED ACCESS CONTROL (RBAC)
-- ════════════════════════════════════════════════════════════

-- Drop roles if they exist (idempotent re-run)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'customer_role') THEN
        CREATE ROLE customer_role;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'vendor_role') THEN
        CREATE ROLE vendor_role;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'audit_role') THEN
        CREATE ROLE audit_role;
    END IF;
END
$$;

-- ── customer_role: read own profile + order history only ────
-- (Row-level security would enforce "own" data; grants define table access)
GRANT SELECT ON Customers       TO customer_role;
GRANT SELECT ON Addresses       TO customer_role;
GRANT SELECT ON Payment_Methods TO customer_role;
GRANT SELECT ON Orders          TO customer_role;
GRANT SELECT ON Order_Items     TO customer_role;
GRANT SELECT ON Products        TO customer_role;
GRANT SELECT ON Categories      TO customer_role;

-- ── vendor_role: update stock and price on their products only ─
GRANT SELECT        ON Products TO vendor_role;
GRANT UPDATE (Price, Stock_Quantity) ON Products TO vendor_role;
GRANT SELECT        ON Suppliers TO vendor_role;
GRANT SELECT        ON Categories TO vendor_role;

-- ── audit_role: read-only on Audit_Log, no DML ──────────────
GRANT SELECT ON Audit_Log TO audit_role;
-- Explicitly deny DML (redundant but documented for clarity)
REVOKE INSERT, UPDATE, DELETE ON Audit_Log FROM audit_role;


-- ════════════════════════════════════════════════════════════
-- SECTION 2: AUDIT TRIGGER — auto-log every price change
-- ════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION trg_audit_product_price()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    -- Only fire when Price actually changes
    IF OLD.Price IS DISTINCT FROM NEW.Price THEN
        INSERT INTO Audit_Log (Table_Name, Column_Name, Old_Value, New_Value, Changed_At, Changed_By)
        VALUES (
            'Products',
            'Price',
            OLD.Price::TEXT,
            NEW.Price::TEXT,
            CURRENT_TIMESTAMP,
            CURRENT_USER
        );
    END IF;

    -- Also log Stock_Quantity changes (useful for inventory auditing)
    IF OLD.Stock_Quantity IS DISTINCT FROM NEW.Stock_Quantity THEN
        INSERT INTO Audit_Log (Table_Name, Column_Name, Old_Value, New_Value, Changed_At, Changed_By)
        VALUES (
            'Products',
            'Stock_Quantity',
            OLD.Stock_Quantity::TEXT,
            NEW.Stock_Quantity::TEXT,
            CURRENT_TIMESTAMP,
            CURRENT_USER
        );
    END IF;

    RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER audit_product_changes
AFTER UPDATE ON Products
FOR EACH ROW
EXECUTE FUNCTION trg_audit_product_price();


-- ════════════════════════════════════════════════════════════
-- SECTION 3: STORED PROCEDURE — place_order
-- Phase 2: Atomic, validated, concurrency-safe order placement
-- ════════════════════════════════════════════════════════════

CREATE OR REPLACE PROCEDURE place_order(
    p_customer_id   INT,
    p_address_id    INT,
    p_payment_id    INT,
    -- items: array of (product_id, quantity) as JSON array
    -- e.g. '[{"product_id":1,"quantity":2},{"product_id":5,"quantity":1}]'
    p_items         JSONB
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_order_id      INT;
    v_total_amount  NUMERIC(12,2) := 0;
    v_item          JSONB;
    v_product_id    INT;
    v_quantity      INT;
    v_price         NUMERIC(10,2);
    v_stock         INT;
    v_supplier_id   INT;
BEGIN
    -- ── Step 1: Validate Customer ───────────────────────────
    IF NOT EXISTS (SELECT 1 FROM Customers WHERE Customer_ID = p_customer_id) THEN
        RAISE EXCEPTION 'Invalid Entity Reference: Customer_ID % does not exist.', p_customer_id;
    END IF;

    -- ── Step 2: Validate Address belongs to Customer ────────
    IF NOT EXISTS (
        SELECT 1 FROM Addresses
        WHERE Address_ID = p_address_id AND Customer_ID = p_customer_id
    ) THEN
        RAISE EXCEPTION 'Invalid Entity Reference: Address_ID % does not belong to Customer_ID %.', p_address_id, p_customer_id;
    END IF;

    -- ── Step 3: Validate Payment Method belongs to Customer ─
    IF NOT EXISTS (
        SELECT 1 FROM Payment_Methods
        WHERE Payment_ID = p_payment_id AND Customer_ID = p_customer_id
    ) THEN
        RAISE EXCEPTION 'Invalid Entity Reference: Payment_ID % does not belong to Customer_ID %.', p_payment_id, p_customer_id;
    END IF;

    -- ── Step 4: Validate items array is not empty ───────────
    IF p_items IS NULL OR jsonb_array_length(p_items) = 0 THEN
        RAISE EXCEPTION 'Order must contain at least one item.';
    END IF;

    -- ── Step 5: Create Order Header (placeholder total) ─────
    INSERT INTO Orders (Customer_ID, Shipping_Address_ID, Payment_Method_ID, Order_Date, Total_Amount, Order_Status)
    VALUES (p_customer_id, p_address_id, p_payment_id, CURRENT_TIMESTAMP, 0.01, 'pending')
    RETURNING Order_ID INTO v_order_id;

    -- ── Step 6: Process each line item ──────────────────────
    FOR v_item IN SELECT * FROM jsonb_array_elements(p_items)
    LOOP
        v_product_id := (v_item->>'product_id')::INT;
        v_quantity   := (v_item->>'quantity')::INT;

        IF v_quantity <= 0 THEN
            RAISE EXCEPTION 'Quantity must be positive for product_id %.', v_product_id;
        END IF;

        -- Row-level lock: prevents race conditions during concurrent checkouts
        SELECT Price, Stock_Quantity
        INTO v_price, v_stock
        FROM Products
        WHERE Product_ID = v_product_id
        FOR UPDATE;

        -- Validate product exists
        IF NOT FOUND THEN
            RAISE EXCEPTION 'Invalid Entity Reference: Product_ID % does not exist.', v_product_id;
        END IF;

        -- Check stock
        IF v_stock < v_quantity THEN
            RAISE EXCEPTION 'Insufficient Stock: Product_ID % has % units available, requested %.', v_product_id, v_stock, v_quantity;
        END IF;

        -- Insert line item (price captured from DB, not frontend)
        INSERT INTO Order_Items (Order_ID, Product_ID, Quantity, Price_At_Purchase)
        VALUES (v_order_id, v_product_id, v_quantity, v_price);

        -- Deduct stock
        UPDATE Products
        SET Stock_Quantity = Stock_Quantity - v_quantity
        WHERE Product_ID = v_product_id;

        -- Accumulate total
        v_total_amount := v_total_amount + (v_price * v_quantity);
    END LOOP;

    -- ── Step 7: Update Order with correct total ──────────────
    UPDATE Orders
    SET Total_Amount = v_total_amount
    WHERE Order_ID = v_order_id;

    RAISE NOTICE 'Order % created successfully. Total: $%', v_order_id, v_total_amount;

EXCEPTION
    WHEN OTHERS THEN
        -- Any failure rolls back the entire transaction automatically
        -- (PL/pgSQL procedures participate in the caller's transaction)
        RAISE;
END;
$$;


-- ════════════════════════════════════════════════════════════
-- SECTION 4: HELPER FUNCTION — get_customer_orders
-- Returns all orders for a given customer (used by customer_role)
-- ════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION get_customer_orders(p_customer_id INT)
RETURNS TABLE (
    order_id      INT,
    order_date    TIMESTAMP,
    order_status  VARCHAR,
    total_amount  NUMERIC,
    item_count    BIGINT
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        o.Order_ID,
        o.Order_Date,
        o.Order_Status,
        o.Total_Amount,
        COUNT(oi.Order_Item_ID) AS item_count
    FROM Orders o
    JOIN Order_Items oi ON oi.Order_ID = o.Order_ID
    WHERE o.Customer_ID = p_customer_id
    GROUP BY o.Order_ID, o.Order_Date, o.Order_Status, o.Total_Amount
    ORDER BY o.Order_Date DESC;
$$;
