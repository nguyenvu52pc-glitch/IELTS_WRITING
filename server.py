"""
ENTERPRISE TIMECLOCK SAAS PRO - SECURE BACKEND SERVER (V5.0)
- Xác thực Bearer Token lưu trong DB (băm SHA-256) cho toàn bộ API quản trị
- Rate Limiting chống Brute-Force theo IP và Tài khoản
- Băm mật khẩu bcrypt, tự động nâng cấp hash cũ khi đăng nhập
- Kiosk Device Token: Chỉ trả link Google Form khi thiết bị đã kích hoạt
- Kiểm tra hạn dùng bản quyền (expires_at), coi hết hạn như bị khóa
- Chuẩn hóa link Google Form sang /viewform?embedded=true
- Chuẩn hóa tenant_code về chữ thường
"""

import os
import re
import uuid
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import FastAPI, Request, HTTPException, Depends, Header, Query
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

import database

# Khởi tạo DB & Migration
database.init_db()
database.cleanup_expired_sessions()

app = FastAPI(title="Enterprise TimeClock Multi-Tenant SaaS", version="5.0.0")

app.add_middleware(GZipMiddleware, minimum_size=500)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

security_bearer = HTTPBearer(auto_error=False)

# =====================================================================
# SCHEMAS
# =====================================================================
class SuperAdminLoginRequest(BaseModel):
    password: str

class SuperAdminChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

class CreateEnterpriseRequest(BaseModel):
    company_name: str
    tenant_code: str
    director_password: str
    plan_tier: Optional[str] = "ENTERPRISE"
    days_valid: Optional[int] = 365

class UpdateSubscriptionRequest(BaseModel):
    plan_tier: Optional[str] = "ENTERPRISE"
    expires_at: Optional[str] = None

class KioskActivateRequest(BaseModel):
    tenant_code: str
    password: str

class DirectorLoginRequest(BaseModel):
    tenant_code: str
    password: str

class DirectorUpdateConfigRequest(BaseModel):
    tenant_code: str
    company_name: str
    branch_name: str
    branch_code: Optional[str] = ""
    work_in_url: Optional[str] = ""
    work_out_url: Optional[str] = ""

class DirectorChangePasswordRequest(BaseModel):
    tenant_code: str
    old_password: str
    new_password: str

# =====================================================================
# HELPER FUNCTIONS
# =====================================================================
def get_client_ip(request: Request) -> str:
    """Lấy IP thực tế của client (hỗ trợ reverse proxy như Render / Cloudflare)"""
    x_forwarded = request.headers.get("x-forwarded-for")
    if x_forwarded:
        return x_forwarded.split(",")[-1].strip()
    if request.client:
        return request.client.host
    return "127.0.0.1"

def find_static_file(filename: str):
    for candidate in [
        os.path.join(STATIC_DIR, filename),
        os.path.join(BASE_DIR, filename),
    ]:
        if os.path.exists(candidate):
            return candidate
    return None

def normalize_google_form_url(url: str) -> str:
    """
    Chuẩn hóa link Google Form về dạng /viewform?embedded=true
    Báo lỗi rõ ràng nếu không phải link Google Form
    """
    if not url or not url.strip():
        return ""
    u = url.strip()

    # Kiểm tra domain Google Form
    if "docs.google.com/forms" not in u and "forms.gle" not in u:
        raise HTTPException(
            status_code=400,
            detail="Đường dẫn không hợp lệ! Vui lòng nhập link Google Form (dạng docs.google.com/forms/... hoặc forms.gle/...)"
        )

    # Nếu là dạng docs.google.com/forms
    if "docs.google.com/forms" in u:
        m = re.match(r"^(https?://docs\.google\.com/forms/d/(?:e/)?[a-zA-Z0-9_\-]+)", u)
        if m:
            return f"{m.group(1)}/viewform?embedded=true"
        if "?" in u:
            u = u.split("?")[0]
        u = re.sub(r"/(edit|responses|prefill)$", "", u)
        if not u.endswith("/viewform"):
            u = f"{u}/viewform"
        return f"{u}?embedded=true"

    # Dạng forms.gle ngắn
    return u

