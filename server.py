"""
ENTERPRISE TIMECLOCK SAAS PRO - BACKEND SERVER (V3.9)
1. Đăng nhập Email BẮT BUỘC ĐI KÈM MẬT KHẨU (Xác thực tại Server, mã hóa SHA-256)
2. Bảo mật chống lộ mật khẩu: Không bao giờ trả mật khẩu về trình duyệt
3. Ẩn thông tin Email, chỉ hiển thị "Xin chào [Tên nhân viên]"
4. Trang Admin quản trị Whitelist và cấp mật khẩu riêng cho từng nhân viên
"""

import os
import io
import csv
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import database

# Khởi tạo DB
database.init_db()

app = FastAPI(title="Enterprise TimeClock SaaS Pro", version="3.9.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

ADMIN_SECRET_PASSWORD = os.environ.get("ADMIN_SECRET_PASSWORD", "admin@saas2026")
ADMIN_SESSIONS = set()

# =====================================================================
# PYDANTIC SCHEMAS
# =====================================================================
class EmployeeLoginRequest(BaseModel):
    email: str
    password: str

class AddAllowedEmailRequest(BaseModel):
    email: str
    employee_name: str
    password: str
    role: Optional[str] = "NHÂN VIÊN"

class AdminLoginRequest(BaseModel):
    password: str

class UpdateGoogleFormsRequest(BaseModel):
    branch_id: int = 1
    work_in_url: str
    work_out_url: str

# =====================================================================
# 1. API ĐĂNG NHẬP EMAIL + MẬT KHẨU (XÁC THỰC BẢO MẬT PHÍA SERVER)
# =====================================================================
@app.post("/api/auth/login")
def employee_login(req: EmployeeLoginRequest):
    """
    Xác thực Email và Mật Khẩu nhân viên.
    Mật khẩu được mã hóa và đối soát tại Server, KHÔNG BAO GIỜ lộ ra ngoài.
    """
    clean_email = req.email.strip().lower()
    clean_pass = req.password.strip()

    if not clean_email or "@" not in clean_email:
        raise HTTPException(status_code=400, detail="Vui lòng nhập địa chỉ Email hợp lệ!")
    if not clean_pass:
        raise HTTPException(status_code=400, detail="Vui lòng nhập mật khẩu tài khoản!")

    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM allowed_emails WHERE LOWER(email) = ?", (clean_email,))
    user = cursor.fetchone()

    # 1. Kiểm tra Email có trong danh sách Whitelist không
    if not user:
        conn.close()
        raise HTTPException(
            status_code=403,
            detail="TÀI KHOẢN CHƯA ĐƯỢC CẤP PHÉP: Email này chưa nằm trong danh sách nhân viên của doanh nghiệp!"
        )

    # 2. Kiểm tra tài khoản có bị khóa không
    if not user["is_active"]:
        conn.close()
        raise HTTPException(
            status_code=403,
            detail="TÀI KHOẢN ĐÃ BỊ KHÓA: Tài khoản này đang bị tạm ngưng quyền truy cập."
        )

    # 3. Kiểm tra Mật Khẩu (So khớp Hash SHA-256)
    expected_hash = database.hash_password(clean_pass)
    if user["password_hash"] != expected_hash:
        conn.close()
        raise HTTPException(
            status_code=401,
            detail="MẬT KHẨU KHÔNG CHÍNH XÁC: Vui lòng kiểm tra lại mật khẩu đăng nhập!"
        )

    # 4. Ghi nhận thời gian đăng nhập
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("UPDATE allowed_emails SET last_login = ? WHERE id = ?", (now_str, user["id"]))
    conn.commit()

    # Lấy thông tin link Google Form
    cursor.execute("SELECT * FROM branches WHERE id = 1")
    branch = cursor.fetchone()
    conn.close()

    branch_dict = dict(branch) if branch else {}
    session_token = str(uuid.uuid4())

    # TRẢ VỀ DUY NHẤT TÊN NHÂN VIÊN VÀ CHỨC VỤ - GIẤU KÍN EMAIL & MẬT KHẨU
    return {
        "success": True,
        "employee_name": user["employee_name"],
        "role": user["role"],
        "session_token": session_token,
        "google_form_work_in": branch_dict.get("google_form_work_in"),
        "google_form_work_out": branch_dict.get("google_form_work_out"),
        "welcome_text": f"Xin chào {user['employee_name']}"
    }

# =====================================================================
# 2. API TRẠNG THÁI HỆ THỐNG & ĐỒNG BỘ THỜI GIAN THỰC
# =====================================================================
@app.get("/api/system/status")
def get_system_status(branch_id: int = 1):
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM branches WHERE id = ?", (branch_id,))
    branch = cursor.fetchone()
    conn.close()

    branch_dict = dict(branch) if branch else {}
    now = datetime.now()

    return {
        "server_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "server_epoch_ms": int(now.timestamp() * 1000),
        "branch": {
            "name": branch_dict.get("branch_name"),
            "google_form_work_in": branch_dict.get("google_form_work_in"),
            "google_form_work_out": branch_dict.get("google_form_work_out")
        }
    }

# =====================================================================
# 3. API QUẢN TRỊ ADMIN MÁY CHỦ (WHITELIST & GOOGLE FORM)
# =====================================================================
@app.post("/api/admin/login")
def admin_login(req: AdminLoginRequest):
    if req.password.strip() == ADMIN_SECRET_PASSWORD:
        token = str(uuid.uuid4())
        ADMIN_SESSIONS.add(token)
        return {"success": True, "token": token, "message": "Xác thực máy chủ thành công!"}
    raise HTTPException(status_code=401, detail="Mật khẩu máy chủ không chính xác! Truy cập bị từ chối.")

@app.get("/api/admin/allowed-emails")
def get_allowed_emails():
    conn = database.get_connection()
    cursor = conn.cursor()
    # Tuyệt đối không chọn password_hash ra ngoài để đảm bảo an ninh
    cursor.execute("SELECT id, email, employee_name, role, is_active, last_login, added_at FROM allowed_emails ORDER BY id DESC")
    emails = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"allowed_emails": emails}

