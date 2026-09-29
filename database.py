"""
ENTERPRISE TIMECLOCK SAAS PRO - UNIFIED DATABASE & AUTH ENGINE (V5.0)
- Connection Pool cho PostgreSQL (ThreadedConnectionPool) & SQLite Fallback
- Migration Idempotent an toàn loại bỏ các cột cũ (IP, GPS, payment, v.v.)
- Băm mật khẩu chuẩn bcrypt với cơ chế tự động nâng cấp hash cũ
- Bảng sessions lưu token Bearer đã băm (SHA256) có hạn dùng
- Bảng kiosk_devices lưu token thiết bị Kiosk đã băm
- Giới hạn số lần đăng nhập sai theo IP và tài khoản (Rate Limiting)
"""

import os
import sqlite3
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from contextlib import contextmanager
import bcrypt

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "timeclock_saas.db")
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

# Chuẩn hóa tiền tố postgres:// sang postgresql:// cho psycopg2
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

IS_POSTGRES = bool(DATABASE_URL)

# Connection pool cho PostgreSQL
PG_POOL = None

def get_pg_pool():
    global PG_POOL
    if PG_POOL is None and IS_POSTGRES:
        import psycopg2.pool
        # Loại bỏ các tham số không tương thích nếu có (như &channel_binding=require)
        clean_url = DATABASE_URL.split("&channel_binding=")[0]
        PG_POOL = psycopg2.pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=clean_url
        )
    return PG_POOL

@contextmanager
def get_db_connection():
    """
    Context manager cung cấp kết nối DB an toàn:
    - Postgres: mượn kết nối từ ThreadedConnectionPool và hoàn trả lại pool khi xong
    - SQLite: mở kết nối cục bộ và đóng khi xong
    """
    if IS_POSTGRES:
        pool = get_pg_pool()
        conn = pool.getconn()
        try:
            yield conn
        finally:
            pool.putconn(conn)
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

