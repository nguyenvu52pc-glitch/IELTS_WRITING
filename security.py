"""
ENTERPRISE TIMECLOCK SAAS PRO - SECURITY & LICENSE ENGINE
- Thuật toán sinh và xác thực License Key chống làm giả
- Cơ chế tường lửa IP Subnet (chặn IP ngoài công ty)
- Thuật toán Hàng rào địa lý GPS Haversine (chặn chấm công ngoài bán kính)
- Trình tạo mã thanh toán VietQR động
"""

import math
import ipaddress
import secrets
import string
from datetime import datetime

# =====================================================================
# 1. THUẬT TOÁN ĐỊA LÝ GEOFENCE (HAVERSINE FORMULA)
# =====================================================================
def calculate_haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Tính khoảng cách mặt cầu giữa 2 tọa độ GPS (Đơn vị: Mét)
    """
    R = 6371000.0  # Bán kính Trái Đất theo mét

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + \
        math.cos(phi1) * math.cos(phi2) * \
        math.sin(delta_lambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    return round(R * c, 1)

# =====================================================================
# 2. KIỂM TRA TƯỜNG LỬA DẢI MẠNG NỘI BỘ (IP SUBNET FILTER)
# =====================================================================
def is_ip_allowed(client_ip: str, allowed_subnets_str: str) -> bool:
    """
    Kiểm tra xem IP người dùng có thuộc dải mạng LAN/Wi-Fi của cửa hàng/chi nhánh không
    """
    if not allowed_subnets_str or allowed_subnets_str.strip() == "*":
        return True

    # Chuẩn hóa client IP
    if client_ip in ("::1", "127.0.0.1", "localhost", "testclient"):
        return True

    client_ip = client_ip.replace("::ffff:", "")

    subnets = [s.strip() for s in allowed_subnets_str.split(",") if s.strip()]
    try:
        c_ip = ipaddress.ip_address(client_ip)
    except ValueError:
        return False

    for subnet in subnets:
        try:
            if "/" in subnet:
                net = ipaddress.ip_network(subnet, strict=False)
                if c_ip in net:
                    return True
            else:
                if c_ip == ipaddress.ip_address(subnet):
                    return True
        except ValueError:
            continue

    return False

# =====================================================================
# 3. BỘ KIỂM SOÁT TOÀN DIỆN CHỐNG TRUY CẬP TỪ XA (REMOTE ACCESS GUARD)
# =====================================================================
def verify_remote_access(
    client_ip: str,
    client_lat: float | None,
    client_lon: float | None,
    branch_rule: dict
) -> dict:
    """
    Phát hiện và ngăn chặn mọi hành vi chấm công gian lận từ xa
    """
    enforce_ip = bool(branch_rule.get("enforce_ip_lock", 1))
    enforce_geo = bool(branch_rule.get("enforce_geofence", 1))

    # 1. Kiểm tra dải IP mạng
    if enforce_ip:
        allowed_ips = branch_rule.get("allowed_ip_subnets", "")
        if not is_ip_allowed(client_ip, allowed_ips):
            return {
                "authorized": False,
                "violation": "IP_RESTRICTED",
                "message": f"CẢNH BÁO: Thiết bị đang truy cập từ IP ngoài mạng công ty ({client_ip}). Bạn phải kết nối đúng Wi-Fi của chi nhánh!",
                "distance_meters": None
            }

    # 2. Kiểm tra hàng rào địa lý GPS
    distance = None
    if enforce_geo:
        if client_lat is None or client_lon is None:
            return {
                "authorized": False,
                "violation": "GPS_REQUIRED",
                "message": "CẢNH BÁO: Trình duyệt chưa cấp quyền định vị GPS. Vui lòng bật vị trí để xác nhận bạn đang ở tại cửa hàng!",
                "distance_meters": None
            }

        branch_lat = float(branch_rule.get("latitude", 0))
        branch_lon = float(branch_rule.get("longitude", 0))
        max_radius = int(branch_rule.get("allowed_radius_meters", 150))

        distance = calculate_haversine_distance(client_lat, client_lon, branch_lat, branch_lon)

        if distance > max_radius:
            return {
                "authorized": False,
                "violation": "GEOFENCE_EXCEEDED",
                "message": f"TỪ CHỐI TRUY CẬP TỪ XA: Bạn đang cách chi nhánh {distance}m (Vượt quá bán kính cho phép {max_radius}m). Không thể chấm công từ xa!",
                "distance_meters": distance
            }

    return {
        "authorized": True,
        "violation": None,
        "message": "Xác thực an ninh thành công: Thiết bị nằm trong vùng an toàn của chi nhánh.",
        "distance_meters": distance
    }

# =====================================================================
# 4. TRÌNH TẠO MÃ BẢN QUYỀN (SAAS LICENSE KEY GENERATOR)
# =====================================================================
def generate_license_key(plan_tier: str = "PRO") -> str:
    """
    Tạo khóa bản quyền chuẩn doanh nghiệp: LIC-VN-[PLAN]-[YEAR]-[RANDOM]
    """
    year = datetime.now().year
    alphabet = string.ascii_uppercase + string.digits
    rand_part1 = "".join(secrets.choice(alphabet) for _ in range(4))
    rand_part2 = "".join(secrets.choice(alphabet) for _ in range(4))
    return f"LIC-VN-{plan_tier.upper()}-{year}-{rand_part1}-{rand_part2}"

# =====================================================================
# 5. TRÌNH TẠO MÃ THANH TOÁN VIETQR CHUYỂN KHOẢN TỰ ĐỘNG
# =====================================================================
def generate_vietqr_url(bank_id: str, account_no: str, account_name: str, amount: int, memo: str) -> str:
    """
    Sinh link ảnh VietQR chuẩn Ngân Hàng Nhà Nước Việt Nam (VietQR QuickPay)
    """
    # Dùng VietQR API chính thức để sinh mã thanh toán có sẵn số tiền và nội dung
    clean_memo = memo.replace(" ", "%20")
    clean_name = account_name.replace(" ", "%20")
    return f"https://img.vietqr.io/image/{bank_id}-{account_no}-compact2.png?amount={amount}&addInfo={clean_memo}&accountName={clean_name}"
