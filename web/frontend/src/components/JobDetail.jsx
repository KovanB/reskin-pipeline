import { useEffect, useState, useRef } from "react";
import { getJob, getJobAssets, connectJobSSE } from "../hooks/useApi";

const API_BASE = import.meta.env.VITE_API_URL || "";

export default function JobDetail({ jobId, onBack }) {
  const [job, setJob] = useState(null);
  const [assets, setAssets] = useState([]);
  const [selectedAsset, setSelectedAsset] = useState(null);
  const [tab, setTab] = useState("preview");
  const sseStarted = useRef(false);

  useEffect(() => {
    getJob(jobId).then((j) => {
      setJob(j);
      // Auto-start pipeline via SSE if job is pending
      if (j.progress?.status === "pending" && !sseStarted.current) {
        sseStarted.current = true;
        connectJobSSE(jobId, (update) => {
          setJob((prev) => ({ ...prev, progress: update, status: update.status }));
          if (update.status === "completed" || update.status === "baking") {
            getJobAssets(jobId).then((r) => setAssets(r.assets || [])).catch(() => {});
          }
        });
      }
    });
    getJobAssets(jobId).then((r) => setAssets(r.assets || [])).catch(() => {});
  }, [jobId]);

  if (!job) return <div style={{ padding: 40, textAlign: "center", color: "var(--text-muted)" }}>Loading...</div>;

  const progress = job.progress || {};

  return (
    <div>
      <button className="btn btn-secondary" onClick={onBack} style={{ marginBottom: 16 }}>
        Back to jobs
      </button>

      <div className="card">
        <div className="card-header">
          <div>
            <h2 className="card-title">{job.name}</h2>
            <div style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 4 }}>
              {job.style_prompt}
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            {job.download_url && (
              <a href={`${API_BASE}${job.download_url}`} className="btn btn-primary">
                Download Skin
              </a>
            )}
          </div>
        </div>

        {/* Progress */}
        {progress.status && !["completed", "failed"].includes(progress.status) && (
          <div style={{ marginBottom: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, color: "var(--text-muted)" }}>
              <span>{progress.message}</span>
              <span>{Math.round(progress.percent || 0)}%</span>
            </div>
            <div className="progress-bar">
              <div className="progress-fill" style={{ width: `${progress.percent || 0}%` }} />
            </div>
          </div>
        )}

        {progress.status === "failed" && (
          <div style={{ padding: 12, background: "rgba(248,113,113,0.1)", borderRadius: 8, color: "var(--error)", fontSize: 13 }}>
            {job.error || progress.message}
          </div>
        )}

        {progress.status === "completed" && (
          <div style={{ padding: 12, background: "rgba(52,211,153,0.1)", borderRadius: 8, color: "var(--success)", fontSize: 13 }}>
            Skin ready! {job.asset_count} assets reskinned.
          </div>
        )}

        {/* Stats */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginTop: 16 }}>
          {[
            { label: "Backend", value: job.backend },
            { label: "Assets", value: job.asset_count || assets.length },
            { label: "Status", value: progress.status },
            { label: "Stage", value: progress.stage || "-" },
          ].map((s) => (
            <div key={s.label} style={{ background: "var(--bg-input)", borderRadius: 8, padding: 12 }}>
              <div style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase" }}>{s.label}</div>
              <div style={{ fontSize: 16, fontWeight: 600, marginTop: 2 }}>{s.value}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Tabs */}
      {assets.length > 0 && (
        <>
          <div className="tabs">
            <button className={`tab ${tab === "preview" ? "active" : ""}`} onClick={() => setTab("preview")}>
              Preview Grid
            </button>
            <button className={`tab ${tab === "compare" ? "active" : ""}`} onClick={() => setTab("compare")}>
              Before / After
            </button>
          </div>

          {tab === "preview" && (
            <div className="preview-grid">
              {assets.filter((a) => a.preview_url).map((asset) => (
                <div key={asset.relative_path} className="preview-item" onClick={() => { setSelectedAsset(asset); setTab("compare"); }}>
                  <img src={`${API_BASE}${asset.preview_url}`} alt={asset.relative_path} loading="lazy" />
                  <div className="preview-overlay">
                    <span>{asset.relative_path.split("/").pop()}</span>
                  </div>
                </div>
              ))}
            </div>
          )}

          {tab === "compare" && (
            <div>
              {!selectedAsset && assets.filter((a) => a.preview_url).length > 0 && (
                <div className="empty-state">
                  <h3>Click an asset to compare</h3>
                  <p>Select from the grid above, or:</p>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "center", marginTop: 12 }}>
                    {assets.filter((a) => a.preview_url).slice(0, 8).map((a) => (
                      <button key={a.relative_path} className="btn btn-secondary" style={{ fontSize: 12, padding: "4px 10px" }} onClick={() => setSelectedAsset(a)}>
                        {a.relative_path.split("/").pop()}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {selectedAsset && (
                <div className="card">
                  <div className="card-header">
                    <span className="card-title">{selectedAsset.relative_path}</span>
                    <span style={{ fontSize: 12, color: "var(--text-muted)" }}>{selectedAsset.width}x{selectedAsset.height} | {selectedAsset.category}</span>
                  </div>
                  <div className="compare-container">
                    <div className="compare-side">
                      <div className="compare-label">Before</div>
                      <img src={`${API_BASE}${selectedAsset.original_url}`} alt="Original" />
                    </div>
                    <div className="compare-side">
                      <div className="compare-label" style={{ color: "var(--accent)" }}>After</div>
                      <img src={`${API_BASE}${selectedAsset.preview_url}`} alt="Reskinned" />
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                    {assets.filter((a) => a.preview_url).map((a) => (
                      <button
                        key={a.relative_path}
                        className={`btn ${a.relative_path === selectedAsset.relative_path ? "btn-primary" : "btn-secondary"}`}
                        style={{ fontSize: 11, padding: "4px 8px" }}
                        onClick={() => setSelectedAsset(a)}
                      >
                        {a.relative_path.split("/").pop()}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
