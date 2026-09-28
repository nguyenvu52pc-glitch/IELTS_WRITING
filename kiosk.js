/**
 * ENTERPRISE TIMECLOCK SAAS PRO - KIOSK CONTROLLER (V3.9)
 * 1. Chống mở mã nguồn F12 / Inspect / Chuột phải
 * 2. Đăng nhập Email + Mật khẩu xác thực Backend
 * 3. Giấu hoàn toàn email, chỉ hiển thị "Xin chào [Tên]" trên thanh tác vụ
 * 4. Đồng hồ nguyên tử đồng bộ Server Time & mở Google Form
 */

// =====================================================================
// BẢO VỆ CHỐNG MỞ MÃ NGUỒN & THANH CÔNG CỤ DEVTOOLS (ANTI-INSPECT)
// =====================================================================
document.addEventListener("contextmenu", (e) => e.preventDefault());

document.addEventListener("keydown", (e) => {
  // Chặn F12
  if (e.key === "F12") {
    e.preventDefault();
    return false;
  }
  // Chặn Ctrl + Shift + I / J / C (Mở DevTools)
  if (e.ctrlKey && e.shiftKey && ["I", "i", "J", "j", "C", "c"].includes(e.key)) {
    e.preventDefault();
    return false;
  }
  // Chặn Ctrl + U (Xem mã nguồn View-Source) & Ctrl + S (Lưu trang)
  if (e.ctrlKey && ["U", "u", "S", "s"].includes(e.key)) {
    e.preventDefault();
    return false;
  }
});

let currentServerOffsetMs = 0;
let currentBranch = null;
let currentActiveFormUrl = "";
let currentUser = null;

// DOM Elements
const hoursEl = document.getElementById("hours");
const minutesEl = document.getElementById("minutes");
const secondsEl = document.getElementById("seconds");
const ampmEl = document.getElementById("ampm");
const dayOfWeekEl = document.getElementById("dayOfWeek");
const fullDateEl = document.getElementById("fullDate");
const currentShiftTextEl = document.getElementById("currentShiftText");

const loginAuthOverlay = document.getElementById("loginAuthOverlay");
const inputLoginEmail = document.getElementById("inputLoginEmail");
const inputLoginPassword = document.getElementById("inputLoginPassword");
const btnLoginSubmit = document.getElementById("btnLoginSubmit");
const btnLogoutUser = document.getElementById("btnLogoutUser");

const headerGreetingText = document.getElementById("headerGreetingText");
const dispUserName = document.getElementById("dispUserName");
const dispUserRole = document.getElementById("dispUserRole");

const cardWorkIn = document.getElementById("cardWorkIn");
const cardWorkOut = document.getElementById("cardWorkOut");

// Google Form Modal
const formModal = document.getElementById("formModal");
const modalTag = document.getElementById("modalTag");
const modalHeading = document.getElementById("modalHeading");
const googleFormIframe = document.getElementById("googleFormIframe");
const iframeLoader = document.getElementById("iframeLoader");
const btnOpenNewTab = document.getElementById("btnOpenNewTab");
const btnCloseModal = document.getElementById("btnCloseModal");

const btnFullscreen = document.getElementById("btnFullscreen");
const fullscreenIcon = document.getElementById("fullscreenIcon");
const toast = document.getElementById("toastNotification");

const DAYS_VI = [
  "CHỦ NHẬT", "THỨ HAI", "THỨ BA", "THỨ TƯ", "THỨ NĂM", "THỨ SÁU", "THỨ BẢY"
];

// =====================================================================
// 1. ĐỒNG BỘ THỜI GIAN NGUYÊN TỬ SERVER TIME
// =====================================================================
async function syncServerStatus() {
  try {
    const res = await fetch("/api/system/status");
    const data = await res.json();

    const localNow = Date.now();
    currentServerOffsetMs = data.server_epoch_ms - localNow;
    currentBranch = data.branch;

    if (data.branch && data.branch.name) {
      document.getElementById("displayStoreName").textContent = data.branch.name;
    }
  } catch (err) {
    console.warn("Lỗi đồng bộ máy chủ:", err);
  }
}

function updateAtomicClock() {
  const now = new Date(Date.now() + currentServerOffsetMs);

  const rawHours = now.getHours();
  const rawMinutes = now.getMinutes();
  const rawSeconds = now.getSeconds();

  if (hoursEl) hoursEl.textContent = String(rawHours).padStart(2, "0");
  if (minutesEl) minutesEl.textContent = String(rawMinutes).padStart(2, "0");
  if (secondsEl) secondsEl.textContent = String(rawSeconds).padStart(2, "0");
  if (ampmEl) ampmEl.textContent = rawHours >= 12 ? "PM" : "AM";

  const dayName = DAYS_VI[now.getDay()];
  const dateNum = String(now.getDate()).padStart(2, "0");
  const monthNum = String(now.getMonth() + 1).padStart(2, "0");
  const yearNum = now.getFullYear();

  if (dayOfWeekEl) dayOfWeekEl.textContent = dayName;
  if (fullDateEl) fullDateEl.textContent = `Ngày ${dateNum} Tháng ${monthNum}, Năm ${yearNum}`;

  if (currentShiftTextEl) {
    if (rawHours >= 6 && rawHours < 14) {
      currentShiftTextEl.textContent = "Ca Sáng (06:00 - 14:00)";
    } else if (rawHours >= 14 && rawHours < 22) {
      currentShiftTextEl.textContent = "Ca Chiều (14:00 - 22:00)";
    } else {
      currentShiftTextEl.textContent = "Ca Đêm (22:00 - 06:00)";
    }
  }
}