def require_same_tenant(session: dict, t_code: str):
    """Token Giám Đốc chỉ được thao tác trên đúng cơ sở của mình (kể cả khi tenant nằm trong body)"""
    if (session.get("tenant_code") or "") != t_code:
        raise HTTPException(status_code=403, detail="Bạn không có quyền thao tác trên cơ sở này!")

# =====================================================================
# DEPENDENCIES: BEARER TOKEN AUTHENTICATION
# =====================================================================
def get_current_super_admin(auth: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer)):
    """
    Xác thực Bearer token cho toàn bộ API Super Admin
    Token phải tồn tại trong bảng sessions và chưa hết hạn
    """
    if not auth or not auth.credentials:
        raise HTTPException(
            status_code=401,
            detail="Yêu cầu Bearer token xác thực Super Admin! Vui lòng đăng nhập lại."
        )
    session = database.get_valid_session(auth.credentials, expected_user_type="SUPER_ADMIN")
    if not session:
        raise HTTPException(
            status_code=401,
            detail="Bearer token không hợp lệ hoặc đã hết hạn! Vui lòng đăng nhập lại."
        )
    return session

def get_current_director(
    request: Request,
    auth: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer)
):
    """
    Xác thực Bearer token cho toàn bộ API Giám Đốc
    Token phải thuộc đúng tenant_code đang truy vấn
    """
    if not auth or not auth.credentials:
        raise HTTPException(
            status_code=401,
            detail="Yêu cầu Bearer token xác thực Giám Đốc! Vui lòng đăng nhập lại."
        )

    # Lấy tenant từ query hoặc body
    tenant = request.query_params.get("tenant")
    session = database.get_valid_session(auth.credentials, expected_user_type="DIRECTOR", tenant_code=tenant)
    if not session:
        raise HTTPException(
            status_code=401,
            detail="Bearer token Giám Đốc không hợp lệ hoặc không có quyền truy cập cơ sở này!"
        )
    return session

# =====================================================================
# 1. API SUPER ADMIN (QUẢN TRỊ BẢN QUYỀN TOÀN HỆ THỐNG)
# =====================================================================
@app.post("/api/super-admin/login")
def super_admin_login(req: SuperAdminLoginRequest, request: Request):
    """Đăng nhập Super Admin, kiểm tra rate limit, băm mật khẩu và cấp Bearer token"""
    client_ip = get_client_ip(request)
    ip_key = f"ip:{client_ip}"
    acc_key = "acc:super_admin"

    # 1. Kiểm tra Rate Limiting
    blocked_ip, rem_ip = database.check_rate_limit(ip_key, max_attempts=5, lock_minutes=15)
    if blocked_ip:
        raise HTTPException(
            status_code=429,
            detail=f"IP của bạn đã bị khóa tạm thời do nhập sai quá 5 lần. Thử lại sau {rem_ip} giây!"
        )
    blocked_acc, rem_acc = database.check_rate_limit(acc_key, max_attempts=5, lock_minutes=15)
    if blocked_acc:
        raise HTTPException(
            status_code=429,
            detail=f"Tài khoản Super Admin đang bị khóa tạm thời. Thử lại sau {rem_acc} giây!"
        )

    # 2. Lấy hash hiện tại
    custom_hash = database.get_setting("super_admin_password_hash")
    is_valid = False
    needs_upgrade = False

    if custom_hash:
        is_valid, needs_upgrade = database.verify_password(req.password.strip(), custom_hash)
    else:
        # Nếu chưa có hash trong DB, dùng biến môi trường
        env_pass = os.environ.get("SUPER_ADMIN_PASSWORD", "admin@saas2026").strip()
        if req.password.strip() == env_pass:
            is_valid = True
            needs_upgrade = True

    if not is_valid:
        database.record_failed_login(ip_key, max_attempts=5, lock_minutes=15)
        database.record_failed_login(acc_key, max_attempts=30, lock_minutes=15)
        raise HTTPException(status_code=401, detail="Mật khẩu Super Admin không chính xác!")

    # 3. Tự động nâng cấp hash lên bcrypt nếu cần
    if needs_upgrade or not custom_hash:
        database.set_setting("super_admin_password_hash", database.hash_password(req.password.strip()))

    # 4. Xóa lịch sử sai & tạo session Bearer token
    database.clear_failed_logins(ip_key)
    database.clear_failed_logins(acc_key)
    token = database.create_session("SUPER_ADMIN", duration_hours=24)

    return {"success": True, "token": token, "message": "Đăng nhập Super Admin thành công!"}

