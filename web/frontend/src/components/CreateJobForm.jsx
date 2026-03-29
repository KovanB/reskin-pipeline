import { useState } from "react";
import { createJob, uploadProject } from "../hooks/useApi";

const BACKENDS = [
  { value: "local", label: "Local Diffusion (SDXL-Turbo)" },
  { value: "lucy", label: "Decart Lucy" },
  { value: "stability", label: "Stability AI" },
  { value: "comfyui", label: "ComfyUI (Local Server)" },
];

const CATEGORIES = ["textures", "ui", "skyboxes", "particles", "materials"];

export default function CreateJobForm({ onCreated }) {
  const [form, setForm] = useState({
    name: "",
    style_prompt: "",
    backend: "local",
    categories: [...CATEGORIES],
    author: "",
    description: "",
    api_key: "",
    quality: { strength: 0.75, guidance_scale: 7.5, steps: 30, preserve_pbr: true, tile_seam_fix: true, consistency_pass: true },
  });
  const [projectPath, setProjectPath] = useState("");
  const [projectFile, setProjectFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const update = (key, val) => setForm((f) => ({ ...f, [key]: val }));
  const updateQuality = (key, val) => setForm((f) => ({ ...f, quality: { ...f.quality, [key]: val } }));

  const toggleCategory = (cat) => {
    setForm((f) => {
      const cats = f.categories.includes(cat) ? f.categories.filter((c) => c !== cat) : [...f.categories, cat];
      return { ...f, categories: cats };
    });
  };

  const handleUpload = async (file) => {
    setProjectFile(file);
    setUploading(true);
    try {
      const result = await uploadProject(file);
      setProjectPath(result.project_path);
    } catch (e) {
      setError(e.message);
    } finally {
      setUploading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const job = await createJob(form, projectPath);
      onCreated(job);
    } catch (e) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  const needsApiKey = form.backend === "lucy" || form.backend === "stability";

  return (
    <form onSubmit={handleSubmit} className="card">
      <div className="card-header">
        <h2 className="card-title">New Reskin Job</h2>
      </div>

      {error && <div style={{ color: "var(--error)", marginBottom: 16, fontSize: 13 }}>{error}</div>}

      <div className="form-row">
        <div className="form-group">
          <label>Skin Name</label>
          <input className="form-input" value={form.name} onChange={(e) => update("name", e.target.value)} placeholder="CyberpunkNeon" required />
        </div>
        <div className="form-group">
          <label>Backend</label>
          <select className="form-select" value={form.backend} onChange={(e) => update("backend", e.target.value)}>
            {BACKENDS.map((b) => (
              <option key={b.value} value={b.value}>{b.label}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="form-group">
        <label>Style Prompt</label>
        <textarea
          className="form-textarea"
          value={form.style_prompt}
          onChange={(e) => update("style_prompt", e.target.value)}
          placeholder="cyberpunk neon aesthetic, glowing edges, dark background with vibrant pink and cyan accents..."
          required
        />
      </div>

      {needsApiKey && (
        <div className="form-group">
          <label>API Key</label>
          <input className="form-input" type="password" value={form.api_key} onChange={(e) => update("api_key", e.target.value)} placeholder="sk-..." />
        </div>
      )}

      <div className="form-group">
        <label>UE Project</label>
        <div className="form-row">
          <input
            className="form-input"
            value={projectPath}
            onChange={(e) => setProjectPath(e.target.value)}
            placeholder="C:/Users/.../MyProject or upload zip"
          />
          <label className="btn btn-secondary" style={{ justifyContent: "center" }}>
            {uploading ? "Uploading..." : "Upload .zip"}
            <input
              type="file"
              accept=".zip"
              style={{ display: "none" }}
              onChange={(e) => e.target.files[0] && handleUpload(e.target.files[0])}
            />
          </label>
        </div>
      </div>

      <div className="form-group">
        <label>Categories</label>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {CATEGORIES.map((cat) => (
            <button
              key={cat}
              type="button"
              className={`btn ${form.categories.includes(cat) ? "btn-primary" : "btn-secondary"}`}
              style={{ padding: "6px 14px", fontSize: 13 }}
              onClick={() => toggleCategory(cat)}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      <div className="form-group">
        <label>Strength: {form.quality.strength}</label>
        <div className="slider-group">
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Keep original</span>
          <input type="range" min="0" max="1" step="0.05" value={form.quality.strength} onChange={(e) => updateQuality("strength", parseFloat(e.target.value))} />
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Full restyle</span>
        </div>
      </div>

      <div className="form-row">
        <div className="form-group">
          <label>Guidance Scale</label>
          <input className="form-input" type="number" min="1" max="30" step="0.5" value={form.quality.guidance_scale} onChange={(e) => updateQuality("guidance_scale", parseFloat(e.target.value))} />
        </div>
        <div className="form-group">
          <label>Steps</label>
          <input className="form-input" type="number" min="1" max="100" value={form.quality.steps} onChange={(e) => updateQuality("steps", parseInt(e.target.value))} />
        </div>
      </div>

      <div className="form-row">
        <div className="form-group">
          <label>Author</label>
          <input className="form-input" value={form.author} onChange={(e) => update("author", e.target.value)} placeholder="Your name" />
        </div>
        <div className="form-group">
          <label>Description</label>
          <input className="form-input" value={form.description} onChange={(e) => update("description", e.target.value)} placeholder="What this skin does" />
        </div>
      </div>

      <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
        <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, color: "var(--text-muted)" }}>
          <input type="checkbox" checked={form.quality.preserve_pbr} onChange={(e) => updateQuality("preserve_pbr", e.target.checked)} />
          Preserve PBR maps
        </label>
        <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, color: "var(--text-muted)" }}>
          <input type="checkbox" checked={form.quality.tile_seam_fix} onChange={(e) => updateQuality("tile_seam_fix", e.target.checked)} />
          Fix tile seams
        </label>
        <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, color: "var(--text-muted)" }}>
          <input type="checkbox" checked={form.quality.consistency_pass} onChange={(e) => updateQuality("consistency_pass", e.target.checked)} />
          Consistency pass
        </label>
      </div>

      <div style={{ marginTop: 20 }}>
        <button type="submit" className="btn btn-primary" disabled={submitting || !form.name || !form.style_prompt || !projectPath}>
          {submitting ? "Creating..." : "Start Reskin Job"}
        </button>
      </div>
    </form>
  );
}
