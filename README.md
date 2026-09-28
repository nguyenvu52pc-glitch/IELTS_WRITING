# ENTERPRISE TIMECLOCK SAAS PRO (COMMERCIAL EDITION V3.5)
> **Phần mềm Chấm Công & Điểm Danh Đa Doanh Nghiệp Thương Mại**  
> Tích hợp Khóa Bản Quyền Thanh Toán (Paywall VietQR) & Tường Lửa Chống Chấm Công Từ Xa (IP & GPS Geofencing)

---

## 🎯 1. ĐẶC ĐIỂM THƯƠNG MẠI NỔI BẬT

### 💳 A. Cơ Chế Khóa Bản Quyền Bắt Buộc Thanh Toán (Paywall & License Key)
- **Tự động khóa phần mềm (Screen Lockout)** khi doanh nghiệp chưa kích hoạt hoặc gói cước hết hạn sử dụng.
- **3 Gói dịch vụ định sẵn**:
  - **Gói Cơ Bản (BASIC)**: 299.000 VNĐ/tháng (Tối đa 2 chi nhánh).
  - **Gói Chuyên Nghiệp (PRO)**: 599.000 VNĐ/tháng (Tối đa 10 chi nhánh, Chống từ xa IP/GPS, Chụp ảnh tại quầy).
  - **Gói Tập Đoàn (ENTERPRISE)**: 1.199.000 VNĐ/tháng (Không giới hạn chi nhánh, API tích hợp).
- **Cổng thanh toán tự động VietQR**: Sinh mã QR động chuẩn ngân hàng, người dùng chỉ cần mở app ngân hàng quét mã là hệ thống tự động ghi nhận và mở khóa ngay.
- **Trình tạo License Key**: Bạn (Nhà phát triển) có thể sinh mã bản quyền dạng `LIC-VN-PRO-2026-XXXX-YYYY` để bán trực tiếp cho khách hàng.

### 🛡️ B. Tường Lửa Ngăn Chặn Truy Cập Từ Xa Trái Phép (Anti-Remote Fraud)
- **Kiểm soát dải mạng nội bộ (IP Subnet Whitelist)**: Chỉ cho phép các thiết bị kết nối vào mạng Wi-Fi hoặc dải IP của cửa hàng (ví dụ: `192.168.1.0/24`, `10.0.0.0/8`). Nhân viên mở link từ nhà hoặc 4G cá nhân sẽ lập tức bị hệ thống từ chối truy cập.
- **Hàng rào địa lý GPS (Geofencing Haversine Guard)**: Tự động đo khoảng cách giữa thiết bị và tọa độ GPS chi nhánh. Nếu khoảng cách > 150m (hoặc bán kính bạn đặt), hai nút Work In / Work Out sẽ bị khóa ngay lập tức và phát cảnh báo đỏ.
- **Chống gian lận giờ máy tính (Atomic Server Time)**: Giờ hiển thị trên đồng hồ và giờ ghi nhận vào cơ sở dữ liệu luôn lấy từ Máy Chủ (Server), nhân viên có đổi giờ trên máy tính cũng không thể gian lận giờ làm.
- **Xác thực khuôn mặt tại quầy (WebCam Snapshot)**: Tích hợp camera chụp ảnh nhân viên tại thời điểm bấm nút để quản lý đối soát.

---

## 🚀 2. HƯỚNG DẪN KHỞI CHẠY HỆ THỐNG

### Cách 1: Chạy bằng file `start.bat` (Khuyên dùng)
- Nhấp đúp chuột vào file `start.bat`. Hệ thống sẽ tự động khởi động máy chủ FastAPI và mở hai giao diện:
  - **Màn hình Kiosk Điểm Danh (Dành cho nhân viên)**: `http://127.0.0.1:8000`
  - **Trung Tâm Quản Trị Bản Quyền (Dành cho bạn)**: `http://127.0.0.1:8000/admin`

### Cách 2: Chạy thủ công qua dòng lệnh Terminal
```powershell
cd "C:\Users\Nguyen Vu\.gemini\antigravity\scratch\timeclock-saas-enterprise"
python server.py
```

---

## 📂 3. CẤU TRÚC MÃ NGUỒN HOÀN TOÀN ĐỘC LẬP
```text
timeclock-saas-enterprise/
├── server.py              # Máy chủ FastAPI: License API, VietQR, Chống truy cập từ xa, Điểm danh
├── database.py            # SQLite Engine: Doanh nghiệp, Bản quyền, Chi nhánh, Lịch sử điểm danh
├── security.py            # Thuật toán: IP subnet, GPS Haversine, Sinh mã bản quyền, VietQR
├── static/
│   ├── css/
│   │   └── style.css      # Giao diện Đỏ - Đen - Trắng đẳng cấp SaaS thương mại
│   ├── js/
│   │   └── kiosk.js       # Bộ điều khiển Kiosk: Đồng hồ nguyên tử, Paywall, WebCam, Anti-Remote
│   ├── index.html         # Màn hình Kiosk Chấm Công & Paywall
│   └── admin.html         # Bảng Quản Trị Bản Quyền & Giấy Phép SaaS
├── start.bat              # File kích hoạt 1-click cho Windows
└── README.md              # Tài liệu chi tiết thương mại
```