@app.post("/api/super-admin/change-password")
def super_admin_change_password(
    req: SuperAdminChangePasswordRequest,
    current_admin=Depends(get_current_super_admin)
):
    """Đổi mật khẩu Super Admin (yêu cầu Bearer token)"""
    custom_hash = database.get_setting("super_admin_password_hash")
    old_p = req.old_password.strip()
    new_p = req.new_password.strip()

    if not custom_hash:
        env_pass = os.environ.get("SUPER_ADMIN_PASSWORD", "admin@saas2026").strip()
        if old_p != env_pass:
            raise HTTPException(status_code=401, detail="Mật khẩu cũ không chính xác!")
    else:
        is_valid, _ = database.verify_password(old_p, custom_hash)
        if not is_valid:
            raise HTTPException(status_code=401, detail="Mật khẩu cũ không chính xác!")

    if len(new_p) < 6:
        raise HTTPException(status_code=400, detail="Mật khẩu mới phải có ít nhất 6 ký tự!")

    database.set_setting("super_admin_password_hash", database.hash_password(new_p))
    return {"success": True, "message": "Đã đổi mật khẩu Super Admin thành công và lưu vĩnh viễn!"}

@app.get("/api/super-admin/enterprises")
def get_all_enterprises(current_admin=Depends(get_current_super_admin)):
    """Lấy danh sách tất cả doanh nghiệp (yêu cầu Bearer token)"""
    enterprises = database.query("""
        SELECT e.id, e.company_name, e.tenant_code, e.status, e.plan_tier, e.expires_at, e.created_at,
               b.branch_name
        FROM enterprises e
        LEFT JOIN branches b ON b.enterprise_id = e.id
        ORDER BY e.id DESC
    """)
    return {
        "enterprises": enterprises,
        "is_postgres": database.IS_POSTGRES
    }

@app.post("/api/super-admin/enterprises")
def create_enterprise(
    req: CreateEnterpriseRequest,
    current_admin=Depends(get_current_super_admin)
):
    """Tạo doanh nghiệp mới (yêu cầu Bearer token)"""
    c_name = req.company_name.strip()
    t_code = req.tenant_code.strip().lower().replace(" ", "-")
    d_pass = req.director_password.strip()

    if not c_name:
        raise HTTPException(status_code=400, detail="Vui lòng nhập tên công ty!")
    if not t_code:
        raise HTTPException(status_code=400, detail="Vui lòng nhập mã định danh Tenant!")
    if not d_pass:
        raise HTTPException(status_code=400, detail="Vui lòng đặt mật khẩu ban đầu cho Giám Đốc!")

    existing = database.query_one("SELECT id FROM enterprises WHERE LOWER(tenant_code) = ?", (t_code,))
    if existing:
        raise HTTPException(status_code=400, detail=f"Mã công ty '{t_code}' đã tồn tại trên hệ thống!")

    days = req.days_valid or 365
    if days >= 9999:
        expires = "2099-12-31"
    else:
        expires = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")

    d_hash = database.hash_password(d_pass)
    lic_key = f"SAAS-{t_code.upper()}-{uuid.uuid4().hex[:6].upper()}"

    try:
        database.transaction([
            ("""INSERT INTO enterprises (company_name, tenant_code, license_key, director_password_hash, status, plan_tier, expires_at)
                VALUES (?, ?, ?, ?, 'ACTIVE', ?, ?)""",
             (c_name, t_code, lic_key, d_hash, req.plan_tier or "ENTERPRISE", expires)),
            ("""INSERT INTO branches (enterprise_id, branch_name, branch_code, google_form_work_in, google_form_work_out)
                SELECT id, ?, ?, '', '' FROM enterprises WHERE tenant_code = ?""",
             (f"{c_name} - Cơ Sở 01", "Cổng Điểm Danh Chi Nhánh 1", t_code)),
        ])
    except Exception:
        raise HTTPException(status_code=400, detail="Không thể tạo doanh nghiệp (mã công ty có thể đã tồn tại). Vui lòng thử mã khác!")
    database.cache_clear()

    return {"success": True, "message": f"Đã cấp bản quyền thành công cho công ty: {c_name} (Mã: {t_code})"}

