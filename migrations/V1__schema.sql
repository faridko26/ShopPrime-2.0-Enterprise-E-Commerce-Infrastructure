-- ============================================================
-- V1__schema.sql  |  ShopPrime Core Schema
-- Phase 1: Normalized tables, named CHECK constraints, 3NF+
-- ============================================================

-- ── Customers ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS Customers (
    Customer_ID   SERIAL PRIMARY KEY,
    First_Name    VARCHAR(100) NOT NULL,
    Last_Name     VARCHAR(100) NOT NULL,
    Email         VARCHAR(255) NOT NULL UNIQUE,
    Phone         VARCHAR(20),
    Created_At    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_email_format
        CHECK (Email ~* '^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$')
);

-- ── Addresses ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS Addresses (
    Address_ID    SERIAL PRIMARY KEY,
    Customer_ID   INT NOT NULL REFERENCES Customers(Customer_ID) ON DELETE CASCADE,
    Address_Line1 VARCHAR(255) NOT NULL,
    Address_Line2 VARCHAR(255),
    City          VARCHAR(100) NOT NULL,
    State         VARCHAR(100) NOT NULL,
    Zip_Code      VARCHAR(10)  NOT NULL,
    Address_Type  VARCHAR(20)  NOT NULL,

    CONSTRAINT chk_zip_format
        CHECK (Zip_Code ~ '^\d{5}(-\d{4})?$'),
    CONSTRAINT chk_address_type
        CHECK (Address_Type IN ('home', 'work', 'billing', 'shipping'))
);

-- ── Payment_Methods ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS Payment_Methods (
    Payment_ID           SERIAL PRIMARY KEY,
    Customer_ID          INT NOT NULL REFERENCES Customers(Customer_ID) ON DELETE CASCADE,
    Payment_Type         VARCHAR(50)  NOT NULL,
    Provider             VARCHAR(100),
    Account_Number_Masked VARCHAR(20),
    Expiry_Date          DATE,
    Is_Default           BOOLEAN NOT NULL DEFAULT FALSE
);

-- ── Suppliers ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS Suppliers (
    Supplier_ID    SERIAL PRIMARY KEY,
    Supplier_Name  VARCHAR(255) NOT NULL,
    Contact_Email  VARCHAR(255),
    Location_Country VARCHAR(100),

    CONSTRAINT chk_supplier_email_format
        CHECK (Contact_Email IS NULL OR
               Contact_Email ~* '^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$')
);

-- ── Categories (self-referencing) ───────────────────────────
CREATE TABLE IF NOT EXISTS Categories (
    Category_ID       SERIAL PRIMARY KEY,
    Category_Name     VARCHAR(100) NOT NULL,
    Parent_Category_ID INT REFERENCES Categories(Category_ID) ON DELETE SET NULL
);

-- ── Products ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS Products (
    Product_ID          SERIAL PRIMARY KEY,
    Supplier_ID         INT NOT NULL REFERENCES Suppliers(Supplier_ID),
    Category_ID         INT NOT NULL REFERENCES Categories(Category_ID),
    Product_Name        VARCHAR(255) NOT NULL,
    Product_Description TEXT,
    Price               NUMERIC(10,2) NOT NULL,
    Stock_Quantity      INT NOT NULL DEFAULT 0,
    Product_Color       VARCHAR(50),
    Product_Size        VARCHAR(20),

    CONSTRAINT chk_price_positive
        CHECK (Price > 0),
    CONSTRAINT chk_stock_non_negative
        CHECK (Stock_Quantity >= 0)
);

-- ── Orders ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS Orders (
    Order_ID           SERIAL PRIMARY KEY,
    Customer_ID        INT NOT NULL REFERENCES Customers(Customer_ID),
    Shipping_Address_ID INT NOT NULL REFERENCES Addresses(Address_ID),
    Payment_Method_ID  INT NOT NULL REFERENCES Payment_Methods(Payment_ID),
    Order_Date         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    Total_Amount       NUMERIC(12,2) NOT NULL,
    Order_Status       VARCHAR(20) NOT NULL DEFAULT 'pending',

    CONSTRAINT chk_order_date_not_future
        CHECK (Order_Date <= CURRENT_TIMESTAMP),
    CONSTRAINT chk_total_amount_positive
        CHECK (Total_Amount > 0),
    CONSTRAINT chk_order_status
        CHECK (Order_Status IN ('pending', 'processing', 'shipped', 'delivered', 'cancelled'))
);

-- ── Order_Items ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS Order_Items (
    Order_Item_ID   SERIAL PRIMARY KEY,
    Order_ID        INT NOT NULL REFERENCES Orders(Order_ID) ON DELETE CASCADE,
    Product_ID      INT NOT NULL REFERENCES Products(Product_ID),
    Quantity        INT NOT NULL,
    Price_At_Purchase NUMERIC(10,2) NOT NULL,

    CONSTRAINT chk_quantity_positive
        CHECK (Quantity > 0),
    CONSTRAINT chk_price_at_purchase_positive
        CHECK (Price_At_Purchase > 0)
);

-- ── Audit_Log ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS Audit_Log (
    Log_ID      SERIAL PRIMARY KEY,
    Table_Name  VARCHAR(100) NOT NULL,
    Column_Name VARCHAR(100) NOT NULL,
    Old_Value   TEXT,
    New_Value   TEXT,
    Changed_At  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    Changed_By  VARCHAR(100) NOT NULL
);