@app.post("/api/admin/allowed-emails")
def add_allowed_email(req: AddAllowedEmailRequest):
    email = req.email.strip().lower()
    name = req.employee_name.strip()
    raw_pass = req.password.strip()
    role = req.role.strip() or "NHÂN VIÊN"

    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Email không hợp lệ!")
    if not name:
        raise HTTPException(status_code=400, detail="Vui lòng nhập họ tên nhân viên!")
    if not raw_pass:
        raise HTTPException(status_code=400, detail="Vui lòng đặt mật khẩu cho nhân viên!")

    pass_hash = database.hash_password(raw_pass)

    conn = database.get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO allowed_emails (email, employee_name, password_hash, role, is_active)
            VALUES (?, ?, ?, ?, 1)
        """, (email, name, pass_hash, role))
        conn.commit()
    except Exception:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Email '{email}' đã tồn tại trong danh sách cấp phép!")

    conn.close()
    return {"success": True, "message": f"Đã cấp phép và đặt mật khẩu thành công cho nhân viên: {name}"}

@app.delete("/api/admin/allowed-emails/{email_id}")
def delete_allowed_email(email_id: int):
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM allowed_emails WHERE id = ?", (email_id,))
    conn.commit()
    conn.close()
    return {"success": True, "message": "Đã xóa nhân viên khỏi danh sách cấp phép!"}

@app.post("/api/admin/allowed-emails/{email_id}/toggle")
def toggle_allowed_email(email_id: int):
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT is_active FROM allowed_emails WHERE id = ?", (email_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy nhân viên!")

    new_status = 0 if row["is_active"] else 1
    cursor.execute("UPDATE allowed_emails SET is_active = ? WHERE id = ?", (new_status, email_id))
    conn.commit()
    conn.close()
    return {"success": True, "is_active": new_status, "message": "Đã cập nhật trạng thái hoạt động!"}

@app.post("/api/admin/update-forms")
def update_google_forms(req: UpdateGoogleFormsRequest):
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE branches 
        SET google_form_work_in = ?, google_form_work_out = ?
        WHERE id = ?
    """, (req.work_in_url.strip(), req.work_out_url.strip(), req.branch_id))
    conn.commit()
    conn.close()
    return {"success": True, "message": "Đã cập nhật liên kết Google Form thành công!"}

# =====================================================================
# 4. SERVE STATIC HTML PAGES
# =====================================================================
@app.get("/", response_class=HTMLResponse)
def serve_kiosk_ui():
    index_path = os.path.join(STATIC_DIR, "index.html")
    return FileResponse(index_path)

@app.get("/admin", response_class=HTMLResponse)
def serve_admin_ui():
    admin_path = os.path.join(STATIC_DIR, "admin.html")
    return FileResponse(admin_path)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    print("\n" + "="*70)
    print(">> ENTERPRISE TIMECLOCK SAAS PRO V3.9 RUNNING")
    print(f">> Server listening on: http://0.0.0.0:{port}")
    print("="*70 + "\n")
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
