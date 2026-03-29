const API_BASE = import.meta.env.VITE_API_URL || "";

export async function apiFetch(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

export function createJob(data, ueProjectPath) {
  return apiFetch(`/api/jobs?ue_project_path=${encodeURIComponent(ueProjectPath)}`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function listJobs() {
  return apiFetch("/api/jobs");
}

export function getJob(id) {
  return apiFetch(`/api/jobs/${id}`);
}

export function getJobAssets(id) {
  return apiFetch(`/api/jobs/${id}/assets`);
}

export function uploadProject(file) {
  const form = new FormData();
  form.append("file", file);
  return fetch(`${API_BASE}/api/upload/project`, { method: "POST", body: form }).then(
    (r) => {
      if (!r.ok) throw new Error("Upload failed");
      return r.json();
    }
  );
}

export function connectJobWS(jobId, onMessage) {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsBase = import.meta.env.VITE_WS_URL || `${protocol}//${window.location.host}`;
  const ws = new WebSocket(`${wsBase}/ws/jobs/${jobId}`);

  ws.onmessage = (event) => {
    onMessage(JSON.parse(event.data));
  };

  ws.onerror = (err) => console.error("WS error:", err);

  return () => ws.close();
}
