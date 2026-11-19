IELTS READING MASTER PRO (V5.0 – SECURE LEARNING CLOUD EDITION)
Hệ thống nền tảng IELTS Reading Practice & Learning Management System được xây dựng nhằm hỗ trợ người học luyện tập kỹ năng đọc hiểu tiếng Anh theo chuẩn kỳ thi IELTS Academic và General Training.

Ứng dụng phát triển trên nền tảng FastAPI, PostgreSQL / SQLite, kết hợp giao diện HTML5 / CSS3 / Vanilla JavaScript, tối ưu tốc độ tải trang, khả năng tương thích đa thiết bị và trải nghiệm học tập trực tuyến.

🏗️ 1. KIẾN TRÚC HỆ THỐNG 3 TẦNG

text
┌──────────────────────────────────────────────────────────────────┐
│                    SUPER ADMIN (QUẢN TRỊ HỆ THỐNG)               │
│                    /super-admin                                  │
│              Xác thực Bearer Token – SHA-256                     │
│                                                                  │
│  - Quản lý tài khoản và phân quyền người dùng                    │
│  - Cấp quyền / Khóa tài khoản học viên                            │
│  - Quản lý gói học tập (Free / Pro / Premium)                    │
│  - Theo dõi hoạt động và thống kê toàn hệ thống                  │
│  - Điều chỉnh thời hạn sử dụng tài khoản                         │
│  - Quản lý ngân hàng đề thi IELTS Reading                        │
└────────────────────────────────┬─────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│                  TEACHER / CONTENT MANAGER                       │
│                  /teacher • Khu vực quản lý học tập              │
│                                                                  │
│  - Tạo và quản lý bộ đề IELTS Reading                            │
│  - Phân loại đề theo Academic / General Training                 │
│  - Quản lý Passage 1, Passage 2 và Passage 3                     │
│  - Tạo câu hỏi trắc nghiệm, True / False / Not Given             │
│  - Quản lý dạng bài Matching Headings, Gap Filling               │
│  - Cập nhật đáp án và lời giải chi tiết                          │
│  - Theo dõi kết quả và tiến độ học viên                          │
└────────────────────────────────┬─────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│                     STUDENT (HỌC VIÊN)                            │
│                     /reading • Khu vực luyện tập                 │
│                                                                  │
│  - Luyện tập IELTS Reading theo từng bài hoặc full test          │
│  - Giao diện đọc Passage kết hợp bảng câu hỏi                    │
│  - Hỗ trợ Highlight và lưu từ vựng                                │
│  - Đồng hồ đếm ngược 60 phút cho bài thi mô phỏng                 │
│  - Tự động lưu tiến độ và câu trả lời                             │
│  - Nộp bài và xem kết quả sau khi hoàn thành                      │
│  - Xem giải thích đáp án và phân tích lỗi sai                    │
│  - Theo dõi lịch sử luyện tập và tiến bộ cá nhân                 │
└──────────────────────────────────────────────────────────────────┘
📚 2. CÁC CHỨC NĂNG HỌC TẬP CHÍNH
2.1. IELTS Reading Practice Engine
Hệ thống cung cấp môi trường luyện thi mô phỏng cấu trúc bài thi IELTS Reading.

Hỗ trợ IELTS Academic Reading với 3 bài đọc và 40 câu hỏi.
Hỗ trợ IELTS General Training Reading.
Đồng hồ đếm ngược 60 phút cho bài thi mô phỏng.
Tự động đánh số câu hỏi từ 1 đến 40.
Hỗ trợ chuyển đổi giữa các Passage.
Cho phép đánh dấu câu hỏi cần xem lại.
Tự động lưu câu trả lời trong quá trình làm bài.
Cảnh báo khi thời gian làm bài sắp kết thúc.
2.2. Question Types – Các dạng câu hỏi IELTS
Hệ thống hỗ trợ những dạng bài phổ biến trong IELTS Reading:


Dạng bài	Chức năng
Multiple Choice	Chọn đáp án trắc nghiệm
True / False / Not Given	Xác định thông tin
Yes / No / Not Given	Nhận diện quan điểm tác giả
Matching Headings	Nối tiêu đề với đoạn văn
Matching Information	Tìm thông tin trong Passage
Matching Features	Ghép đặc điểm
Sentence Completion	Hoàn thành câu
Summary Completion	Điền từ vào bản tóm tắt
Note Completion	Hoàn thành ghi chú
Table Completion	Điền thông tin vào bảng
Short Answer Questions	Trả lời câu hỏi ngắn
2.3. Smart Vocabulary System
Highlight từ vựng trực tiếp trong Passage.
Lưu từ mới vào Personal Vocabulary.
Hiển thị nghĩa tiếng Việt và định nghĩa tiếng Anh.
Lưu ví dụ sử dụng từ trong ngữ cảnh.
Phân loại từ vựng theo chủ đề IELTS.
Theo dõi danh sách từ đã học và chưa thuộc.
2.4. IELTS Scoring & Performance Analytics
Tự động chấm điểm dựa trên đáp án chuẩn.
Tính số câu đúng và số câu sai.
Ước lượng band score IELTS Reading.
Thống kê kết quả theo từng dạng câu hỏi.
Phân tích những kỹ năng còn yếu.
Lưu lịch sử các bài thi đã hoàn thành.
Theo dõi tiến bộ qua biểu đồ theo thời gian.
Lưu ý: Band score được ước lượng dựa trên bảng quy đổi tham khảo; mức quy đổi thực tế có thể khác nhau tùy bài thi.

