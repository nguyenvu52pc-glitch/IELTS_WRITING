"""
Test cốt lõi (chạy: python test_core.py hoặc pytest test_core.py)
- Dùng file DB TẠM, KHÔNG BAO GIỜ đụng vào DB thật / DATABASE_URL.
"""
import os, sys, tempfile, sqlite3, hashlib, time

_tmp = tempfile.mkdtemp()
os.environ["TIMECLOCK_DB"] = os.path.join(_tmp, "test.db")
os.environ.pop("DATABASE_URL", None)

# Dựng sẵn DB kiểu CŨ (branch_code UNIQUE + chi nhánh mồ côi + mật khẩu băm kiểu V4) để thử migration
_c = sqlite3.connect(os.environ["TIMECLOCK_DB"])
_c.executescript("""
CREATE TABLE enterprises (id INTEGER PRIMARY KEY AUTOINCREMENT, company_name TEXT NOT NULL, license_key TEXT UNIQUE NOT NULL,
  plan_tier TEXT NOT NULL DEFAULT 'PRO', status TEXT NOT NULL DEFAULT 'ACTIVE', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  expires_at TIMESTAMP NOT NULL, tenant_code TEXT DEFAULT 'default', director_password_hash TEXT DEFAULT '');
CREATE TABLE branches (id INTEGER PRIMARY KEY AUTOINCREMENT, enterprise_id INTEGER NOT NULL, branch_name TEXT NOT NULL,
  branch_code TEXT UNIQUE NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  google_form_work_in TEXT DEFAULT '', google_form_work_out TEXT DEFAULT '');
""")
_v4 = hashlib.sha256(("saas_salt_novalux_2026_xyz" + "matkhau_cu").encode()).hexdigest()
_c.execute("INSERT INTO enterprises (company_name,license_key,expires_at,tenant_code,director_password_hash) VALUES ('Quan Cu','K1','2099-01-01','quan-cu',?)", (_v4,))
_c.execute("INSERT INTO branches (enterprise_id,branch_name,branch_code) VALUES (1,'CN cu','Cổng Điểm Danh Chi Nhánh 1')")
_c.execute("INSERT INTO branches (enterprise_id,branch_name,branch_code) VALUES (99,'mo coi','Cổng Điểm Danh Chi Nhánh 2')")
_c.commit(); _c.close()

os.environ["SUPER_ADMIN_PASSWORD"] = "sa_test_pw"
from fastapi.testclient import TestClient
import database
from server import app
client = TestClient(app)

def H(t): return {"Authorization": f"Bearer {t}"}
def login_sa():
    r = client.post("/api/super-admin/login", json={"password": "sa_test_pw"}); assert r.status_code == 200, r.text
    return r.json()["token"]
def create(sa, code, pw="pw123456"):
    return client.post("/api/super-admin/enterprises", headers=H(sa), json={"company_name": code.upper(), "tenant_code": code, "director_password": pw, "plan_tier": "PRO", "days_valid": 30})
def dir_login(code, pw="pw123456", ip="1.1.1.1"):
    return client.post("/api/director/login", headers={"X-Forwarded-For": ip}, json={"tenant_code": code, "password": pw})

def test_migration_and_legacy_login():
    # DB cũ: branch mồ côi bị dọn, UNIQUE bị gỡ, mật khẩu V4 vẫn đăng nhập được và tự nâng lên bcrypt
    assert database.query("SELECT * FROM branches WHERE enterprise_id = 99") == []
    r = dir_login("quan-cu", "matkhau_cu"); assert r.status_code == 200, r.text
    assert database.query_one("SELECT director_password_hash h FROM enterprises WHERE tenant_code='quan-cu'")["h"].startswith("$2b$10$")

def test_no_token_401():
    for m, p in [("get", "/api/super-admin/enterprises"), ("delete", "/api/super-admin/enterprises/1"), ("get", "/api/director/config?tenant=quan-cu")]:
        assert getattr(client, m)(p).status_code == 401

def test_create_many_tenants_atomic():
    sa = login_sa()
    for c in ["shop-a", "shop-b", "shop-c"]:
        assert create(sa, c).status_code == 200
    assert create(sa, "shop-a").status_code == 400            # trùng mã -> báo lỗi
    assert database.query("SELECT tenant_code FROM enterprises WHERE id NOT IN (SELECT enterprise_id FROM branches)") == []  # không có công ty ma

