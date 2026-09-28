"""
ENTERPRISE TIMECLOCK SAAS PRO - DATABASE ENGINE (V3.9)
Hỗ trợ Mật Khẩu Mã Hóa Cho Từng Nhân Viên (Password Security Hash),
Bảo vệ chống lộ mật khẩu và phân quyền Whitelist.
"""

import sqlite3
import os
import hashlib
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "timeclock_saas.db")

def hash_password(password: str) -> str:
    """Mã hóa mật khẩu bằng SHA-256 kèm muối bảo mật (Salt)"""
    salt = "saas_salt_novalux_2026_xyz"
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Bảng Doanh Nghiệp
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS enterprises (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_name TEXT NOT NULL,
        contact_email TEXT,
        contact_phone TEXT,
        license_key TEXT UNIQUE NOT NULL,
        plan_tier TEXT NOT NULL DEFAULT 'PRO',
        status TEXT NOT NULL DEFAULT 'ACTIVE',
        max_terminals INTEGER NOT NULL DEFAULT 5,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP NOT NULL,
        last_payment_amount INTEGER DEFAULT 0,
        last_payment_date TIMESTAMP
    )
    """)

    # 2. Bảng Chi Nhánh
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS branches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        enterprise_id INTEGER NOT NULL,
        branch_name TEXT NOT NULL,
        branch_code TEXT UNIQUE NOT NULL,
        allowed_ip_subnets TEXT DEFAULT '*',
        latitude REAL DEFAULT 21.028511,
        longitude REAL DEFAULT 105.854444,
        allowed_radius_meters INTEGER DEFAULT 150,
        enforce_geofence INTEGER DEFAULT 0,
        enforce_ip_lock INTEGER DEFAULT 0,
        google_form_work_in TEXT DEFAULT '',
        google_form_work_out TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (enterprise_id) REFERENCES enterprises (id)
    )
    """)

    # 3. BẢNG DANH SÁCH EMAIL + MẬT KHẨU NHÂN VIÊN
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS allowed_emails (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        enterprise_id INTEGER DEFAULT 1,
        email TEXT UNIQUE NOT NULL,
        employee_name TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT DEFAULT 'NHÂN VIÊN',
        is_active INTEGER DEFAULT 1,
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login TIMESTAMP
    )
    """)

    # Tự động kiểm tra và thêm cột password_hash nếu database cũ chưa có
    cursor.execute("PRAGMA table_info(allowed_emails)")
    cols = [r["name"] for r in cursor.fetchall()]
    if "password_hash" not in cols:
        cursor.execute("ALTER TABLE allowed_emails ADD COLUMN password_hash TEXT DEFAULT ''")

    # Cập nhật mật khẩu mặc định (123456) cho các tài khoản mẫu
    default_hash = hash_password("123456")
    cursor.execute("UPDATE allowed_emails SET password_hash = ? WHERE password_hash IS NULL OR password_hash = ''", (default_hash,))

    # Nạp tài khoản mẫu nếu chưa có
    cursor.execute("SELECT COUNT(*) as count FROM allowed_emails")
    if cursor.fetchone()["count"] == 0:
        demo_users = [
            ("quanly.cuahang@gmail.com", "Nguyễn Văn Quản Lý", hash_password("quanly888"), "QUẢN LÝ CA"),
            ("nhanvien01@gmail.com", "Trần Thị Thu Ngân", hash_password("123456"), "THU NGÂN"),
            ("nhanvien02@gmail.com", "Lê Hoàng Phục Vụ", hash_password("123456"), "PHỤC VỤ")
        ]
        cursor.executemany("""
            INSERT INTO allowed_emails (email, employee_name, password_hash, role)
            VALUES (?, ?, ?, ?)
        """, demo_users)

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database SQLite V3.9 with password security initialized.")
