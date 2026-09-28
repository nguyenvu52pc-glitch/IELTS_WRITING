"""
ENTERPRISE TIMECLOCK SAAS PRO - MULTI-TENANT BACKEND SERVER (V4.0)
Hỗ trợ kiến trúc 3 cấp quyền hạn độc lập:
1. Super Admin (Bạn - Nhà cung cấp SaaS): Quản lý bản quyền, Bật/Tắt kích hoạt các Công Ty
2. Giám Đốc (Director): Cài đặt tên cơ sở, link Google Form, và cấp tài khoản Quản Lý
3. Quản Lý (Manager): Đăng nhập mở ca cho Kiosk để nhân viên chấm công
"""

import os
import io
import csv
import uuid
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import database

# Khởi tạo DB
database.init_db()

app = FastAPI(title="Enterprise TimeClock Multi-Tenant SaaS", version="4.0.0")

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

SUPER_ADMIN_PASSWORD = os.environ.get("SUPER_ADMIN_PASSWORD", "owner@saas2026")
SUPER_ADMIN_SESSIONS = set()
DIRECTOR_SESSIONS = set()

# =====================================================================
# PYDANTIC SCHEMAS
# =====================================================================
class SuperAdminLoginRequest(BaseModel):
    password: str

class CreateEnterpriseRequest(BaseModel):
    company_name: str
    tenant_code: str
    director_password: str
    plan_tier: Optional[str] = "ENTERPRISE"
    days_valid: Optional[int] = 365

class ManagerLoginRequest(BaseModel):
    tenant_code: str
    username: str
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

class CreateManagerRequest(BaseModel):
    tenant_code: str
    username: str
    full_name: str
    password: str
    role: Optional[str] = "QUẢN LÝ CA"

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

# =====================================================================
# 1. API SUPER ADMIN (DÀNH CHO BẠN - QUẢN LÝ BẢN QUYỀN CÁC CÔNG TY)
# =====================================================================
@app.post("/api/super-admin/login")
def super_admin_login(req: SuperAdminLoginRequest):
    if req.password.strip() == SUPER_ADMIN_PASSWORD:
        token = str(uuid.uuid4())
        SUPER_ADMIN_SESSIONS.add(token)
        return {"success": True, "token": token, "message": "Đăng nhập Super Admin thành công!"}
    raise HTTPException(status_code=401, detail="Mật khẩu Super Admin không chính xác!")

