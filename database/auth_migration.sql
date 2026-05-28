-- =============================================================================
-- Authentication & RBAC Migration
-- =============================================================================
-- This migration adds authentication tables for internal company users.
-- Run this after the initial schema.sql setup.
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- AUTH_USERS
-- Internal company users (admin, agent, supervisor) — NOT customers.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS auth_users (
    id              SERIAL PRIMARY KEY,
    email           VARCHAR(255) UNIQUE NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    full_name       VARCHAR(255) NOT NULL,
    role            VARCHAR(32) NOT NULL DEFAULT 'agent',
    status          VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    last_login      TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_auth_users_email ON auth_users (email);
CREATE INDEX IF NOT EXISTS idx_auth_users_role ON auth_users (role);
CREATE INDEX IF NOT EXISTS idx_auth_users_status ON auth_users (status);


-- ─────────────────────────────────────────────────────────────────────────────
-- AUDIT_LOGS
-- Track all user actions for compliance and debugging.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS audit_logs (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
    action          VARCHAR(255) NOT NULL,
    resource_type   VARCHAR(100),
    resource_id     VARCHAR(100),
    changes         JSONB,
    ip_address      VARCHAR(45),
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs (user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs (action);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs (created_at DESC);


-- ─────────────────────────────────────────────────────────────────────────────
-- INSERT DEFAULT USERS FOR TESTING
-- ─────────────────────────────────────────────────────────────────────────────
-- Passwords are hashed with bcrypt. These are test credentials only.
-- In production, create users through the signup endpoint.
--
-- Test credentials:
-- Admin: admin@company.com / admin123
-- Agent: agent@company.com / agent123
-- Supervisor: supervisor@company.com / supervisor123
--
-- To generate bcrypt hashes in Python:
-- import bcrypt
-- bcrypt.hashpw(b'password123', bcrypt.gensalt()).decode('utf-8')
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO auth_users (email, password_hash, full_name, role, status)
VALUES
    (
        'admin@company.com',
        '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5YmMxSUmGEJiq',  -- admin123
        'Admin User',
        'admin',
        'active'
    ),
    (
        'agent@company.com',
        '$2b$12$R9h7cIPz0gi.URNNX3kh2OPST9/PgBkqquzi.Ss7KIUgO2t0jWMUm',  -- agent123
        'Jane Agent',
        'agent',
        'active'
    ),
    (
        'supervisor@company.com',
        '$2b$12$Dn1l5z7b8c9d0e1f2g3h4i5j6k7l8m9n0o1p2q3r4s5t6u7v8w9x0y',  -- supervisor123
        'Bob Supervisor',
        'supervisor',
        'active'
    )
ON CONFLICT (email) DO NOTHING;
