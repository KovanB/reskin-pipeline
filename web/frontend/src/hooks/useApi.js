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

export function connectJobSSE(jobId, onMessage) {
  /**
   * Connect to the SSE /run endpoint which actually executes the pipeline
   * and streams progress events back. The connection stays alive until done.
   */
  let active = true;

  const run = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/jobs/${jobId}/run`);
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (active) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop(); // keep incomplete chunk

        for (const line of lines) {
          const match = line.match(/^data:\s*(.+)$/m);
          if (match) {
            try {
              onMessage(JSON.parse(match[1]));
            } catch (e) {
              console.error("SSE parse error:", e);
            }
          }
        }
      }
    } catch (e) {
      console.error("SSE error:", e);
      onMessage({ status: "failed", message: `Connection error: ${e.message}` });
    }
  };

  run();
  return () => { active = false; };
}

// Keep the old polling as a fallback for viewing completed jobs
export function connectJobWS(jobId, onMessage) {
  let active = true;
  const poll = async () => {
    while (active) {
      try {
        const job = await apiFetch(`/api/jobs/${jobId}`);
        if (job.progress) onMessage(job.progress);
        if (job.progress?.status === "completed" || job.progress?.status === "failed") break;
      } catch (e) {
        console.error("Poll error:", e);
      }
      await new Promise((r) => setTimeout(r, 2000));
    }
  };
  poll();
  return () => { active = false; };
}