// =====================================================================
// 2. ĐĂNG NHẬP EMAIL & MẬT KHẨU (BẢO VỆ PHÍA MÁY CHỦ)
// =====================================================================
function checkUserSession() {
  const savedUserJson = localStorage.getItem("timeclock_user_session");
  if (savedUserJson) {
    try {
      currentUser = JSON.parse(savedUserJson);
      applyAuthenticatedUser(currentUser);
      return;
    } catch (e) {}
  }

  // Chưa đăng nhập -> Hiện màn hình đăng nhập
  loginAuthOverlay.style.display = "flex";
  headerGreetingText.textContent = "Chưa Đăng Nhập";
}

function applyAuthenticatedUser(user) {
  loginAuthOverlay.style.display = "none";
  // CHỈ HIỂN THỊ "XIN CHÀO + TÊN" (GIẤU HOÀN TOÀN EMAIL)
  headerGreetingText.textContent = `Xin chào ${user.employee_name}`;
  dispUserName.textContent = user.employee_name;
  dispUserRole.textContent = user.role;
}

btnLoginSubmit.addEventListener("click", async () => {
  const email = inputLoginEmail.value.trim().toLowerCase();
  const password = inputLoginPassword.value.trim();

  if (!email || !email.includes("@")) {
    showToast("Vui lòng nhập Email nhân viên hợp lệ!");
    return;
  }
  if (!password) {
    showToast("Vui lòng nhập Mật khẩu tài khoản!");
    return;
  }

  try {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: email, password: password })
    });

    const data = await res.json();
    if (res.ok && data.success) {
      currentUser = {
        employee_name: data.employee_name,
        role: data.role,
        session_token: data.session_token
      };
      // Lưu phiên làm việc (Chỉ lưu Tên, không lưu Mật khẩu hay Email)
      localStorage.setItem("timeclock_user_session", JSON.stringify(currentUser));
      applyAuthenticatedUser(currentUser);

      inputLoginEmail.value = "";
      inputLoginPassword.value = "";
      showToast(`🎉 Xin chào ${data.employee_name}! Đã mở khóa vào ca.`);
    } else {
      showToast(`❌ ${data.detail || "Đăng nhập thất bại!"}`);
    }
  } catch (err) {
    showToast("Lỗi kết nối máy chủ: " + err.message);
  }
});

inputLoginPassword.addEventListener("keydown", (e) => {
  if (e.key === "Enter") btnLoginSubmit.click();
});

btnLogoutUser.addEventListener("click", () => {
  localStorage.removeItem("timeclock_user_session");
  currentUser = null;
  loginAuthOverlay.style.display = "flex";
  dispUserName.textContent = "Đang tải...";
  dispUserRole.textContent = "---";
  headerGreetingText.textContent = "Chưa Đăng Nhập";
  showToast("Đã đăng xuất đổi ca thành công!");
});

// =====================================================================
// 3. MỞ GOOGLE FORM ĐIỂM DANH (WORK IN & WORK OUT)
// =====================================================================
window.handleOpenGoogleForm = function(type) {
  if (!currentUser) {
    showToast("Vui lòng đăng nhập tài khoản trước khi điểm danh!");
    loginAuthOverlay.style.display = "flex";
    return;
  }

  let formUrl = "";
  if (type === "WORK_IN") {
    formUrl = currentBranch?.google_form_work_in || "https://docs.google.com/forms/d/e/1FAIpQLScJ_v5aA0mD6q8_demo_work_in/viewform?embedded=true";
    modalTag.textContent = "WORK IN";
    modalTag.style.background = "var(--primary-red)";
    modalHeading.textContent = `[VÀO CA] Điểm Danh - ${currentUser.employee_name}`;
  } else {
    formUrl = currentBranch?.google_form_work_out || "https://docs.google.com/forms/d/e/1FAIpQLSdX_w7bB1nE7r9_demo_work_out/viewform?embedded=true";
    modalTag.textContent = "WORK OUT";
    modalTag.style.background = "#ff3344";
    modalHeading.textContent = `[TAN CA] Báo Cáo - ${currentUser.employee_name}`;
  }

  currentActiveFormUrl = formUrl;

  iframeLoader.style.display = "flex";
  iframeLoader.style.opacity = "1";
  googleFormIframe.src = formUrl;

  googleFormIframe.onload = () => {
    iframeLoader.style.opacity = "0";
    setTimeout(() => { iframeLoader.style.display = "none"; }, 300);
  };

  formModal.classList.add("active");
  document.body.style.overflow = "hidden";
};

function closeFormModal() {
  formModal.classList.remove("active");
  document.body.style.overflow = "";
  setTimeout(() => { googleFormIframe.src = "about:blank"; }, 200);
}

btnCloseModal.addEventListener("click", closeFormModal);
formModal.addEventListener("click", (e) => {
  if (e.target === formModal) closeFormModal();
});

btnOpenNewTab.addEventListener("click", () => {
  if (currentActiveFormUrl && currentActiveFormUrl !== "about:blank") {
    window.open(currentActiveFormUrl, "_blank", "noopener,noreferrer");
  }
});

btnFullscreen.addEventListener("click", () => {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen().catch(() => {});
  } else {
    if (document.exitFullscreen) document.exitFullscreen();
  }
});

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("show");
  setTimeout(() => { toast.classList.remove("show"); }, 3500);
}

window.addEventListener("DOMContentLoaded", () => {
  if (window.lucide) lucide.createIcons();
  updateAtomicClock();
  setInterval(updateAtomicClock, 1000);

  syncServerStatus();
  setInterval(syncServerStatus, 30000);

  checkUserSession();
});