@app.get("/api/super-admin/enterprises")
def get_all_enterprises():
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT e.id, e.company_name, e.tenant_code, e.status, e.plan_tier, e.expires_at, e.created_at,
               b.branch_name,
               (SELECT COUNT(*) FROM managers m WHERE m.enterprise_id = e.id) as manager_count
        FROM enterprises e
        LEFT JOIN branches b ON b.enterprise_id = e.id
        GROUP BY e.id
        ORDER BY e.id DESC
    """)
    enterprises = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"enterprises": enterprises}

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

    conn = database.get_connection()
    cursor = conn.cursor()
    
    # Kiểm tra mã tenant
    cursor.execute("SELECT id FROM enterprises WHERE tenant_code = ?", (t_code,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail=f"Mã công ty '{t_code}' đã tồn tại trên hệ thống!")

    expires = (datetime.now() + timedelta(days=req.days_valid or 365)).strftime("%Y-%m-%d")
    d_hash = database.hash_password(d_pass)
    lic_key = f"SAAS-{t_code.upper()}-{uuid.uuid4().hex[:6].upper()}"

    try:
        cursor.execute("""
            INSERT INTO enterprises (company_name, tenant_code, license_key, director_password_hash, status, plan_tier, expires_at)
            VALUES (?, ?, ?, ?, 'ACTIVE', ?, ?)
        """, (c_name, t_code, lic_key, d_hash, req.plan_tier or "ENTERPRISE", expires))
        ent_id = cursor.lastrowid

        # Tạo branch mặc định cho công ty
        cursor.execute("""
            INSERT INTO branches (enterprise_id, branch_name, branch_code, google_form_work_in, google_form_work_out)
            VALUES (?, ?, ?, '', '')
        """, (ent_id, f"{c_name} - Cơ Sở 01", "Cổng Điểm Danh Chi Nhánh 1"))

        conn.commit()
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Lỗi tạo doanh nghiệp: {str(e)}")

    conn.close()
    return {"success": True, "message": f"Đã cấp bản quyền thành công cho công ty: {c_name} (Mã: {t_code})"}

@app.post("/api/super-admin/enterprises/{ent_id}/toggle")
def toggle_enterprise_status(ent_id: int):
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT status, company_name FROM enterprises WHERE id = ?", (ent_id,))
    ent = cursor.fetchone()
    if not ent:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy công ty!")

    new_status = "SUSPENDED" if ent["status"] == "ACTIVE" else "ACTIVE"
    cursor.execute("UPDATE enterprises SET status = ? WHERE id = ?", (new_status, ent_id))
    conn.commit()
    conn.close()
    action_text = "ĐÃ KÍCH HOẠT" if new_status == "ACTIVE" else "ĐÃ KHÓA BẢN QUYỀN"
    return {"success": True, "status": new_status, "message": f"{action_text} công ty: {ent['company_name']}"}

@app.delete("/api/super-admin/enterprises/{ent_id}")
def delete_enterprise(ent_id: int):
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM managers WHERE enterprise_id = ?", (ent_id,))
    cursor.execute("DELETE FROM branches WHERE enterprise_id = ?", (ent_id,))
    cursor.execute("DELETE FROM enterprises WHERE id = ?", (ent_id,))
    conn.commit()
    conn.close()
    return {"success": True, "message": "Đã xóa công ty khỏi hệ thống!"}

# =====================================================================
# 2. API KIOSK STATUS & ĐĂNG NHẬP MỞ CA CHO QUẢN LÝ
# =====================================================================
@app.get("/api/kiosk/status")
def get_kiosk_status(tenant: Optional[str] = None):
    conn = database.get_connection()
    cursor = conn.cursor()

    if tenant:
        cursor.execute("SELECT * FROM enterprises WHERE LOWER(tenant_code) = ?", (tenant.strip().lower(),))
    else:
        cursor.execute("SELECT * FROM enterprises ORDER BY id ASC LIMIT 1")
    
    ent = cursor.fetchone()
    if not ent:
        conn.close()
        return {
            "status": "SUSPENDED",
            "company_name": "Doanh Nghiệp Chưa Đăng Ký",
            "detail": "Hệ thống chưa tìm thấy dữ liệu doanh nghiệp này. Vui lòng liên hệ nhà cung cấp phần mềm."
        }

    # KIỂM TRA BẢN QUYỀN: BẬT HAY KHÓA?
    if ent["status"] != "ACTIVE":
        conn.close()
        return {
            "status": "SUSPENDED",
            "tenant_code": ent["tenant_code"],
            "company_name": ent["company_name"],
            "detail": "BẢN QUYỀN HỆ THỐNG ĐÃ TẠM KHÓA HOẶC HẾT HẠN. Vui lòng liên hệ nhà cung cấp phần mềm để gia hạn / kích hoạt."
        }

    # Lấy thông tin chi nhánh
    cursor.execute("SELECT * FROM branches WHERE enterprise_id = ? ORDER BY id ASC LIMIT 1", (ent["id"],))
    branch = cursor.fetchone()
    conn.close()

    branch_dict = dict(branch) if branch else {}
    now = datetime.now()

    return {
        "status": "ACTIVE",
        "tenant_code": ent["tenant_code"],
        "company_name": ent["company_name"],
        "branch": {
            "name": branch_dict.get("branch_name", ent["company_name"]),
            "code": branch_dict.get("branch_code", "Cổng Điểm Danh & Chấm Công"),
            "google_form_work_in": branch_dict.get("google_form_work_in", ""),
            "google_form_work_out": branch_dict.get("google_form_work_out", "")
        },
        "server_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "server_epoch_ms": int(now.timestamp() * 1000)
    }

@app.post("/api/manager/login")
def manager_login(req: ManagerLoginRequest):
    """
    Quản lý cửa hàng đăng nhập mở ca tại Kiosk
    """
    t_code = req.tenant_code.strip().lower()
    u_name = req.username.strip()
    raw_pass = req.password.strip()

    conn = database.get_connection()
    cursor = conn.cursor()

    # Kiểm tra enterprise
    cursor.execute("SELECT id, status, company_name FROM enterprises WHERE LOWER(tenant_code) = ?", (t_code,))
    ent = cursor.fetchone()
    if not ent:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy thông tin doanh nghiệp!")

    if ent["status"] != "ACTIVE":
        conn.close()
        raise HTTPException(status_code=403, detail="Bản quyền doanh nghiệp đang bị tạm ngưng! Không thể mở ca.")

    # Tìm Quản Lý
    cursor.execute("""
        SELECT * FROM managers 
        WHERE enterprise_id = ? AND LOWER(username) = ?
    """, (ent["id"], u_name.lower()))
    manager = cursor.fetchone()

    if not manager:
        conn.close()
        raise HTTPException(status_code=401, detail="Tài khoản Quản lý không tồn tại!")

    if not manager["is_active"]:
        conn.close()
        raise HTTPException(status_code=403, detail="Tài khoản Quản lý này đang bị Giám đốc tạm khóa!")

    expected_hash = database.hash_password(raw_pass)
    if manager["password_hash"] != expected_hash:
        conn.close()
        raise HTTPException(status_code=401, detail="Mật khẩu Quản lý không chính xác!")

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("UPDATE managers SET last_login = ? WHERE id = ?", (now_str, manager["id"]))
    conn.commit()
    conn.close()

    return {
        "success": True,
        "manager_name": manager["full_name"],
        "role": manager["role"],
        "session_token": str(uuid.uuid4()),
        "welcome_text": f"Quản lý: {manager['full_name']}"
    }

# =====================================================================
# 3. API DÀNH RIÊNG CHO GIÁM ĐỐC (CÀI ĐẶT FORM & QUẢN LÝ TÀI KHOẢN)
# =====================================================================
@app.post("/api/director/login")
def director_login(req: DirectorLoginRequest):
    t_code = req.tenant_code.strip().lower()
    raw_pass = req.password.strip()

    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, director_password_hash, company_name, status FROM enterprises WHERE LOWER(tenant_code) = ?", (t_code,))
    ent = cursor.fetchone()
    conn.close()

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
    conn = database.get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, company_name, tenant_code FROM enterprises WHERE LOWER(tenant_code) = ?", (tenant.strip().lower(),))
    ent = cursor.fetchone()
    if not ent:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy doanh nghiệp!")

    cursor.execute("SELECT * FROM branches WHERE enterprise_id = ? ORDER BY id ASC LIMIT 1", (ent["id"],))
    branch = cursor.fetchone()
    branch_dict = dict(branch) if branch else {}

    cursor.execute("""
        SELECT id, username, full_name, role, is_active, last_login, created_at
        FROM managers
        WHERE enterprise_id = ?
        ORDER BY id DESC
    """, (ent["id"],))
    managers = [dict(m) for m in cursor.fetchall()]
    conn.close()

    return {
        "company_name": ent["company_name"],
        "tenant_code": ent["tenant_code"],
        "branch_name": branch_dict.get("branch_name", ""),
        "branch_code": branch_dict.get("branch_code", ""),
        "google_form_work_in": branch_dict.get("google_form_work_in", ""),
        "google_form_work_out": branch_dict.get("google_form_work_out", ""),
        "managers": managers
    }

@app.post("/api/director/update-config")
def update_director_config(req: DirectorUpdateConfigRequest):
    t_code = req.tenant_code.strip().lower()
    conn = database.get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM enterprises WHERE LOWER(tenant_code) = ?", (t_code,))
    ent = cursor.fetchone()
    if not ent:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy doanh nghiệp!")

    # Cập nhật tên công ty
    cursor.execute("UPDATE enterprises SET company_name = ? WHERE id = ?", (req.company_name.strip(), ent["id"]))

    # Cập nhật thông tin chi nhánh & Google Form
    cursor.execute("""
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

    conn.commit()
    conn.close()
    return {"success": True, "message": "Giám đốc đã lưu thông tin cơ sở và biểu mẫu thành công!"}

