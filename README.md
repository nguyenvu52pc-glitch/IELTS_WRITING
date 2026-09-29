# ENTERPRISE TIMECLOCK SAAS PRO (V4.2 CLOUD EDITION)

> **Hệ Thống Phần Mềm Chấm Công & Điểm Danh Đa Doanh Nghiệp (Multi-Tenant SaaS)**  
> - **Super Admin (Bạn)**: Cấp quyền, khóa bản quyền tức thì, đổi mật khẩu Super Admin, giám sát toàn bộ khách hàng.  
> - **Giám Đốc Cửa Hàng (Khách Mua)**: Kích hoạt Kiosk 1 lần duy nhất, tự quản lý link Google Form Vào Ca / Tan Ca và đổi mật khẩu Giám Đốc.  
> - **Nhân Viên**: Bấm chấm công 24/7 trực tiếp trên màn hình Kiosk (không cần đăng nhập, không cần tài khoản Quản Lý).  
> - **Lưu Trữ Vĩnh Viễn (Cloud Persistence)**: Tích hợp PostgreSQL (Neon.tech / Supabase / Render Postgres) không bao giờ bị mất dữ liệu khi server Render ngủ đông hoặc khởi động lại.

---

## 🌟 1. GIẢI QUYẾT TRIỆT ĐỂ VẤN ĐỀ DỮ LIỆU BỊ RESET TRÊN RENDER

### Tại sao dữ liệu cục bộ (SQLite) bị mất sau một thời gian không dùng?
Render (gói Free) sử dụng cơ chế **Ephemeral Filesystem (ổ đĩa tạm)**:
- Sau 15 phút không có người truy cập, Render sẽ tự động đưa server vào chế độ ngủ (Spin down).
- Khi có lượt truy cập mới, Render khởi động một container mới tinh dựa trên mã nguồn commit trên GitHub.
- Mọi dữ liệu ghi vào file SQLite `timeclock_saas.db` trong phiên chạy trước sẽ bị thay thế bằng file gốc trên GitHub!

### Giải pháp tối ưu: Kết nối Cloud Database PostgreSQL miễn phí (100% vĩnh viễn)
Phần mềm đã được nâng cấp engine `database.py` tự động chuyển sang PostgreSQL khi có biến môi trường `DATABASE_URL`:
1. Đăng ký tài khoản miễn phí tại **[Neon.tech](https://neon.tech)** hoặc **[Supabase.com](https://supabase.com)**.
2. Tạo 1 database mới (chọn PostgreSQL miễn phí).
3. Copy chuỗi kết nối (Connection String), ví dụ:  
   `postgresql://neondb_owner:xyz...@ep-cool-rain-123456.us-east-2.aws.neon.tech/neondb?sslmode=require`
4. Vào Render -> Chọn Web Service của bạn -> Tab **Environment** -> Bấm **Add Environment Variable**:
   - **Key**: `DATABASE_URL`
   - **Value**: Dán chuỗi kết nối vừa copy ở trên.
5. Render sẽ tự redeploy. Toàn bộ tài khoản, mật khẩu, bản quyền, link Google Form sẽ được lưu vĩnh viễn trên Cloud, không bao giờ bị mất dữ liệu nữa!

---

## 🔑 2. CƠ CHẾ VẬN HÀNH 3 CẤP

### 👑 Cấp 1: Super Admin (Dành cho Bạn - Nhà Cung Cấp SaaS)
- **Đường dẫn**: `https://<ten-mien-render>.onrender.com/super-admin`
- **Mật khẩu mặc định**: `owner@saas2026`
- **Chức năng**:
  - **Đổi Mật Khẩu Super Admin**: Nút 🔑 trực tiếp trên giao diện, mật khẩu mới được lưu bền vững.
  - **Tạo Doanh Nghiệp Mới**: Nhập Tên Công Ty, Mã Tenant (ví dụ `the-coffee-house`), và cấp Mật Khẩu Giám Đốc ban đầu.
  - **Khóa / Mở Bản Quyền (Kill-Switch)**: Nút bật/tắt bản quyền tức thì. Nếu bị khóa, Kiosk của khách hàng lập tức chuyển sang màn hình đỏ cảnh báo và chặn toàn bộ thao tác chấm công.
  - **Chỉ Báo Cơ Sở Dữ Liệu**: Hiển thị trạng thái đang chạy trên Đám Mây (PostgreSQL) hay Cục Bộ (SQLite).

### 🏢 Cấp 2: Giám Đốc Cơ Sở (Khách Hàng Mua Web)
- **Đường dẫn Kiosk**: `https://<ten-mien-render>.onrender.com/?tenant=ma-tenant`
- **Kích Hoạt Thiết Bị (1 Lần Duy Nhất)**:
  - Khi mở web lần đầu trên thiết bị/máy tính bàn/tablet của quán, Kiosk yêu cầu nhập Mật Khẩu Giám Đốc.
  - Nhập thành công 1 lần -> Kiosk được mở khóa vĩnh viễn trên trình duyệt đó.
- **Nút "⚙️ Cài Đặt (Giám Đốc)" ở góc trên bên phải**:
  - Yêu cầu nhập mật khẩu Giám Đốc để mở cấu hình.
  - Tự đổi Tên Doanh Nghiệp, Tên Cơ Sở.
  - Tự dán link Google Form `WORK IN` (Vào Ca) & `WORK OUT` (Tan Ca).
  - Tự đổi Mật Khẩu Giám Đốc bất cứ lúc nào.
  - Tùy chọn khóa lại thiết bị Kiosk nếu cần.

### 👥 Cấp 3: Nhân Viên Chấm Công
- Không cần tài khoản Quản Lý mở ca.
- Kiosk luôn sẵn sàng 24/7.
- Chỉ cần chạm vào thẻ to **WORK IN** hoặc **WORK OUT** (hoặc ấn phím tắt `I` / `O`).
- Google Form hiển thị full màn hình để nhân viên điểm danh và chụp ảnh gửi trực tiếp về Google Sheets của Giám Đốc.

---

## 🚀 3. HƯỚNG DẪN CẬP NHẬT LÊN GITHUB & RENDER

Chạy lệnh hoặc tải các file sau lên GitHub của bạn:
1. `database.py` (Hỗ trợ PostgreSQL + SQLite)
2. `server.py` (Toàn bộ API V4.2)
3. `requirements.txt` (Đã thêm `psycopg2-binary`)
4. `index.html` & `static/index.html` (Kiosk tự động 24/7 kích hoạt 1 lần)
5. `super_admin.html` & `static/super_admin.html` (Quản trị Super Admin đổi mật khẩu)
6. `render.yaml`