def test_cross_tenant_blocked():
    sa = login_sa(); create(sa, "xa"); create(sa, "xb")
    ta = dir_login("xa").json()["token"]
    r = client.post("/api/director/update-config", headers=H(ta), json={"tenant_code": "xb", "company_name": "HACK", "branch_name": "x"})
    assert r.status_code == 403
    r = client.post("/api/director/change-password", headers=H(ta), json={"tenant_code": "xb", "old_password": "pw123456", "new_password": "newpass1"})
    assert r.status_code == 403
    assert database.query_one("SELECT company_name n FROM enterprises WHERE tenant_code='xb'")["n"] == "XB"
    assert client.post("/api/director/update-config", headers=H(ta), json={"tenant_code": "xa", "company_name": "XA moi", "branch_name": "CN"}).status_code == 200

def test_kiosk_device_and_form_link():
    sa = login_sa(); create(sa, "kiosk1")
    ta = dir_login("kiosk1").json()["token"]
    client.post("/api/director/update-config", headers=H(ta), json={"tenant_code": "kiosk1", "company_name": "K1", "branch_name": "CN", "work_in_url": "https://docs.google.com/forms/d/e/ABC123/edit"})
    assert client.get("/api/kiosk/status?tenant=kiosk1").json()["branch"]["google_form_work_in"] == ""       # chưa kích hoạt: không lộ link
    dev = client.post("/api/kiosk/activate", json={"tenant_code": "kiosk1", "password": "pw123456"}).json()["device_token"]
    d = client.get("/api/kiosk/status?tenant=kiosk1", headers={"X-Device-Token": dev}).json()
    assert d["is_device_activated"] and d["branch"]["google_form_work_in"].endswith("/viewform?embedded=true")

def test_suspend_delete_take_effect_immediately():
    sa = login_sa(); create(sa, "sus1")
    ent = database.query_one("SELECT id FROM enterprises WHERE tenant_code='sus1'")["id"]
    ta = dir_login("sus1").json()["token"]
    dev = client.post("/api/kiosk/activate", json={"tenant_code": "sus1", "password": "pw123456"}).json()["device_token"]
    assert client.get("/api/kiosk/status?tenant=sus1", headers={"X-Device-Token": dev}).json()["status"] == "ACTIVE"   # đưa vào cache
    client.post(f"/api/super-admin/enterprises/{ent}/toggle", headers=H(sa))
    assert client.get("/api/kiosk/status?tenant=sus1", headers={"X-Device-Token": dev}).json()["status"] == "SUSPENDED"  # cache đã bị xóa
    assert client.get("/api/director/config?tenant=sus1", headers=H(ta)).status_code == 401                              # phiên Giám Đốc bị hủy
    client.delete(f"/api/super-admin/enterprises/{ent}", headers=H(sa)); create(sa, "sus1")
    assert client.get("/api/kiosk/status?tenant=sus1", headers={"X-Device-Token": dev}).json()["is_device_activated"] is False  # token thiết bị cũ vô hiệu

def test_rate_limit_not_a_lockout_weapon():
    sa = login_sa(); create(sa, "rl1")
    for _ in range(6): dir_login("rl1", "sai", ip="6.6.6.6")
    assert dir_login("rl1", "sai", ip="6.6.6.6").status_code == 429    # kẻ tấn công bị khóa
    assert dir_login("rl1", "pw123456", ip="7.7.7.7").status_code == 200  # chủ quán thật (IP khác) vẫn vào được

def test_speed():
    sa = login_sa(); create(sa, "fast1")
    dev = client.post("/api/kiosk/activate", json={"tenant_code": "fast1", "password": "pw123456"}).json()["device_token"]
    n = {"q": 0}; oq, oe = database.query, database.execute
    database.query = lambda *a, **k: (n.__setitem__("q", n["q"] + 1), oq(*a, **k))[1]
    database.execute = lambda *a, **k: (n.__setitem__("q", n["q"] + 1), oe(*a, **k))[1]
    try:
        database.cache_clear()
        client.get("/api/kiosk/status?tenant=fast1", headers={"X-Device-Token": dev}); first = n["q"]
        n["q"] = 0
        for _ in range(50): client.get("/api/kiosk/status?tenant=fast1", headers={"X-Device-Token": dev})
        n["q"] = n["q"]
        rest = n["q"]
    finally:
        database.query, database.execute = oq, oe
    print(f"   kiosk status: lần đầu {first} truy vấn DB, 50 lần tiếp theo {rest} truy vấn")
    assert first <= 2 and rest == 0

if __name__ == "__main__":
    ok = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            t = time.perf_counter(); fn(); ok += 1
            print(f"[OK] {name}  ({1000*(time.perf_counter()-t):.0f} ms)")
    print(f"\n{ok} test qua.")
