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
import time
import threading
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from contextlib import contextmanager
import bcrypt

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("TIMECLOCK_DB") or os.path.join(BASE_DIR, "timeclock_saas.db")
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

# Chuẩn hóa tiền tố postgres:// sang postgresql:// cho psycopg2
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

IS_POSTGRES = bool(DATABASE_URL)

# Connection pool cho PostgreSQL
PG_POOL = None
_PG_LOCK = threading.Lock()

def get_pg_pool():
    global PG_POOL
    if PG_POOL is None and IS_POSTGRES:
        with _PG_LOCK:
            if PG_POOL is None:
                import psycopg2.pool
                # Loại bỏ các tham số không tương thích nếu có (như &channel_binding=require)
                clean_url = DATABASE_URL.split("&channel_binding=")[0]
                PG_POOL = psycopg2.pool.ThreadedConnectionPool(
                    1, 5, dsn=clean_url,
                    connect_timeout=10,
                    keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=3,
                )
    return PG_POOL

def _is_conn_error(e: Exception) -> bool:
    import psycopg2
    return isinstance(e, (psycopg2.OperationalError, psycopg2.InterfaceError))

@contextmanager
def get_db_connection():
    """
    - Postgres: mượn kết nối từ pool; nếu kết nối bị đứt thì đóng hẳn thay vì trả lại pool
    - SQLite: mở kết nối cục bộ và đóng khi xong
    """
    if IS_POSTGRES:
        pool = get_pg_pool()
        conn = pool.getconn()
        bad = False
        try:
            yield conn
        except Exception as e:
            bad = _is_conn_error(e)
            raise
        finally:
            pool.putconn(conn, close=bad)
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

def _pg_run(work):
    """
    Chạy work(conn) trên Postgres. Nếu kết nối trong pool đã chết (ví dụ Neon tự ngủ đông)
    thì lấy kết nối mới và thử lại đúng 1 lần, người dùng không thấy lỗi.
    """
    for attempt in (0, 1):
        try:
            with get_db_connection() as conn:
                return work(conn)
        except Exception as e:
            if attempt == 0 and _is_conn_error(e):
                continue
            raise

def query(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    """SELECT -> danh sách dict. Postgres dùng autocommit nên tiết kiệm 2 vòng mạng BEGIN/ROLLBACK."""
    if IS_POSTGRES:
        import psycopg2.extras
        def work(conn):
            conn.autocommit = True
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(sql.replace("?", "%s"), params)
                    return [dict(r) for r in cur.fetchall()]
            finally:
                conn.autocommit = False
        return _pg_run(work)
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]