@app.post("/api/director/managers")
def add_manager_by_director(req: CreateManagerRequest):
    t_code = req.tenant_code.strip().lower()
    u_name = req.username.strip()
    f_name = req.full_name.strip()
    raw_pass = req.password.strip()

    if not u_name or not f_name or not raw_pass:
        raise HTTPException(status_code=400, detail="Vui lòng điền đủ Tên đăng nhập, Họ tên và Mật khẩu!")

    conn = database.get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM enterprises WHERE LOWER(tenant_code) = ?", (t_code,))
    ent = cursor.fetchone()
    if not ent:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy doanh nghiệp!")

    p_hash = database.hash_password(raw_pass)

    try:
        cursor.execute("""
            INSERT INTO managers (enterprise_id, username, full_name, password_hash, role, is_active)
            VALUES (?, ?, ?, ?, ?, 1)
        """, (ent["id"], u_name, f_name, p_hash, req.role or "QUẢN LÝ CA"))
        conn.commit()
    except Exception:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Tên đăng nhập '{u_name}' đã tồn tại trong doanh nghiệp này!")

    conn.close()
    return {"success": True, "message": f"Giám đốc đã cấp tài khoản Quản lý cho: {f_name}"}

@app.post("/api/director/managers/{mgr_id}/toggle")
def toggle_manager(mgr_id: int):
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT is_active, full_name FROM managers WHERE id = ?", (mgr_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản quản lý!")

    new_st = 0 if row["is_active"] else 1
    cursor.execute("UPDATE managers SET is_active = ? WHERE id = ?", (new_st, mgr_id))
    conn.commit()
    conn.close()
    txt = "ĐÃ MỞ KHÓA" if new_st == 1 else "ĐÃ TẠM KHÓA"
    return {"success": True, "is_active": new_st, "message": f"{txt} tài khoản: {row['full_name']}"}

