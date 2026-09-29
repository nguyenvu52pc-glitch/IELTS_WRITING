"""
ENTERPRISE TIMECLOCK SAAS PRO - UNIFIED DATABASE ENGINE (V4.1)
Hỗ trợ lưu trữ vĩnh viễn trên Đám Mây:
1. Nếu có biến môi trường DATABASE_URL -> Kết nối PostgreSQL (Supabase / Neon / Render Postgres)
2. Nếu không có DATABASE_URL -> Tự động dùng SQLite timeclock_saas.db cục bộ
"""

import os
import hashlib
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

DATABASE_URL = os.environ.get("DATABASE_URL")
# Render / Heroku Postgres URL fix (postgres:// -> postgresql://)
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

IS_POSTGRES = bool(DATABASE_URL)
DB_PATH = os.path.join(os.path.dirname(__file__), "timeclock_saas.db")

def hash_password(password: str) -> str:
    salt = "saas_salt_novalux_2026_xyz"
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()

def get_raw_connection():
    if IS_POSTGRES:
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    else:
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

def query(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    conn = get_raw_connection()
    try:
        if IS_POSTGRES:
            import psycopg2.extras
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql.replace("?", "%s"), params)
                rows = cur.fetchall()
                return [dict(r) for r in rows]
        else:
            cur = conn.cursor()
            cur.execute(sql, params)
            rows = cur.fetchall()
            return [dict(r) for r in rows]
    finally:
        conn.close()

def query_one(sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
    rows = query(sql, params)
    return rows[0] if rows else None

def execute(sql: str, params: tuple = ()) -> int:
    conn = get_raw_connection()
    try:
        if IS_POSTGRES:
            with conn.cursor() as cur:
                # If insert, try to return id
                pg_sql = sql.replace("?", "%s")
                cur.execute(pg_sql, params)
                conn.commit()
                try:
                    return cur.lastrowid or 1
                except Exception:
                    return 1
        else:
            cur = conn.cursor()
            cur.execute(sql, params)
            conn.commit()
            return cur.lastrowid or cur.rowcount
    finally:
        conn.close()

def set_setting(key: str, value: str):
    if IS_POSTGRES:
        sql = """
            INSERT INTO system_settings (key, value) VALUES (?, ?)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP
        """
    else:
        sql = "INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)"
    execute(sql, (key, value))

def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    row = query_one("SELECT value FROM system_settings WHERE key = ?", (key,))
    return row["value"] if row else default

def init_db():
    conn = get_raw_connection()
    try:
        if IS_POSTGRES:
            with conn.cursor() as cur:
                cur.execute("""
                CREATE TABLE IF NOT EXISTS enterprises (
                    id SERIAL PRIMARY KEY,
                    company_name TEXT NOT NULL,
                    tenant_code TEXT UNIQUE NOT NULL,
                    license_key TEXT UNIQUE NOT NULL,
                    director_password_hash TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'ACTIVE',
                    plan_tier TEXT NOT NULL DEFAULT 'ENTERPRISE',
                    expires_at TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """)
                cur.execute("""
                CREATE TABLE IF NOT EXISTS branches (
                    id SERIAL PRIMARY KEY,
                    enterprise_id INTEGER NOT NULL REFERENCES enterprises (id) ON DELETE CASCADE,
                    branch_name TEXT NOT NULL,
                    branch_code TEXT,
                    google_form_work_in TEXT DEFAULT '',
                    google_form_work_out TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """)
                cur.execute("""
                CREATE TABLE IF NOT EXISTS system_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """)
                conn.commit()
        else:
            cur = conn.cursor()
            cur.execute("""
            CREATE TABLE IF NOT EXISTS enterprises (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT NOT NULL,
                tenant_code TEXT UNIQUE NOT NULL,
                license_key TEXT UNIQUE NOT NULL,
                director_password_hash TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                plan_tier TEXT NOT NULL DEFAULT 'ENTERPRISE',
                expires_at TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS branches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                enterprise_id INTEGER NOT NULL,
                branch_name TEXT NOT NULL,
                branch_code TEXT,
                google_form_work_in TEXT DEFAULT '',
                google_form_work_out TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (enterprise_id) REFERENCES enterprises (id) ON DELETE CASCADE
            );
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS system_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            conn.commit()

        # Seed data if empty
        row = query_one("SELECT COUNT(*) as count FROM enterprises")
        if not row or row["count"] == 0:
            expires = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d")
            
            # Enterprise 1: The Coffee House
            execute("""
                INSERT INTO enterprises (company_name, tenant_code, license_key, director_password_hash, status, plan_tier, expires_at)
                VALUES (?, ?, ?, ?, 'ACTIVE', 'ENTERPRISE', ?)
            """, ("THE COFFEE HOUSE - CHUỖI CÀ PHÊ", "coffee-house", "SAAS-COFFEE-HOUSE-DEMO", hash_password("giamdoc123"), expires))
            
            ent1 = query_one("SELECT id FROM enterprises WHERE tenant_code = 'coffee-house'")
            execute("""
                INSERT INTO branches (enterprise_id, branch_name, branch_code, google_form_work_in, google_form_work_out)
                VALUES (?, ?, ?, ?, ?)
            """, (
                ent1["id"],
                "THE COFFEE HOUSE - CHI NHÁNH 01",
                "Cổng Điểm Danh Chi Nhánh 1",
                "https://docs.google.com/forms/d/e/1FAIpQLScJ_v5aA0mD6q8_demo_work_in/viewform?embedded=true",
                "https://docs.google.com/forms/d/e/1FAIpQLSdX_w7bB1nE7r9_demo_work_out/viewform?embedded=true"
            ))

            # Enterprise 2: Highlands Coffee
            execute("""
                INSERT INTO enterprises (company_name, tenant_code, license_key, director_password_hash, status, plan_tier, expires_at)
                VALUES (?, ?, ?, ?, 'ACTIVE', 'PRO', ?)
            """, ("HIGHLANDS COFFEE - CHI NHÁNH HÀ NỘI", "highlands", "SAAS-HIGHLANDS-DEMO", hash_password("giamdoc888"), expires))

            ent2 = query_one("SELECT id FROM enterprises WHERE tenant_code = 'highlands'")
            execute("""
                INSERT INTO branches (enterprise_id, branch_name, branch_code, google_form_work_in, google_form_work_out)
                VALUES (?, ?, ?, ?, ?)
            """, (
                ent2["id"],
                "HIGHLANDS COFFEE - TRÀNG TIỀN",
                "Cổng Điểm Danh Cơ Sở 2",
                "https://docs.google.com/forms/d/e/1FAIpQLScJ_v5aA0mD6q8_demo_work_in/viewform?embedded=true",
                "https://docs.google.com/forms/d/e/1FAIpQLSdX_w7bB1nE7r9_demo_work_out/viewform?embedded=true"
            ))

    finally:
        conn.close()

if __name__ == "__main__":
    init_db()
    print("Database Engine initialized successfully. (Postgres:", IS_POSTGRES, ")")
