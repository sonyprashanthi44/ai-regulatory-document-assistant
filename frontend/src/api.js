const API_BASE = (import.meta.env.VITE_API_BASE || "").replace(/\/$/, "");

function authHeaders() {
  const token = localStorage.getItem("token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function handle(res) {
  let data = {};
  const text = await res.text();
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { detail: text || "Request failed" };
  }
  if (!res.ok) {
    const d = data.detail;
    const msg = Array.isArray(d)
      ? d.map((x) => x.msg || JSON.stringify(x)).join("; ")
      : typeof d === "string"
        ? d
        : d
          ? JSON.stringify(d)
          : data.message || `Request failed (${res.status})`;
    throw new Error(msg);
  }
  return data;
}

export async function register(email, password, full_name) {
  return handle(
    await fetch(`${API_BASE}/api/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, full_name }),
    })
  );
}

export async function login(email, password) {
  const body = new URLSearchParams();
  body.set("username", email);
  body.set("password", password);
  return handle(
    await fetch(`${API_BASE}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    })
  );
}

export async function logout() {
  try {
    await fetch(`${API_BASE}/api/auth/logout`, {
      method: "POST",
      headers: { ...authHeaders() },
    });
  } finally {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
  }
}

export async function listDocuments() {
  return handle(
    await fetch(`${API_BASE}/api/documents`, { headers: { ...authHeaders() } })
  );
}

export async function uploadDocument(file) {
  const fd = new FormData();
  fd.append("file", file);
  return handle(
    await fetch(`${API_BASE}/api/documents/upload`, {
      method: "POST",
      headers: { ...authHeaders() },
      body: fd,
    })
  );
}

export async function clearDocuments() {
  return handle(
    await fetch(`${API_BASE}/api/documents`, {
      method: "DELETE",
      headers: { ...authHeaders() },
    })
  );
}

export async function askQuestion(question) {
  return handle(
    await fetch(`${API_BASE}/api/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ question }),
    })
  );
}

export function apiBase() {
  return API_BASE || "(same origin / Vite proxy)";
}