@app.post("/api/super-admin/enterprises/{ent_id}/toggle")
def toggle_enterprise_status(
    ent_id: int,
    current_admin=Depends(get_current_super_admin)
):
    """Khóa hoặc Mở bản quyền doanh nghiệp (yêu cầu Bearer token)"""
    ent = database.query_one("SELECT status, company_name, tenant_code FROM enterprises WHERE id = ?", (ent_id,))
    if not ent:
        raise HTTPException(status_code=404, detail="Không tìm thấy công ty!")

    new_status = "SUSPENDED" if ent["status"] == "ACTIVE" else "ACTIVE"
    database.execute("UPDATE enterprises SET status = ? WHERE id = ?", (new_status, ent_id))
    if new_status == "SUSPENDED":
        database.execute("DELETE FROM sessions WHERE tenant_code = ?", (ent["tenant_code"],))
    database.cache_clear()
    action_text = "ĐÃ KÍCH HOẠT" if new_status == "ACTIVE" else "ĐÃ KHÓA BẢN QUYỀN"
    return {"success": True, "status": new_status, "message": f"{action_text} công ty: {ent['company_name']}"}

@app.post("/api/super-admin/enterprises/{ent_id}/subscription")
def update_enterprise_subscription(
    ent_id: int,
    req: UpdateSubscriptionRequest,
    current_admin=Depends(get_current_super_admin)
):
    """Điều chỉnh gói cước và gia hạn ngày hết hạn (yêu cầu Bearer token)"""
    ent = database.query_one("SELECT id, company_name FROM enterprises WHERE id = ?", (ent_id,))
    if not ent:
        raise HTTPException(status_code=404, detail="Không tìm thấy công ty!")

    plan = req.plan_tier or "ENTERPRISE"
    exp = req.expires_at or "2099-12-31"
    database.execute("UPDATE enterprises SET plan_tier = ?, expires_at = ? WHERE id = ?", (plan, exp, ent_id))
    database.cache_clear()
    return {"success": True, "message": f"Đã cập nhật gói {plan} và hạn sử dụng ({exp}) cho công ty: {ent['company_name']}"}

@app.delete("/api/super-admin/enterprises/{ent_id}")
def delete_enterprise(
    ent_id: int,
    current_admin=Depends(get_current_super_admin)
):
    """Xóa doanh nghiệp khỏi hệ thống (yêu cầu Bearer token)"""
    ent = database.query_one("SELECT tenant_code FROM enterprises WHERE id = ?", (ent_id,))
    if not ent:
        raise HTTPException(status_code=404, detail="Không tìm thấy công ty!")
    t = ent["tenant_code"]
    database.transaction([
        ("DELETE FROM kiosk_devices WHERE tenant_code = ?", (t,)),
        ("DELETE FROM sessions WHERE tenant_code = ?", (t,)),
        ("DELETE FROM branches WHERE enterprise_id = ?", (ent_id,)),
        ("DELETE FROM enterprises WHERE id = ?", (ent_id,)),
    ])
    database.cache_clear()
    return {"success": True, "message": "Đã xóa công ty khỏi hệ thống!"}

# =====================================================================
# 2. API KIOSK STATUS & KÍCH HOẠT THIẾT BỊ BẰNG MẬT KHẨU GIÁM ĐỐC
# =====================================================================
def _load_kiosk_row(t_code: str):
    """Doanh nghiệp + chi nhánh trong 1 truy vấn, nhớ 15 giây (mọi thay đổi từ Super Admin / Giám Đốc sẽ xóa cache ngay)"""
    key = f"kiosk:{t_code}"
    row = database.cache_get(key)
    if row is None:
        where, params = ("WHERE LOWER(e.tenant_code) = ?", (t_code,)) if t_code else ("", ())
        row = database.query_one(f"""
            SELECT e.id, e.company_name, e.tenant_code, e.status, e.expires_at,
                   b.branch_name, b.branch_code, b.google_form_work_in, b.google_form_work_out
            FROM enterprises e LEFT JOIN branches b ON b.enterprise_id = e.id
            {where} ORDER BY e.id ASC, b.id ASC LIMIT 1
        """, params)
        if row:
            database.cache_set(key, row, 15)
    return row