def query_one(sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
    rows = query(sql, params)
    return rows[0] if rows else None

def execute(sql: str, params: tuple = ()) -> int:
    """INSERT / UPDATE / DELETE 1 lệnh. Postgres dùng autocommit (không cần BEGIN/COMMIT riêng)."""
    if IS_POSTGRES:
        def work(conn):
            conn.autocommit = True
            try:
                with conn.cursor() as cur:
                    cur.execute(sql.replace("?", "%s"), params)
                    return cur.rowcount
            finally:
                conn.autocommit = False
        return _pg_run(work)
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
        return cur.lastrowid or cur.rowcount

def transaction(statements: List[Tuple[str, tuple]]):
    """Chạy nhiều lệnh trong 1 giao dịch: hoặc tất cả được lưu, hoặc không lệnh nào."""
    if IS_POSTGRES:
        def work(conn):
            with conn.cursor() as cur:
                for sql, params in statements:
                    cur.execute(sql.replace("?", "%s"), params)
            conn.commit()
        _pg_run(work)
    else:
        with get_db_connection() as conn:
            try:
                cur = conn.cursor()
                for sql, params in statements:
                    cur.execute(sql, params)
                conn.commit()
            except Exception:
                conn.rollback()
                raise

# Bộ nhớ đệm ngắn hạn trong RAM (server chạy 1 tiến trình nên đủ dùng)
_CACHE: Dict[str, Any] = {}

def cache_get(key: str):
    item = _CACHE.get(key)
    if item and item[0] > time.monotonic():
        return item[1]
    _CACHE.pop(key, None)
    return None

def cache_set(key: str, value: Any, ttl: float):
    if len(_CACHE) > 2000:
        _CACHE.clear()
    _CACHE[key] = (time.monotonic() + ttl, value)

def cache_clear():
    _CACHE.clear()

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
BCRYPT_ROUNDS = 10  # ~75ms/lần. 12 vòng ~300ms (chậm gấp 4, nhất là trên Render Free)

def hash_password(password: str) -> str:
    """Băm mật khẩu bằng bcrypt"""
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
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
            # Hash cũ cost cao (12) -> băm lại 1 lần với cost hiện tại để các lần đăng nhập sau nhanh hơn
            return valid, valid and int(stored_hash.split("$")[2]) > BCRYPT_ROUNDS
        except Exception:
            return False, False

    # 2. Kiểm tra SHA-256 legacy (các phiên bản cũ)
    legacy_hash_salt = hashlib.sha256(f"TIMECLOCK_SAAS_{raw_password}".encode("utf-8")).hexdigest()
    legacy_hash_plain = hashlib.sha256(raw_password.encode("utf-8")).hexdigest()
    # Bản V4 cũ băm bằng salt cố định này (đang nằm trong DB Postgres của các bản đã triển khai)
    legacy_hash_v4 = hashlib.sha256(("saas_salt_novalux_2026_xyz" + raw_password).encode("utf-8")).hexdigest()
    if stored_hash in (legacy_hash_salt, legacy_hash_plain, legacy_hash_v4):
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
    """Kiểm tra token thiết bị Kiosk. Kết quả đúng được nhớ 60 giây để không phải hỏi DB mỗi lần."""
    if not raw_device_token or not tenant_code:
        return False

    t_code = tenant_code.strip().lower()
    token_hash = hashlib.sha256(raw_device_token.strip().encode("utf-8")).hexdigest()
    ck = f"dev:{t_code}:{token_hash}"
    if cache_get(ck):
        return True

    row = query_one("SELECT id FROM kiosk_devices WHERE tenant_code = ? AND device_token_hash = ?", (t_code, token_hash))
    if row:
        cache_set(ck, True, 60)
        return True
    return False

# =====================================================================
# 4. GIỚI HẠN SỐ LẦN ĐĂNG NHẬP SAI (RATE LIMITING THEO IP & TÀI KHOẢN)
# =====================================================================
_FAILS: Dict[str, list] = {}  # key -> [số lần sai, khóa đến (epoch), lần sai gần nhất]
_FAILS_LOCK = threading.Lock()

def check_rate_limit(key: str, max_attempts: int = 5, lock_minutes: int = 15) -> Tuple[bool, int]:
    """Trả về (đang bị khóa?, số giây còn lại). Lưu trong RAM nên không tốn truy vấn DB."""
    rec = _FAILS.get(key)
    now = time.time()
    if rec and rec[1] > now:
        return True, int(rec[1] - now)
    return False, 0

def record_failed_login(key: str, max_attempts: int = 5, lock_minutes: int = 15) -> int:
    """Ghi 1 lần sai; đủ max_attempts thì khóa lock_minutes phút. Lần sai cũ quá hạn khóa sẽ được đếm lại từ đầu."""
    now = time.time()
    with _FAILS_LOCK:
        if len(_FAILS) > 5000:
            _FAILS.clear()
        rec = _FAILS.get(key)
        if not rec or now - rec[2] > lock_minutes * 60:
            rec = [0, 0, now]
        rec[0] += 1
        rec[2] = now
        if rec[0] >= max_attempts:
            rec[1] = now + lock_minutes * 60
        _FAILS[key] = rec
        return rec[0]

def clear_failed_logins(key: str):
    """Xóa lịch sử sai khi đăng nhập thành công"""
    _FAILS.pop(key, None)

def cleanup_expired_sessions():
    execute("DELETE FROM sessions WHERE expires_at < ?", (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))

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

    # Đã migrate rồi thì bỏ qua: tránh ~17 lệnh ALTER/DROP lên Postgres ở MỖI lần khởi động server
    if get_setting("migrations_v5_done") == "1":
        return

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

    _fix_legacy_branches()
    set_setting("migrations_v5_done", "1")

def _fix_legacy_branches():
    """
    DB SQLite cũ có branch_code UNIQUE -> tạo công ty thứ 2 trở đi bị lỗi.
    Dựng lại bảng branches không có ràng buộc đó, và xóa chi nhánh mồ côi (công ty đã bị xóa).
    """
    if IS_POSTGRES:
        return
    with get_db_connection() as conn:
        cur = conn.cursor()
        has_unique = False
        for idx in cur.execute("PRAGMA index_list(branches)").fetchall():
            if idx[2]:
                cols = [r[2] for r in conn.execute(f"PRAGMA index_info('{idx[1]}')").fetchall()]
                if cols == ["branch_code"]:
                    has_unique = True
        cur.execute("DELETE FROM branches WHERE enterprise_id NOT IN (SELECT id FROM enterprises)")
        if has_unique:
            existing = [r[1] for r in cur.execute("PRAGMA table_info(branches)").fetchall()]
            keep = [c for c in ("id", "enterprise_id", "branch_name", "branch_code",
                                "google_form_work_in", "google_form_work_out", "created_at") if c in existing]
            cols = ", ".join(keep)
            cur.execute("ALTER TABLE branches RENAME TO branches_old")
            cur.execute("""
                CREATE TABLE branches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    enterprise_id INTEGER NOT NULL,
                    branch_name TEXT NOT NULL,
                    branch_code TEXT,
                    google_form_work_in TEXT DEFAULT '',
                    google_form_work_out TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (enterprise_id) REFERENCES enterprises (id) ON DELETE CASCADE
                )
            """)
            cur.execute(f"INSERT INTO branches ({cols}) SELECT {cols} FROM branches_old")
            cur.execute("DROP TABLE branches_old")
        conn.commit()

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
