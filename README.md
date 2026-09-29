# ENTERPRISE TIMECLOCK SAAS PRO (V5.0 SECURE CLOUD EDITION)

Hệ thống phần mềm Kiosk Chấm Công & Điểm Danh Đa Doanh Nghiệp (Multi-Tenant SaaS) xây dựng trên nền tảng **FastAPI**, **PostgreSQL / SQLite**, và giao diện **HTML5 / CSS3 / Vanilla JS** tối ưu tốc độ.

---

## 🏗️ 1. KIẾN TRÚC HỆ THỐNG 3 TẦNG

```text
┌──────────────────────────────────────────────────────────────────┐
│                   SUPER ADMIN (Chủ phần mềm)                     │
│        /super-admin • Xác thực Bearer Token (băm SHA-256)        │
│  - Cấp quyền / Khóa bản quyền tức thì (Kill-Switch)              │
│  - Điều chỉnh gói cước (Enterprise/Pro/Basic) & Gia hạn ngày     │
│  - Đổi mật khẩu Super Admin (băm bcrypt)                         │
└────────────────────────────────┬─────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│             GIÁM ĐỐC CƠ SỞ / CHỦ QUÁN (Khách hàng)               │
│               /?tenant=<mã-quán> • Nút [⚙️ Cài Đặt]               │
│  - Kích hoạt Kiosk 1 lần duy nhất bằng mật khẩu Giám Đốc         │
│  - Tự quản lý và dán link Google Form Vào Ca / Tan Ca            │
│  - Hệ thống tự chuẩn hóa link sang /viewform?embedded=true       │
│  - Tự đổi mật khẩu Giám Đốc                                      │
└────────────────────────────────┬─────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│                     NHÂN VIÊN CHẤM CÔNG                          │
│               /?tenant=<mã-quán> • Màn hình Kiosk                │
│  - Hoạt động tự động 24/7 (Không cần quản lý mở ca)              │
│  - Chạm thẻ WORK IN / WORK OUT (Phím tắt: [ I ] / [ O ])         │
│  - Nhúng Google Form full-screen ghi nhận giờ & ảnh điểm danh    │
│  - Cơ chế Device Token: Chỉ hiển thị form khi máy đã kích hoạt   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 🛡️ 2. BẢO MẬT & ĐỘ ỔN ĐỊNH CAO CẤP (V5.0)

1. **Xác thực Bearer Token Độc Lập**:
   - Toàn bộ API quản trị `/api/super-admin/*` và `/api/director/*` bắt buộc có header `Authorization: Bearer <token>`.
   - Token ngẫu nhiên (32 bytes) được băm bằng SHA-256 trước khi lưu vào bảng `sessions` kèm thời hạn `expires_at`.
2. **Kiosk Device Token (Phần Cứng Kiosk)**:
   - Khi Giám Đốc kích hoạt Kiosk lần đầu, server cấp một `device_token` lưu băm trong bảng `kiosk_devices`.
   - Endpoint `/api/kiosk/status` chỉ trả về link Google Form khi request gửi kèm `X-Device-Token` hợp lệ.
3. **Mã Hóa Mật Khẩu Chuẩn Bcrypt & Tự Động Nâng Cấp**:
   - Toàn bộ mật khẩu Super Admin và Giám Đốc được băm bằng thuật toán `bcrypt` (salt rounds 12).
   - Hệ thống tự động phát hiện các hash SHA-256 cũ khi đăng nhập thành công và tự nâng cấp lên bcrypt mà không làm gián đoạn người dùng.
4. **Chống Tấn Công Dò Mật Khẩu (Brute-Force Rate Limiting)**:
   - Tự động theo dõi số lần đăng nhập sai theo IP (`ip:<client_ip>`) và theo tài khoản.
   - Khóa tạm thời 15 phút nếu nhập sai quá 5 lần liên tiếp (HTTP 429 Too Many Requests).
5. **Kiểm Tra Bản Quyền & Thời Gian Hết Hạn (`expires_at`)**:
   - Endpoint `/api/kiosk/status` tự động so khớp `expires_at` với ngày hiện tại; nếu hết hạn sẽ lập tức khóa Kiosk như trạng thái `SUSPENDED`.
6. **Chuẩn Hóa Link Google Form Thông Minh**:
   - Khi Giám Đốc lưu link, server tự chuẩn hóa mọi link Google Form sang định dạng nhúng `/viewform?embedded=true`.
   - Báo lỗi rõ ràng nếu link nhập vào không thuộc domain `docs.google.com/forms` hoặc `forms.gle`.
7. **Connection Pool Cho PostgreSQL**:
   - Sử dụng `psycopg2.pool.ThreadedConnectionPool` khi chạy với Cloud Database (Neon / Supabase), tự động tái sử dụng kết nối an toàn.
8. **Chuẩn Hóa Tenant Code**:
   - Mọi mã định danh tenant đều được tự động chuẩn hóa về chữ thường (`lowercase`) để tránh xung đột URL.

---

## ⚙️ 3. BIẾN MÔI TRƯỜNG (ENVIRONMENT VARIABLES)

| Tên Biến | Ý Nghĩa | Giá Trị Mặc Định / Ví Dụ |
| :--- | :--- | :--- |
| `DATABASE_URL` | Chuỗi kết nối PostgreSQL (Neon, Supabase, Render Postgres). Bỏ trống sẽ dùng SQLite cục bộ (`timeclock_saas.db`). | `postgresql://user:pass@host/db?sslmode=require` |
| `SUPER_ADMIN_PASSWORD` | Mật khẩu khởi tạo cho Super Admin nếu chưa đổi trong DB. | Do hệ thống sinh ngẫu nhiên hoặc đặt riêng |
| `PORT` | Cổng lắng nghe của máy chủ Web. | `10000` (Render) hoặc `8000` (Local) |

---

## 📁 4. CẤU TRÚC THƯ MỤC CHUẨN

```text
timeclock-saas-enterprise/
├── server.py              # FastAPI Server V5.0: Bearer Auth, Kiosk Device Token, Rate Limiting, API
├── database.py            # Database Engine V5.0: Postgres Pool, Bcrypt, Sessions, Idempotent Migrations
├── requirements.txt       # fastapi, uvicorn, pydantic, psycopg2-binary, bcrypt
├── render.yaml            # Cấu hình tự động triển khai lên Render Cloud
├── .gitignore             # Loại bỏ *.db, .env, __pycache__
├── index.html             # Giao diện Kiosk Chấm Công 24/7 & Cài Đặt Giám Đốc
├── super_admin.html       # Trung Tâm Kiểm Soát Bản Quyền SaaS (Super Admin)
└── static/
    ├── index.html         # Bản sao tĩnh Kiosk
    └── super_admin.html   # Bản sao tĩnh Super Admin
```

---

## 🚀 5. KHỞI CHẠY & KIỂM THỬ

### Chạy cục bộ:
```bash
pip install -r requirements.txt
python server.py
```
- Mở Kiosk: `http://localhost:8000/?tenant=coffee-house`
- Mở Super Admin: `http://localhost:8000/super-admin`

### Kiểm thử tự động:
```bash
python -m pytest test_security_lifecycle.py
```
