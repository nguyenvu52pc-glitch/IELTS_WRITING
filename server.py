"""
ENTERPRISE TIMECLOCK SAAS PRO - UNIFIED MULTI-TENANT BACKEND SERVER (V4.1)
1. Hỗ trợ Đổi Mật Khẩu Super Admin & Lưu Trữ Đám Mây (PostgreSQL / SQLite)
2. Kiosk Kích Hoạt 1 Lần Bằng Mật Khẩu Giám Đốc -> Hoạt Động Vĩnh Viễn
3. Loại bỏ phiền phức tài khoản Quản Lý mở ca hàng ngày
4. Super Admin kiểm soát bật / tắt bản quyền tức thì
"""

import os
import uuid
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import database

# Khởi tạo DB
database.init_db()

app = FastAPI(title="Enterprise TimeClock Multi-Tenant SaaS", version="4.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

SUPER_ADMIN_SESSIONS = set()
DIRECTOR_SESSIONS = set()

# =====================================================================
# PYDANTIC SCHEMAS
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

# Helper tìm file
def find_static_file(filename: str):
    for candidate in [
        os.path.join(STATIC_DIR, filename),
        os.path.join(BASE_DIR, filename),
    ]:
        if os.path.exists(candidate):
            return candidate
    return None

def verify_super_admin_pass(raw_pass: str) -> bool:
    custom_hash = database.get_setting("super_admin_password_hash")
    if custom_hash:
        return custom_hash == database.hash_password(raw_pass.strip())
    default_pass = os.environ.get("SUPER_ADMIN_PASSWORD", "owner@saas2026")
    return raw_pass.strip() == default_pass

# =====================================================================
# 1. API SUPER ADMIN (DÀNH CHO BẠN - QUẢN LÝ BẢN QUYỀN CÁC CÔNG TY)
# =====================================================================
@app.post("/api/super-admin/login")
def super_admin_login(req: SuperAdminLoginRequest):
    if verify_super_admin_pass(req.password):
        token = str(uuid.uuid4())
        SUPER_ADMIN_SESSIONS.add(token)
        return {"success": True, "token": token, "message": "Đăng nhập Super Admin thành công!"}
    raise HTTPException(status_code=401, detail="Mật khẩu Super Admin không chính xác!")

@app.post("/api/super-admin/change-password")
def super_admin_change_password(req: SuperAdminChangePasswordRequest):
    if not verify_super_admin_pass(req.old_password):
        raise HTTPException(status_code=401, detail="Mật khẩu Super Admin hiện tại không chính xác!")
    new_p = req.new_password.strip()
    if len(new_p) < 6:
        raise HTTPException(status_code=400, detail="Mật khẩu mới phải có ít nhất 6 ký tự!")
    database.set_setting("super_admin_password_hash", database.hash_password(new_p))
    return {"success": True, "message": "Đã đổi mật khẩu Super Admin thành công và lưu vĩnh viễn!"}

@app.get("/api/super-admin/enterprises")
def get_all_enterprises():
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
def create_enterprise(req: CreateEnterpriseRequest):
    c_name = req.company_name.strip()
    t_code = req.tenant_code.strip().lower().replace(" ", "-")
    d_pass = req.director_password.strip()

    if not c_name:
        raise HTTPException(status_code=400, detail="Vui lòng nhập tên công ty!")
    if not t_code:
        raise HTTPException(status_code=400, detail="Vui lòng nhập mã định danh Tenant!")
    if not d_pass:
        raise HTTPException(status_code=400, detail="Vui lòng đặt mật khẩu ban đầu cho Giám Đốc!")

    # Kiểm tra mã tenant
    existing = database.query_one("SELECT id FROM enterprises WHERE LOWER(tenant_code) = ?", (t_code,))
    if existing:
        raise HTTPException(status_code=400, detail=f"Mã công ty '{t_code}' đã tồn tại trên hệ thống!")

    expires = (datetime.now() + timedelta(days=req.days_valid or 365)).strftime("%Y-%m-%d")
    d_hash = database.hash_password(d_pass)
    lic_key = f"SAAS-{t_code.upper()}-{uuid.uuid4().hex[:6].upper()}"

    try:
        database.execute("""
            INSERT INTO enterprises (company_name, tenant_code, license_key, director_password_hash, status, plan_tier, expires_at)
            VALUES (?, ?, ?, ?, 'ACTIVE', ?, ?)
        """, (c_name, t_code, lic_key, d_hash, req.plan_tier or "ENTERPRISE", expires))

        ent = database.query_one("SELECT id FROM enterprises WHERE LOWER(tenant_code) = ?", (t_code,))
        ent_id = ent["id"]

        database.execute("""
            INSERT INTO branches (enterprise_id, branch_name, branch_code, google_form_work_in, google_form_work_out)
            VALUES (?, ?, ?, '', '')
        """, (ent_id, f"{c_name} - Cơ Sở 01", "Cổng Điểm Danh Chi Nhánh 1"))

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Lỗi tạo doanh nghiệp: {str(e)}")

    return {"success": True, "message": f"Đã cấp bản quyền thành công cho công ty: {c_name} (Mã: {t_code})"}

@app.post("/api/super-admin/enterprises/{ent_id}/toggle")
def toggle_enterprise_status(ent_id: int):
    ent = database.query_one("SELECT status, company_name FROM enterprises WHERE id = ?", (ent_id,))
    if not ent:
        raise HTTPException(status_code=404, detail="Không tìm thấy công ty!")

    new_status = "SUSPENDED" if ent["status"] == "ACTIVE" else "ACTIVE"
    database.execute("UPDATE enterprises SET status = ? WHERE id = ?", (new_status, ent_id))
    action_text = "ĐÃ KÍCH HOẠT" if new_status == "ACTIVE" else "ĐÃ KHÓA BẢN QUYỀN"
    return {"success": True, "status": new_status, "message": f"{action_text} công ty: {ent['company_name']}"}

@app.delete("/api/super-admin/enterprises/{ent_id}")
def delete_enterprise(ent_id: int):
    database.execute("DELETE FROM branches WHERE enterprise_id = ?", (ent_id,))
    database.execute("DELETE FROM enterprises WHERE id = ?", (ent_id,))
    return {"success": True, "message": "Đã xóa công ty khỏi hệ thống!"}

# =====================================================================
# 2. API KIOSK STATUS & KÍCH HOẠT 1 LẦN BẰNG MẬT KHẨU GIÁM ĐỐC
# =====================================================================
@app.get("/api/kiosk/status")
def get_kiosk_status(tenant: Optional[str] = None):
    if tenant:
        ent = database.query_one("SELECT * FROM enterprises WHERE LOWER(tenant_code) = ?", (tenant.strip().lower(),))
    else:
        ent = database.query_one("SELECT * FROM enterprises ORDER BY id ASC")
    
    if not ent:
        return {
            "status": "SUSPENDED",
            "company_name": "Doanh Nghiệp Chưa Đăng Ký",
            "detail": "Hệ thống chưa tìm thấy dữ liệu doanh nghiệp này. Vui lòng liên hệ nhà cung cấp phần mềm."
        }

    # KIỂM TRA BẢN QUYỀN: BẬT HAY KHÓA?
    if ent["status"] != "ACTIVE":
        return {
            "status": "SUSPENDED",
            "tenant_code": ent["tenant_code"],
            "company_name": ent["company_name"],
            "detail": "BẢN QUYỀN HỆ THỐNG ĐÃ TẠM KHÓA HOẶC HẾT HẠN. Vui lòng liên hệ nhà cung cấp phần mềm để gia hạn / kích hoạt."
        }

    branch = database.query_one("SELECT * FROM branches WHERE enterprise_id = ? ORDER BY id ASC", (ent["id"],))
    branch_dict = branch or {}
    now = datetime.now()

    return {
        "status": "ACTIVE",
        "tenant_code": ent["tenant_code"],
        "company_name": ent["company_name"],
        "branch": {
            "name": branch_dict.get("branch_name", ent["company_name"]),
            "code": branch_dict.get("branch_code", "Cổng Điểm Danh Tự Động"),
            "google_form_work_in": branch_dict.get("google_form_work_in", ""),
            "google_form_work_out": branch_dict.get("google_form_work_out", "")
        },
        "server_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "server_epoch_ms": int(now.timestamp() * 1000)
    }

@app.post("/api/kiosk/activate")
def kiosk_activate(req: KioskActivateRequest):
    """
    Kích hoạt Kiosk 1 lần duy nhất bằng Mật khẩu Giám Đốc -> Kiosk hoạt động vĩnh viễn
    """
    t_code = req.tenant_code.strip().lower()
    raw_pass = req.password.strip()

    ent = database.query_one("SELECT id, director_password_hash, company_name, status FROM enterprises WHERE LOWER(tenant_code) = ?", (t_code,))
    if not ent:
        raise HTTPException(status_code=404, detail="Không tìm thấy thông tin doanh nghiệp!")

    if ent["status"] != "ACTIVE":
        raise HTTPException(status_code=403, detail="Bản quyền doanh nghiệp đang bị khóa bởi nhà cung cấp!")

    expected_hash = database.hash_password(raw_pass)
    if ent["director_password_hash"] != expected_hash:
        raise HTTPException(status_code=401, detail="Mật khẩu Giám Đốc không chính xác!")

    token = str(uuid.uuid4())
    return {
        "success": True,
        "token": token,
        "company_name": ent["company_name"],
        "message": f"Kích hoạt thành công Kiosk cho: {ent['company_name']}! Kiosk sẽ mở sẵn sàng cho nhân viên chấm công."
    }

# =====================================================================
# 3. API DÀNH RIÊNG CHO GIÁM ĐỐC (CÀI ĐẶT FORM & CƠ SỞ)
# =====================================================================
@app.post("/api/director/login")
def director_login(req: DirectorLoginRequest):
    t_code = req.tenant_code.strip().lower()
    raw_pass = req.password.strip()

    ent = database.query_one("SELECT id, director_password_hash, company_name, status FROM enterprises WHERE LOWER(tenant_code) = ?", (t_code,))
    if not ent:
        raise HTTPException(status_code=404, detail="Không tìm thấy doanh nghiệp!")

    if ent["status"] != "ACTIVE":
        raise HTTPException(status_code=403, detail="Bản quyền doanh nghiệp đã bị tạm khóa bởi nhà cung cấp!")

    expected_hash = database.hash_password(raw_pass)
    if ent["director_password_hash"] != expected_hash:
        raise HTTPException(status_code=401, detail="Mật khẩu Giám Đốc không chính xác!")

    token = str(uuid.uuid4())
    DIRECTOR_SESSIONS.add(token)
    return {"success": True, "token": token, "company_name": ent["company_name"], "message": "Xác thực Giám Đốc thành công!"}

@app.get("/api/director/config")
def get_director_config(tenant: str):
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
def update_director_config(req: DirectorUpdateConfigRequest):
    t_code = req.tenant_code.strip().lower()
    ent = database.query_one("SELECT id FROM enterprises WHERE LOWER(tenant_code) = ?", (t_code,))
    if not ent:
        raise HTTPException(status_code=404, detail="Không tìm thấy doanh nghiệp!")

    # Cập nhật tên công ty
    database.execute("UPDATE enterprises SET company_name = ? WHERE id = ?", (req.company_name.strip(), ent["id"]))

    # Cập nhật thông tin chi nhánh & Google Form
    database.execute("""
        UPDATE branches
        SET branch_name = ?, branch_code = ?, google_form_work_in = ?, google_form_work_out = ?
        WHERE enterprise_id = ?
    """, (
        req.branch_name.strip(),
        req.branch_code.strip() if req.branch_code else "",
        req.work_in_url.strip() if req.work_in_url else "",
        req.work_out_url.strip() if req.work_out_url else "",
        ent["id"]
    ))

    return {"success": True, "message": "Giám đốc đã lưu thông tin cơ sở và biểu mẫu thành công!"}

@app.post("/api/director/change-password")
def change_director_password(req: DirectorChangePasswordRequest):
    t_code = req.tenant_code.strip().lower()
    ent = database.query_one("SELECT id, director_password_hash FROM enterprises WHERE LOWER(tenant_code) = ?", (t_code,))

    if not ent:
        raise HTTPException(status_code=404, detail="Không tìm thấy doanh nghiệp!")

    old_hash = database.hash_password(req.old_password.strip())
    if ent["director_password_hash"] != old_hash:
        raise HTTPException(status_code=401, detail="Mật khẩu Giám Đốc hiện tại không đúng!")

    new_hash = database.hash_password(req.new_password.strip())
    database.execute("UPDATE enterprises SET director_password_hash = ? WHERE id = ?", (new_hash, ent["id"]))
    return {"success": True, "message": "Giám đốc đã đổi mật khẩu thành công!"}

# =====================================================================
# 4. GIAO DIỆN WEB (STATIC SERVE)
# =====================================================================
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
    print(">> ENTERPRISE TIMECLOCK SAAS PRO V4.1 RUNNING")
    print(f">> Master Server listening on: http://0.0.0.0:{port}")
    print(f">> Super Admin Portal: http://0.0.0.0:{port}/super-admin")
    print("="*70 + "\n")
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
