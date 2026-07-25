// SigmX desktop setup wizard — runs in the Electron shell before the main app.
// Works with the Python backend's /onboarding/* endpoints.

const PORT = 8899;
const BASE = `http://127.0.0.1:${PORT}`;

let currentStep = 1;
const totalSteps = 4;

// ---- Navigation ----

function showStep(n) {
  document.querySelectorAll(".step").forEach((s) => s.classList.remove("active"));
  const el = document.getElementById(`step${n}`);
  if (el) el.classList.add("active");
  // Update dots
  for (let i = 1; i <= totalSteps; i++) {
    const dot = document.getElementById(`dot${i}`);
    if (!dot) continue;
    dot.classList.remove("done", "current");
    if (i < n) dot.classList.add("done");
    else if (i === n) dot.classList.add("current");
  }
  currentStep = n;

  // Pre-fill confirmation on step 4.
  if (n === 4) {
    document.getElementById("confirmEmail").textContent =
      document.getElementById("email").value || "admin@local";
    const ts = document.getElementById("tushareToken").value.trim();
    const tp = document.getElementById("tpdogToken").value.trim();
    document.getElementById("confirmTushare").textContent = ts || "未配置";
    document.getElementById("confirmTpdog").textContent = tp || "未配置";
    document.getElementById("step4Error").style.display = "none";
    document.getElementById("step4Success").style.display = "none";
    document.getElementById("initBtn").style.display = "block";
    document.getElementById("retryBtn").style.display = "none";
  }
}

function nextStep(n) {
  showStep(n);
}

function prevStep(n) {
  showStep(Math.max(1, n));
}

// ---- Validation (step 2) ----

function validateAndNext() {
  const email = document.getElementById("email").value.trim();
  const pw = document.getElementById("password").value;
  const pw2 = document.getElementById("password2").value;
  const err = document.getElementById("step2Error");

  err.style.display = "none";

  if (!email || !email.includes("@")) {
    err.textContent = "请输入有效的邮箱地址";
    err.style.display = "block";
    return;
  }
  if (pw.length < 4) {
    err.textContent = "密码至少4位";
    err.style.display = "block";
    return;
  }
  if (pw !== pw2) {
    err.textContent = "两次密码不一致";
    err.style.display = "block";
    return;
  }
  nextStep(3);
}

// ---- Initialize ----

async function doInitialize() {
  const initBtn = document.getElementById("initBtn");
  const retryBtn = document.getElementById("retryBtn");
  const err = document.getElementById("step4Error");
  const ok = document.getElementById("step4Success");

  initBtn.disabled = true;
  initBtn.textContent = "正在初始化…";
  err.style.display = "none";
  ok.style.display = "none";

  try {
    const body = {
      email: document.getElementById("email").value.trim() || "admin@local",
      password: document.getElementById("password").value || "admin123",
      tushare_token: document.getElementById("tushareToken").value.trim(),
      tpdog_token: document.getElementById("tpdogToken").value.trim(),
    };

    const res = await fetch(`${BASE}/onboarding/initialize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || `HTTP ${res.status}`);
    }

    ok.textContent = "✓ 设置完成！正在进入 SigmX…";
    ok.style.display = "block";
    initBtn.style.display = "none";

    // Notify Electron that setup is done, then redirect.
    setTimeout(() => {
      window.location.href = `${BASE}/`;
    }, 1200);
  } catch (e) {
    err.textContent = `初始化失败：${e.message}`;
    err.style.display = "block";
    initBtn.style.display = "none";
    retryBtn.style.display = "block";
  }
}

function retryInit() {
  const initBtn = document.getElementById("initBtn");
  const retryBtn = document.getElementById("retryBtn");
  initBtn.style.display = "block";
  initBtn.textContent = "完成设置";
  initBtn.disabled = false;
  retryBtn.style.display = "none";
  document.getElementById("step4Error").style.display = "none";
}

// ---- Init ----

document.addEventListener("DOMContentLoaded", () => {
  // Show the data directory in step 1.
  // The backend returns it in /onboarding/status, but for simplicity we hardcode.
  // On Windows this resolves under the user's home dir.
  showStep(1);
});
