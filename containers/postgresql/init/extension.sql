-- PostgreSQL init script for Odoo Multi-Tenant SaaS
-- Runs on first database initialization only

-- Create required extensions
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

-- Enable pg_stat_statements for query monitoring
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Optimized settings for Odoo
ALTER SYSTEM SET idle_in_transaction_session_timeout = '600s';
ALTER SYSTEM SET statement_timeout = '600s';

SELECT pg_reload_conf();