@app.get("/api/kiosk/status")
def get_kiosk_status(
    tenant: Optional[str] = None,
    x_device_token: Optional[str] = Header(None, alias="X-Device-Token"),
    device_token: Optional[str] = Query(None)
):
    """
    Trạng thái Kiosk: khóa bản quyền, hết hạn, và chỉ trả link Google Form khi thiết bị đã kích hoạt.
    """
    ent = _load_kiosk_row((tenant or "").strip().lower())

    if not ent:
        return {
            "status": "SUSPENDED",
            "company_name": "Doanh Nghiệp Chưa Đăng Ký",
            "detail": "Hệ thống chưa tìm thấy dữ liệu doanh nghiệp này. Vui lòng liên hệ nhà cung cấp phần mềm."
        }

    if ent["status"] != "ACTIVE":
        return {
            "status": "SUSPENDED",
            "tenant_code": ent["tenant_code"],
            "company_name": ent["company_name"],
            "detail": "BẢN QUYỀN HỆ THỐNG ĐÃ TẠM KHÓA. Vui lòng liên hệ nhà cung cấp phần mềm để gia hạn / kích hoạt."
        }

    expires_at = ent.get("expires_at")
    if expires_at and expires_at != "Vĩnh viễn":
        exp_clean = str(expires_at).split(" ")[0]
        if exp_clean < datetime.now().strftime("%Y-%m-%d"):
            return {
                "status": "SUSPENDED",
                "tenant_code": ent["tenant_code"],
                "company_name": ent["company_name"],
                "detail": f"Bản quyền phần mềm đã hết hạn vào ngày {exp_clean}. Vui lòng liên hệ nhà cung cấp để gia hạn."
            }

    activated = database.verify_kiosk_device(ent["tenant_code"], x_device_token or device_token or "")
    now = datetime.now()

    return {
        "status": "ACTIVE",
        "tenant_code": ent["tenant_code"],
        "company_name": ent["company_name"],
        "is_device_activated": activated,
        "branch": {
            "name": ent.get("branch_name") or ent["company_name"],
            "code": ent.get("branch_code") or "Cổng Điểm Danh Tự Động",
            "google_form_work_in": (ent.get("google_form_work_in") or "") if activated else "",
            "google_form_work_out": (ent.get("google_form_work_out") or "") if activated else ""
        },
        "server_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "server_epoch_ms": int(now.timestamp() * 1000)
    }

@app.post("/api/kiosk/activate")
def kiosk_activate(req: KioskActivateRequest, request: Request):
    """
    Kích hoạt Kiosk 1 lần duy nhất bằng Mật khẩu Giám Đốc.
    Cấp device_token lưu băm trong DB -> Kiosk hoạt động vĩnh viễn
    """
    client_ip = get_client_ip(request)
    t_code = req.tenant_code.strip().lower()
    raw_pass = req.password.strip()
    rate_key = f"kiosk:{t_code}:{client_ip}"

    # Rate Limiting
    blocked, rem = database.check_rate_limit(rate_key, max_attempts=5, lock_minutes=15)
    if blocked:
        raise HTTPException(
            status_code=429,
            detail=f"Bạn đã thử kích hoạt sai quá nhiều lần. Vui lòng thử lại sau {rem} giây!"
        )

    ent = database.query_one("SELECT id, director_password_hash, company_name, status, expires_at FROM enterprises WHERE LOWER(tenant_code) = ?", (t_code,))
    if not ent:
        raise HTTPException(status_code=404, detail="Không tìm thấy thông tin doanh nghiệp!")

    if ent["status"] != "ACTIVE":
        raise HTTPException(status_code=403, detail="Bản quyền doanh nghiệp đang bị khóa bởi nhà cung cấp!")

    is_valid, needs_upgrade = database.verify_password(raw_pass, ent["director_password_hash"])
    if not is_valid:
        database.record_failed_login(rate_key, max_attempts=5, lock_minutes=15)
        raise HTTPException(status_code=401, detail="Mật khẩu Giám Đốc không chính xác!")

    if needs_upgrade:
        database.execute("UPDATE enterprises SET director_password_hash = ? WHERE id = ?", (database.hash_password(raw_pass), ent["id"]))

    database.clear_failed_logins(rate_key)

    # Cấp device token lưu băm vào DB
    device_token = database.register_kiosk_device(t_code, device_name=f"Kiosk-{client_ip}")

    return {
        "success": True,
        "device_token": device_token,
        "company_name": ent["company_name"],
        "message": f"Kích hoạt thành công Kiosk cho: {ent['company_name']}! Kiosk sẵn sàng phục vụ nhân viên 24/7."
    }