def query(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    """Thực thi truy vấn SELECT và trả về danh sách dict"""
    with get_db_connection() as conn:
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

def query_one(sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
    """Thực thi truy vấn SELECT và trả về 1 dòng dict đầu tiên hoặc None"""
    rows = query(sql, params)
    return rows[0] if rows else None

def execute(sql: str, params: tuple = ()) -> int:
    """Thực thi INSERT / UPDATE / DELETE và commit"""
    with get_db_connection() as conn:
        if IS_POSTGRES:
            with conn.cursor() as cur:
                pg_sql = sql.replace("?", "%s")
                cur.execute(pg_sql, params)
                conn.commit()
                try:
                    return cur.lastrowid or cur.rowcount
                except Exception:
                    return cur.rowcount
        else:
            cur = conn.cursor()
            cur.execute(sql, params)
            conn.commit()
            return cur.lastrowid or cur.rowcount

def set_setting(key: str, value: str):
    """Lưu giá trị cấu hình hệ thống (Idempotent upsert)"""
    if IS_POSTGRES:
        sql = """
            INSERT INTO system_settings (key, value) VALUES (?, ?)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP
        """
    else:
        sql = "INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)"
    execute(sql, (key, value))

def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    """Đọc giá trị cấu hình hệ thống"""
    row = query_one("SELECT value FROM system_settings WHERE key = ?", (key,))
    return row["value"] if row else default

# =====================================================================
# 1. BĂM MẬT KHẨU (BCRYPT + TỰ ĐỘNG NÂNG CẤP HASH CŨ)
# =====================================================================
def hash_password(password: str) -> str:
    """Băm mật khẩu bằng thuật toán an toàn bcrypt (salt rounds 12)"""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

def verify_password(raw_password: str, stored_hash: str) -> Tuple[bool, bool]:
    """
    Xác thực mật khẩu và kiểm tra xem có cần nâng cấp hash không.
    Trả về: (is_valid, needs_upgrade)
    - Nếu khớp bcrypt: (True, False)
    - Nếu khớp SHA-256 cũ: (True, True) -> hệ thống sẽ cập nhật DB lên bcrypt
    - Nếu sai: (False, False)
    """
    if not stored_hash or not raw_password:
        return False, False

    # 1. Kiểm tra bcrypt hash chuẩn
    if stored_hash.startswith("$2b$") or stored_hash.startswith("$2a$") or stored_hash.startswith("$2y$"):
        try:
            valid = bcrypt.checkpw(raw_password.encode("utf-8"), stored_hash.encode("utf-8"))
            return valid, False
        except Exception:
            return False, False

    # 2. Kiểm tra SHA-256 legacy (các phiên bản cũ)
    legacy_hash_salt = hashlib.sha256(f"TIMECLOCK_SAAS_{raw_password}".encode("utf-8")).hexdigest()
    legacy_hash_plain = hashlib.sha256(raw_password.encode("utf-8")).hexdigest()
    if stored_hash in (legacy_hash_salt, legacy_hash_plain):
        return True, True  # Mật khẩu đúng nhưng cần nâng cấp lên bcrypt!

    return False, False

# =====================================================================
# 2. QUẢN LÝ SESSIONS & BEARER TOKEN BẰNG SHA-256
# =====================================================================
def create_session(user_type: str, tenant_code: Optional[str] = None, duration_hours: int = 24) -> str:
    """
    Tạo session token ngẫu nhiên, băm token trước khi lưu vào DB,
    trả về raw_token cho client dùng làm Bearer token.
    """
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    expires_at = (datetime.now() + timedelta(hours=duration_hours)).strftime("%Y-%m-%d %H:%M:%S")

    t_code = tenant_code.strip().lower() if tenant_code else None

    execute("""
        INSERT INTO sessions (token_hash, user_type, tenant_code, expires_at)
        VALUES (?, ?, ?, ?)
    """, (token_hash, user_type, t_code, expires_at))

    return raw_token

def get_valid_session(raw_token: str, expected_user_type: Optional[str] = None, tenant_code: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Xác thực Bearer token từ client:
    - Băm raw_token bằng SHA-256 và so khớp trong bảng sessions
    - Kiểm tra hạn dùng expires_at
    - Kiểm tra user_type và tenant_code (nếu có yêu cầu)
    """
    if not raw_token:
        return None

    token_hash = hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    row = query_one("""
        SELECT * FROM sessions
        WHERE token_hash = ? AND expires_at > ?
    """, (token_hash, now_str))

    if not row:
        return None

    if expected_user_type and row["user_type"] != expected_user_type:
        return None

    if tenant_code:
        sess_tenant = (row.get("tenant_code") or "").strip().lower()
        if sess_tenant != tenant_code.strip().lower():
            return None

    return row

def revoke_session(raw_token: str):
    """Hủy session khi đăng xuất"""
    if not raw_token:
        return
    token_hash = hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()
    execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))

# =====================================================================
# 3. QUẢN LÝ KIOSK DEVICE TOKEN
# =====================================================================
def register_kiosk_device(tenant_code: str, device_name: str = "Kiosk Terminal") -> str:
    """
    Cấp device_token cho thiết bị Kiosk sau khi kích hoạt thành công bằng mật khẩu Giám Đốc.
    Token được băm trước khi lưu vào bảng kiosk_devices.
    """
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    t_code = tenant_code.strip().lower()

    execute("""
        INSERT INTO kiosk_devices (tenant_code, device_token_hash, device_name, last_used_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
    """, (t_code, token_hash, device_name))

    return raw_token

def verify_kiosk_device(tenant_code: str, raw_device_token: str) -> bool:
    """
    Kiểm tra xem thiết bị Kiosk có token hợp lệ đã kích hoạt trong DB không
    """
    if not raw_device_token or not tenant_code:
        return False

    t_code = tenant_code.strip().lower()
    token_hash = hashlib.sha256(raw_device_token.strip().encode("utf-8")).hexdigest()

    row = query_one("""
        SELECT id FROM kiosk_devices
        WHERE tenant_code = ? AND device_token_hash = ?
    """, (t_code, token_hash))

    if row:
        # Cập nhật thời điểm sử dụng gần nhất
        execute("UPDATE kiosk_devices SET last_used_at = CURRENT_TIMESTAMP WHERE id = ?", (row["id"],))
        return True

    return False

# =====================================================================
# 4. GIỚI HẠN SỐ LẦN ĐĂNG NHẬP SAI (RATE LIMITING THEO IP & TÀI KHOẢN)
# =====================================================================
def check_rate_limit(key: str, max_attempts: int = 5, lock_minutes: int = 15) -> Tuple[bool, int]:
    """
    Kiểm tra xem IP hoặc tài khoản có đang bị khóa do nhập sai mật khẩu nhiều lần không.
    Trả về: (is_blocked, remaining_seconds)
    """
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    row = query_one("SELECT * FROM login_attempts WHERE rate_key = ?", (key,))
    if not row:
        return False, 0

    blocked_until_str = row.get("blocked_until")
    if blocked_until_str:
        try:
            blocked_until = datetime.strptime(str(blocked_until_str).split(".")[0], "%Y-%m-%d %H:%M:%S")
            if blocked_until > now:
                remaining_secs = int((blocked_until - now).total_seconds())
                return True, remaining_secs
        except Exception:
            pass

    return False, 0

def record_failed_login(key: str, max_attempts: int = 5, lock_minutes: int = 15) -> int:
    """
    Ghi nhận một lần nhập sai mật khẩu.
    Nếu vượt quá max_attempts, khóa tài khoản/IP trong lock_minutes phút.
    Trả về số lần sai hiện tại.
    """
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    row = query_one("SELECT * FROM login_attempts WHERE rate_key = ?", (key,))
    if not row:
        execute("""
            INSERT INTO login_attempts (rate_key, attempt_count, first_attempt_at, last_attempt_at, blocked_until)
            VALUES (?, 1, ?, ?, NULL)
        """, (key, now_str, now_str))
        return 1
    else:
        new_count = row["attempt_count"] + 1
        blocked_until = None
        if new_count >= max_attempts:
            blocked_until = (now + timedelta(minutes=lock_minutes)).strftime("%Y-%m-%d %H:%M:%S")

        execute("""
            UPDATE login_attempts
            SET attempt_count = ?, last_attempt_at = ?, blocked_until = ?
            WHERE rate_key = ?
        """, (new_count, now_str, blocked_until, key))
        return new_count

def clear_failed_logins(key: str):
    """Xóa bỏ lịch sử sai khi đăng nhập thành công"""
    execute("DELETE FROM login_attempts WHERE rate_key = ?", (key,))

# =====================================================================
# 5. MIGRATIONS IDEMPOTENT (DỌN DẸP CỘT & BẢNG CŨ AN TOÀN)
# =====================================================================
def run_migrations():
    """
    Chạy migration dọn dẹp các cột cũ không dùng:
    - enterprises: contact_email, contact_phone, max_terminals, last_payment_amount, last_payment_date
    - branches: allowed_ip_subnets, latitude, longitude, allowed_radius_meters, enforce_geofence, enforce_ip_lock
    - Xóa các bảng cũ: terminals, attendance_logs, payment_orders, email_configs, allowed_emails, managers
    Idempotent trên cả SQLite và PostgreSQL mà không gây mất dữ liệu hiện có.
    """
    cols_to_drop_ent = [
        "contact_email", "contact_phone", "max_terminals",
        "last_payment_amount", "last_payment_date"
    ]
    cols_to_drop_branch = [
        "allowed_ip_subnets", "latitude", "longitude",
        "allowed_radius_meters", "enforce_geofence", "enforce_ip_lock"
    ]
    tables_to_drop = [
        "terminals", "attendance_logs", "payment_orders",
        "email_configs", "allowed_emails", "managers"
    ]

    with get_db_connection() as conn:
        if IS_POSTGRES:
            with conn.cursor() as cur:
                for col in cols_to_drop_ent:
                    try:
                        cur.execute(f"ALTER TABLE enterprises DROP COLUMN IF EXISTS {col};")
                    except Exception:
                        conn.rollback()
                        continue
                for col in cols_to_drop_branch:
                    try:
                        cur.execute(f"ALTER TABLE branches DROP COLUMN IF EXISTS {col};")
                    except Exception:
                        conn.rollback()
                        continue
                for tbl in tables_to_drop:
                    try:
                        cur.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE;")
                    except Exception:
                        conn.rollback()
                        continue
                conn.commit()
        else:
            cur = conn.cursor()
            # SQLite: Kiểm tra xem bảng enterprises có tồn tại không
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='enterprises'")
            if cur.fetchone():
                cur.execute("PRAGMA table_info(enterprises)")
                ent_existing = [r[1] for r in cur.fetchall()]
                for col in cols_to_drop_ent:
                    if col in ent_existing:
                        try:
                            cur.execute(f"ALTER TABLE enterprises DROP COLUMN {col};")
                            conn.commit()
                        except Exception:
                            pass

            # SQLite: Kiểm tra bảng branches
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='branches'")
            if cur.fetchone():
                cur.execute("PRAGMA table_info(branches)")
                branch_existing = [r[1] for r in cur.fetchall()]
                for col in cols_to_drop_branch:
                    if col in branch_existing:
                        try:
                            cur.execute(f"ALTER TABLE branches DROP COLUMN {col};")
                            conn.commit()
                        except Exception:
                            pass

            # Xóa các bảng cũ nếu tồn tại
            for tbl in tables_to_drop:
                try:
                    cur.execute(f"DROP TABLE IF EXISTS {tbl};")
                    conn.commit()
                except Exception:
                    pass

# =====================================================================
# 6. KHỞI TẠO CƠ SỞ DỮ LIỆU ĐỒNG BỘ
# =====================================================================
def init_db():
    with get_db_connection() as conn:
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
                CREATE TABLE IF NOT EXISTS sessions (
                    id SERIAL PRIMARY KEY,
                    token_hash TEXT UNIQUE NOT NULL,
                    user_type TEXT NOT NULL,
                    tenant_code TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL
                );
                """)
                cur.execute("""
                CREATE TABLE IF NOT EXISTS kiosk_devices (
                    id SERIAL PRIMARY KEY,
                    tenant_code TEXT NOT NULL,
                    device_token_hash TEXT UNIQUE NOT NULL,
                    device_name TEXT DEFAULT 'Kiosk Terminal',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """)
                cur.execute("""
                CREATE TABLE IF NOT EXISTS login_attempts (
                    id SERIAL PRIMARY KEY,
                    rate_key TEXT UNIQUE NOT NULL,
                    attempt_count INTEGER DEFAULT 1,
                    first_attempt_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_attempt_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    blocked_until TIMESTAMP
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
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_hash TEXT UNIQUE NOT NULL,
                user_type TEXT NOT NULL,
                tenant_code TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL
            );
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS kiosk_devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_code TEXT NOT NULL,
                device_token_hash TEXT UNIQUE NOT NULL,
                device_name TEXT DEFAULT 'Kiosk Terminal',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS login_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rate_key TEXT UNIQUE NOT NULL,
                attempt_count INTEGER DEFAULT 1,
                first_attempt_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_attempt_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                blocked_until TIMESTAMP
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

    # Chạy dọn dẹp các cột và bảng cũ
    run_migrations()

    # Khởi tạo dữ liệu mẫu nếu DB trống
    row = query_one("SELECT COUNT(*) as count FROM enterprises")
    if not row or row["count"] == 0:
        expires = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d")

        # Enterprise 1: The Coffee House
        execute("""
            INSERT INTO enterprises (company_name, tenant_code, license_key, director_password_hash, status, plan_tier, expires_at)
            VALUES (?, ?, ?, ?, 'ACTIVE', 'ENTERPRISE', ?)
        """, (
            "THE COFFEE HOUSE - CHUỖI CÀ PHÊ",
            "coffee-house",
            "SAAS-COFFEE-HOUSE-DEMO",
            hash_password("giamdoc123"),
            expires
        ))

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
        """, (
            "HIGHLANDS COFFEE - CHI NHÁNH HÀ NỘI",
            "highlands",
            "SAAS-HIGHLANDS-DEMO",
            hash_password("giamdoc888"),
            expires
        ))

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

if __name__ == "__main__":
    init_db()
    print("Database Engine V5.0 initialized successfully. (Postgres:", IS_POSTGRES, ")")
