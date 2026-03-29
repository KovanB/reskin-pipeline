import { useState } from "react";

const STATUS_BADGES = {
  pending: "badge-pending",
  extracting: "badge-running",
  generating: "badge-running",
  baking: "badge-running",
  packaging: "badge-running",
  completed: "badge-completed",
  failed: "badge-failed",
};

const STATUS_LABELS = {
  pending: "Pending",
  extracting: "Extracting",
  generating: "Generating",
  baking: "Baking",
  packaging: "Packaging",
  completed: "Completed",
  failed: "Failed",
};

function timeAgo(dateStr) {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export default function JobCard({ job: initialJob, onClick }) {
  const [job] = useState(initialJob);
  const progress = job.progress || {};
  const isRunning = !["completed", "failed", "pending"].includes(progress.status);

  return (
    <div className="card" style={{ cursor: "pointer" }} onClick={() => onClick(job)}>
      <div className="job-card">
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontWeight: 600 }}>{job.name}</span>
            <span className={`badge ${STATUS_BADGES[progress.status] || "badge-pending"}`}>
              {STATUS_LABELS[progress.status] || progress.status}
            </span>
          </div>
          <div className="job-meta">
            <span>{job.backend}</span>
            <span>{job.asset_count || 0} assets</span>
            <span>{timeAgo(job.created_at)}</span>
          </div>
          {progress.message && (
            <div style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 4 }}>
              {progress.message}
            </div>
          )}
          {isRunning && (
            <div className="progress-bar">
              <div className="progress-fill" style={{ width: `${progress.percent || 0}%` }} />
            </div>
          )}
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          {job.download_url && (
            <a
              href={job.download_url}
              className="btn btn-primary"
              style={{ fontSize: 13, padding: "6px 14px" }}
              onClick={(e) => e.stopPropagation()}
            >
              Download
            </a>
          )}
        </div>
      </div>
    </div>
  );
}
