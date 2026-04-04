-- Script SQL để tạo các user PostgreSQL cho Odoo
-- File này sẽ được thực thi tự động khi khởi tạo PostgreSQL container

\echo 'Creating PostgreSQL users for Odoo versions...'

-- Tạo function để kiểm tra và tạo user
DO $$
BEGIN
    -- User cho Odoo 15
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'odoo15') THEN
        CREATE USER odoo15 WITH CREATEDB PASSWORD 'odoo15@pwd';
        RAISE NOTICE 'User odoo15 created successfully';
    ELSE
        RAISE NOTICE 'User odoo15 already exists';
    END IF;

    -- User cho Odoo 16
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'odoo16') THEN
        CREATE USER odoo16 WITH CREATEDB PASSWORD 'odoo16@pwd';
        RAISE NOTICE 'User odoo16 created successfully';
    ELSE
        RAISE NOTICE 'User odoo16 already exists';
    END IF;

    -- User cho Odoo 17
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'odoo17') THEN
        CREATE USER odoo17 WITH CREATEDB PASSWORD 'odoo17@pwd';
        RAISE NOTICE 'User odoo17 created successfully';
    ELSE
        RAISE NOTICE 'User odoo17 already exists';
    END IF;

    -- User cho Odoo 18
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'odoo18') THEN
        CREATE USER odoo18 WITH CREATEDB PASSWORD 'odoo18@pwd';
        RAISE NOTICE 'User odoo18 created successfully';
    ELSE
        RAISE NOTICE 'User odoo18 already exists';
    END IF;
END
$$;

-- Hiển thị danh sách users đã tạo
\echo 'Current PostgreSQL users for Odoo:'
SELECT rolname, rolcanlogin, rolcreatedb, rolcreaterole 
FROM pg_roles 
WHERE rolname LIKE 'odoo%' 
ORDER BY rolname;

\echo 'PostgreSQL users initialization completed!'