@app.delete("/api/director/managers/{mgr_id}")
def delete_manager(mgr_id: int):
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM managers WHERE id = ?", (mgr_id,))
    conn.commit()
    conn.close()
    return {"success": True, "message": "Đã xóa tài khoản Quản lý!"}

@app.post("/api/director/change-password")
def change_director_password(req: DirectorChangePasswordRequest):
    t_code = req.tenant_code.strip().lower()
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, director_password_hash FROM enterprises WHERE LOWER(tenant_code) = ?", (t_code,))
    ent = cursor.fetchone()

    if not ent:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy doanh nghiệp!")

    old_hash = database.hash_password(req.old_password.strip())
    if ent["director_password_hash"] != old_hash:
        conn.close()
        raise HTTPException(status_code=401, detail="Mật khẩu Giám Đốc hiện tại không đúng!")

    new_hash = database.hash_password(req.new_password.strip())
    cursor.execute("UPDATE enterprises SET director_password_hash = ? WHERE id = ?", (new_hash, ent["id"]))
    conn.commit()
    conn.close()
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
    p = find_static_file("admin.html")
    if p:
        return FileResponse(p)
    return FileResponse(find_static_file("index.html"))

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    print("\n" + "="*70)
    print(">> ENTERPRISE TIMECLOCK SAAS PRO V4.0 (MULTI-TENANT) RUNNING")
    print(f">> Master Server listening on: http://0.0.0.0:{port}")
    print(f">> Super Admin Portal: http://0.0.0.0:{port}/super-admin")
    print("="*70 + "\n")
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
