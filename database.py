"""
ENTERPRISE TIMECLOCK SAAS PRO - MULTI-TENANT DATABASE ENGINE (V4.0)
Hỗ trợ Kiến Trúc Đa Khách Hàng 3 Cấp:
1. Super Admin: Quản lý bản quyền (Bật/Tắt kích hoạt các Công Ty Khách Hàng)
2. Giám Đốc (Director): Tự cài đặt tên cơ sở, link Google Form, và cấp tài khoản Quản Lý
3. Quản Lý (Manager): Đăng nhập mở ca cho Kiosk để nhân viên chấm công
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

    # 1. BẢNG CÔNG TY / DOANH NGHIỆP (TENANTS)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS enterprises (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_name TEXT NOT NULL,
        tenant_code TEXT UNIQUE NOT NULL,
        director_password_hash TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'ACTIVE',
        plan_tier TEXT NOT NULL DEFAULT 'ENTERPRISE',
        expires_at TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Kiểm tra cột director_password_hash và tenant_code nếu bảng đã tồn tại từ trước
    cursor.execute("PRAGMA table_info(enterprises)")
    ent_cols = [r["name"] for r in cursor.fetchall()]
    if "tenant_code" not in ent_cols:
        cursor.execute("ALTER TABLE enterprises ADD COLUMN tenant_code TEXT DEFAULT 'default'")
    if "director_password_hash" not in ent_cols:
        cursor.execute("ALTER TABLE enterprises ADD COLUMN director_password_hash TEXT DEFAULT ''")

    # 2. BẢNG CHI NHÁNH & CẤU HÌNH GOOGLE FORM
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS branches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        enterprise_id INTEGER NOT NULL,
        branch_name TEXT NOT NULL,
        branch_code TEXT UNIQUE,
        google_form_work_in TEXT DEFAULT '',
        google_form_work_out TEXT DEFAULT '',
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (enterprise_id) REFERENCES enterprises (id)
    )
    """)

    # 3. BẢNG TÀI KHOẢN QUẢN LÝ (STORE MANAGERS) DO GIÁM ĐỐC CẤP
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS managers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        enterprise_id INTEGER NOT NULL,
        username TEXT NOT NULL,
        full_name TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT DEFAULT 'CỬA HÀNG TRƯỞNG',
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login TIMESTAMP,
        FOREIGN KEY (enterprise_id) REFERENCES enterprises (id),
        UNIQUE (enterprise_id, username)
    )
    """)

    # 4. TẠO DỮ LIỆU KHỞI TẠO MẪU (NẾU CHƯA CÓ)
    cursor.execute("SELECT COUNT(*) as count FROM enterprises")
    if cursor.fetchone()["count"] == 0:
        expires = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d")
        
        # Công ty 1: The Coffee House
        cursor.execute("""
        INSERT INTO enterprises (id, company_name, tenant_code, director_password_hash, status, plan_tier, expires_at)
        VALUES (1, 'THE COFFEE HOUSE - CHUỖI CÀ PHÊ', 'coffee-house', ?, 'ACTIVE', 'ENTERPRISE', ?)
        """, (hash_password("giamdoc123"), expires))

        cursor.execute("""
        INSERT INTO branches (id, enterprise_id, branch_name, branch_code, google_form_work_in, google_form_work_out, is_active)
        VALUES (1, 1, 'THE COFFEE HOUSE - CHI NHÁNH 01', 'Cổng Điểm Danh Chi Nhánh 1', 
                'https://docs.google.com/forms/d/e/1FAIpQLScJ_v5aA0mD6q8_demo_work_in/viewform?embedded=true',
                'https://docs.google.com/forms/d/e/1FAIpQLSdX_w7bB1nE7r9_demo_work_out/viewform?embedded=true', 1)
        """)

        cursor.execute("""
        INSERT INTO managers (enterprise_id, username, full_name, password_hash, role, is_active)
        VALUES (1, 'quanly01', 'Trần Văn An', ?, 'CỬA HÀNG TRƯỞNG', 1)
        """, (hash_password("quanly123"),))

        # Công ty 2: Highlands Coffee (để Super Admin test bật/tắt)
        cursor.execute("""
        INSERT INTO enterprises (id, company_name, tenant_code, director_password_hash, status, plan_tier, expires_at)
        VALUES (2, 'HIGHLANDS COFFEE - CHI NHÁNH MIỀN TRUNG', 'highlands', ?, 'ACTIVE', 'PRO', ?)
        """, (hash_password("giamdoc888"), expires))

        cursor.execute("""
        INSERT INTO branches (id, enterprise_id, branch_name, branch_code, google_form_work_in, google_form_work_out, is_active)
        VALUES (2, 2, 'HIGHLANDS COFFEE - TRÀNG TIỀN', 'Cổng Điểm Danh Cơ Sở 2',
                'https://docs.google.com/forms/d/e/1FAIpQLScJ_v5aA0mD6q8_demo_work_in/viewform?embedded=true',
                'https://docs.google.com/forms/d/e/1FAIpQLSdX_w7bB1nE7r9_demo_work_out/viewform?embedded=true', 1)
        """)

        cursor.execute("""
        INSERT INTO managers (enterprise_id, username, full_name, password_hash, role, is_active)
        VALUES (2, 'quanly.hn', 'Nguyễn Thị Thu Hà', ?, 'QUẢN LÝ CA', 1)
        """, (hash_password("quanly888"),))

    else:
        # Đảm bảo enterprise 1 có mật khẩu giám đốc
        cursor.execute("SELECT director_password_hash FROM enterprises WHERE id = 1")
        row = cursor.fetchone()
        if not row or not row["director_password_hash"]:
            cursor.execute("UPDATE enterprises SET director_password_hash = ?, tenant_code = 'coffee-house' WHERE id = 1", (hash_password("giamdoc123"),))

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database SQLite V4.0 initialized successfully.")