# =====================================================================
# 3. API DÀNH RIÊNG CHO GIÁM ĐỐC (CÀI ĐẶT FORM & CƠ SỞ)
# =====================================================================
@app.post("/api/director/login")
def director_login(req: DirectorLoginRequest, request: Request):
    """Giám Đốc đăng nhập vào trang Cài Đặt (Rate limited, cấp Bearer token)"""
    client_ip = get_client_ip(request)
    t_code = req.tenant_code.strip().lower()
    raw_pass = req.password.strip()
    rate_key = f"dir:{t_code}:{client_ip}"

    # Rate Limiting
    blocked, rem = database.check_rate_limit(rate_key, max_attempts=5, lock_minutes=15)
    if blocked:
        raise HTTPException(
            status_code=429,
            detail=f"Đăng nhập sai quá 5 lần. Vui lòng thử lại sau {rem} giây!"
        )

    ent = database.query_one("SELECT id, director_password_hash, company_name, status FROM enterprises WHERE LOWER(tenant_code) = ?", (t_code,))
    if not ent:
        raise HTTPException(status_code=404, detail="Không tìm thấy doanh nghiệp!")

    if ent["status"] != "ACTIVE":
        raise HTTPException(status_code=403, detail="Bản quyền doanh nghiệp đã bị tạm khóa bởi nhà cung cấp!")

    is_valid, needs_upgrade = database.verify_password(raw_pass, ent["director_password_hash"])
    if not is_valid:
        database.record_failed_login(rate_key, max_attempts=5, lock_minutes=15)
        raise HTTPException(status_code=401, detail="Mật khẩu Giám Đốc không chính xác!")

    if needs_upgrade:
        database.execute("UPDATE enterprises SET director_password_hash = ? WHERE id = ?", (database.hash_password(raw_pass), ent["id"]))

    database.clear_failed_logins(rate_key)
    token = database.create_session("DIRECTOR", tenant_code=t_code, duration_hours=24)

    return {"success": True, "token": token, "company_name": ent["company_name"], "message": "Xác thực Giám Đốc thành công!"}

@app.get("/api/director/config")
def get_director_config(
    tenant: str,
    current_director=Depends(get_current_director)
):
    """Lấy thông tin cấu hình cơ sở & Google Form (yêu cầu Bearer token Giám Đốc)"""
    t_code = tenant.strip().lower()
    ent = database.query_one("SELECT id, company_name, tenant_code FROM enterprises WHERE LOWER(tenant_code) = ?", (t_code,))
    if not ent:
        raise HTTPException(status_code=404, detail="Không tìm thấy doanh nghiệp!")

    branch = database.query_one("SELECT * FROM branches WHERE enterprise_id = ? ORDER BY id ASC", (ent["id"],))
    branch_dict = branch or {}

    return {
        "company_name": ent["company_name"],
        "tenant_code": ent["tenant_code"],
        "branch_name": branch_dict.get("branch_name", ""),
        "branch_code": branch_dict.get("branch_code", ""),
        "google_form_work_in": branch_dict.get("google_form_work_in", ""),
        "google_form_work_out": branch_dict.get("google_form_work_out", "")
    }