🛡️ 3. BẢO MẬT & ĐỘ ỔN ĐỊNH HỆ THỐNG (V5.0)
1. Xác thực Bearer Token độc lập
API quản trị /api/super-admin/* yêu cầu header Authorization: Bearer <token>.
API giáo viên /api/teacher/* yêu cầu xác thực và quyền truy cập phù hợp.
Token được sinh ngẫu nhiên 32 bytes.
Token được băm SHA-256 trước khi lưu vào bảng sessions.
Mỗi phiên đăng nhập có thời hạn expires_at.
2. Quản lý phiên đăng nhập học viên
Mỗi người dùng có phiên đăng nhập riêng.
Hỗ trợ đăng xuất và thu hồi token.
Tự động hết hạn phiên khi vượt quá thời gian quy định.
Ngăn chặn truy cập trái phép vào lịch sử và kết quả học tập.
3. Mã hóa mật khẩu bằng Bcrypt
Mật khẩu Super Admin, Teacher và Student được lưu dưới dạng bcrypt hash.
Sử dụng salt tự động.
Hỗ trợ nâng cấp mật khẩu từ SHA-256 cũ sang bcrypt sau khi đăng nhập thành công.
Không lưu mật khẩu dạng văn bản thuần trong database.
4. Chống tấn công dò mật khẩu (Brute-Force Protection)
Theo dõi số lần đăng nhập sai theo IP.
Theo dõi số lần đăng nhập sai theo tài khoản.
Tạm khóa đăng nhập 15 phút khi vượt quá 5 lần sai liên tiếp.
Trả về HTTP 429 Too Many Requests khi bị giới hạn.
5. Quản lý gói học tập và thời hạn sử dụng
Hỗ trợ các gói Free, Pro và Premium.
Kiểm tra trạng thái tài khoản trước khi truy cập nội dung.
Tự động khóa tính năng Premium khi tài khoản hết hạn.
Cho phép Super Admin gia hạn hoặc thu hồi quyền truy cập.
6. Bảo vệ dữ liệu học tập
Mỗi học viên chỉ được truy cập dữ liệu thuộc tài khoản của mình.
Kiểm tra quyền sở hữu bài thi và lịch sử làm bài ở phía server.
Hạn chế truy cập trực tiếp vào đáp án trước khi nộp bài.
Sử dụng cơ chế lưu bài làm an toàn để tránh mất dữ liệu khi tải lại trang.
7. Connection Pool cho PostgreSQL
Sử dụng psycopg2.pool.ThreadedConnectionPool.
Tái sử dụng kết nối database.
Hỗ trợ triển khai trên Neon, Supabase và Render PostgreSQL.
SQLite được sử dụng cho môi trường phát triển cục bộ.
8. Quản lý ngân hàng đề thi
Mỗi Passage và Question có ID riêng.
Hỗ trợ cập nhật nội dung mà không làm mất lịch sử bài thi.
Kiểm tra dữ liệu đầu vào trước khi lưu.
Hỗ trợ sao lưu và khôi phục ngân hàng đề.
⚙️ 4. BIẾN MÔI TRƯỜNG (ENVIRONMENT VARIABLES)

Tên biến	Ý nghĩa	Giá trị mặc định / Ví dụ
DATABASE_URL	Chuỗi kết nối PostgreSQL	postgresql://user:pass@host/db?sslmode=require
SUPER_ADMIN_PASSWORD	Mật khẩu khởi tạo Super Admin	Sinh ngẫu nhiên hoặc đặt riêng
PORT	Cổng máy chủ Web	8000 hoặc 10000
SECRET_KEY	Khóa bảo mật ứng dụng	Chuỗi ngẫu nhiên đủ mạnh
SESSION_EXPIRE_MINUTES	Thời hạn phiên đăng nhập	1440
MAX_LOGIN_ATTEMPTS	Số lần đăng nhập sai tối đa	5
LOCKOUT_MINUTES	Thời gian khóa tài khoản	15
📁 5. CẤU TRÚC THƯ MỤC CHUẨN

text
ielts-reading-master/
│
├── server.py                 # FastAPI Server V5.0
├── database.py               # Database Engine, Bcrypt, Sessions
├── requirements.txt          # Dependencies
├── render.yaml               # Cấu hình triển khai Render
├── .gitignore                # Loại bỏ file nhạy cảm
│
├── index.html                # Trang chủ IELTS Reading
├── login.html                # Đăng nhập học viên
├── register.html             # Đăng ký tài khoản
├── reading.html              # Giao diện luyện Reading
├── result.html               # Kết quả bài thi
├── vocabulary.html           # Sổ tay từ vựng
├── dashboard.html            # Dashboard học viên
│
├── teacher.html              # Quản lý đề thi
├── super_admin.html          # Quản trị hệ thống
│
├── static/
│   ├── css/
│   │   ├── style.css
│   │   ├── reading.css
│   │   └── dashboard.css
│   │
│   ├── js/
│   │   ├── app.js
│   │   ├── reading.js
│   │   ├── timer.js
│   │   ├── vocabulary.js
│   │   └── analytics.js
│   │
│   └── images/
│
├── data/
│   └── reading_passages.json  # Ngân hàng đề IELTS Reading
│
└── tests/
    ├── test_auth.py
    ├── test_reading.py
    ├── test_scoring.py
    └── test_security.py
🚀 6. KHỞI CHẠY & TRIỂN KHAI
6.1. Chạy cục bộ
Cài đặt thư viện:


bash
pip install -r requirements.txt
Khởi chạy máy chủ:


bash
python server.py
Truy cập hệ thống:

Trang chủ: http://localhost:8000/
Đăng nhập: http://localhost:8000/login
Luyện IELTS Reading: http://localhost:8000/reading
Teacher Dashboard: http://localhost:8000/teacher
Super Admin: http://localhost:8000/super-admin
6.2. Triển khai Cloud
Hệ thống hỗ trợ triển khai trên:

Render Cloud – Hosting FastAPI.
Neon PostgreSQL – Database đám mây.
Supabase – Quản lý cơ sở dữ liệu.
GitHub – Quản lý mã nguồn và phiên bản.
Quy trình triển khai:

Đẩy source code lên GitHub.
Kết nối GitHub với Render.
Cấu hình Environment Variables.
Kết nối PostgreSQL Database.
Deploy ứng dụng.
Kiểm tra API và giao diện trên môi trường Cloud.
6.3. Kiểm thử tự động
Chạy toàn bộ kiểm thử:


bash
python -m pytest tests/
Kiểm thử riêng từng chức năng:


bash
python -m pytest tests/test_auth.py
python -m pytest tests/test_reading.py
python -m pytest tests/test_scoring.py
python -m pytest tests/test_security.py
🎯 7. MỤC TIÊU PHÁT TRIỂN
IELTS Reading Master Pro hướng đến việc xây dựng một nền tảng luyện thi IELTS Reading toàn diện với các mục tiêu:

Practice Anywhere: Luyện IELTS Reading mọi lúc, mọi nơi.
Real Exam Experience: Mô phỏng trải nghiệm làm bài thi thực tế.
Smart Learning: Phân tích kết quả và nhận diện điểm yếu.
Vocabulary Development: Phát triển vốn từ vựng học thuật.
Performance Tracking: Theo dõi tiến độ và sự tiến bộ.
Secure Cloud Learning: Bảo vệ tài khoản và dữ liệu học tập.
IELTS READING MASTER PRO – READ SMARTER, PRACTICE BETTER, ACHIEVE YOUR TARGET BAND SCORE.
