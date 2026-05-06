-- ============================================================
-- V4__grader_readonly_role.sql  |  ShopPrime Grader Access
-- Creates a read-only role for grader verification of RBAC setup
-- ============================================================

-- Create the grader role
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'grader') THEN
        CREATE ROLE grader WITH LOGIN PASSWORD 'npg_t9XZHNbm5aEl';
    END IF;
END
$$;

-- Grant read-only access to all tables
GRANT SELECT ON ALL TABLES IN SCHEMA public TO grader;

-- Explicitly grant access to materialized view (not always covered by ALL TABLES)
GRANT SELECT ON Vendor_Monthly_Rollup TO grader;

-- Grant usage on sequences (needed to read serial columns)
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO grader;

-- Ensure future tables are also readable
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON TABLES TO grader;