@app.post("/api/director/update-config")
def update_director_config(
    req: DirectorUpdateConfigRequest,
    current_director=Depends(get_current_director)
):
    """
    Giám Đốc lưu thông tin cơ sở & link Google Form (yêu cầu Bearer token).
    Tự động chuẩn hóa link Google Form sang /viewform?embedded=true
    """
    t_code = req.tenant_code.strip().lower()
    require_same_tenant(current_director, t_code)
    ent = database.query_one("SELECT id FROM enterprises WHERE LOWER(tenant_code) = ?", (t_code,))
    if not ent:
        raise HTTPException(status_code=404, detail="Không tìm thấy doanh nghiệp!")

    # Chuẩn hóa link Google Form
    norm_in = normalize_google_form_url(req.work_in_url or "")
    norm_out = normalize_google_form_url(req.work_out_url or "")

    # Cập nhật tên công ty
    database.execute("UPDATE enterprises SET company_name = ? WHERE id = ?", (req.company_name.strip(), ent["id"]))

    # Cập nhật thông tin chi nhánh & Google Form
    b_code = (req.branch_code or "").strip()
    if b_code:
        database.execute("""
            UPDATE branches
            SET branch_name = ?, branch_code = ?, google_form_work_in = ?, google_form_work_out = ?
            WHERE enterprise_id = ?
        """, (req.branch_name.strip(), b_code, norm_in, norm_out, ent["id"]))
    else:
        database.execute("""
            UPDATE branches
            SET branch_name = ?, google_form_work_in = ?, google_form_work_out = ?
            WHERE enterprise_id = ?
        """, (req.branch_name.strip(), norm_in, norm_out, ent["id"]))

    database.cache_clear()
    return {
        "success": True,
        "message": "Đã lưu thành công thông tin cơ sở & biểu mẫu Google Form!",
        "work_in_url": norm_in,
        "work_out_url": norm_out
    }

@app.post("/api/director/change-password")
def change_director_password(
    req: DirectorChangePasswordRequest,
    current_director=Depends(get_current_director)
):
    """Giám Đốc đổi mật khẩu quản trị (yêu cầu Bearer token)"""
    t_code = req.tenant_code.strip().lower()
    require_same_tenant(current_director, t_code)
    ent = database.query_one("SELECT id, director_password_hash FROM enterprises WHERE LOWER(tenant_code) = ?", (t_code,))

    if not ent:
        raise HTTPException(status_code=404, detail="Không tìm thấy doanh nghiệp!")

    is_valid, _ = database.verify_password(req.old_password.strip(), ent["director_password_hash"])
    if not is_valid:
        raise HTTPException(status_code=401, detail="Mật khẩu Giám Đốc hiện tại không đúng!")

    if len(req.new_password.strip()) < 6:
        raise HTTPException(status_code=400, detail="Mật khẩu mới phải có ít nhất 6 ký tự!")

    new_hash = database.hash_password(req.new_password.strip())
    database.execute("UPDATE enterprises SET director_password_hash = ? WHERE id = ?", (new_hash, ent["id"]))
    return {"success": True, "message": "Giám đốc đã đổi mật khẩu thành công!"}

# =====================================================================
# 4. GIAO DIỆN WEB (STATIC SERVE)
# =====================================================================
@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.get("/", response_class=HTMLResponse)
def serve_kiosk():
    p = find_static_file("index.html")
    if p:
        return FileResponse(p)
    return HTMLResponse("<h2>Kiosk UI: Vui lòng tải index.html!</h2>")

@app.get("/super-admin", response_class=HTMLResponse)
def serve_super_admin():
    p = find_static_file("super_admin.html")
    if p:
        return FileResponse(p)
    return HTMLResponse("<h2>Super Admin UI: Vui lòng tải super_admin.html!</h2>")

@app.get("/admin", response_class=HTMLResponse)
def serve_admin():
    p = find_static_file("super_admin.html")
    if p:
        return FileResponse(p)
    return FileResponse(find_static_file("index.html"))

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    print("\n" + "="*70)
    print(">> ENTERPRISE TIMECLOCK SAAS PRO V5.0 SECURE ENGINE RUNNING")
    print(f">> Master Server listening on: http://0.0.0.0:{port}")
    print(f">> Super Admin Portal: http://0.0.0.0:{port}/super-admin")
    print("="*70 + "\n")
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
