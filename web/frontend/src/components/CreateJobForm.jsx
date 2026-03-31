import { useState } from "react";
import { createJob, uploadProject } from "../hooks/useApi";

const BACKENDS = [
  { value: "lucy", label: "Decart Lucy (Recommended)" },
  { value: "local", label: "Local Diffusion (SDXL-Turbo)" },
  { value: "stability", label: "Stability AI" },
  { value: "comfyui", label: "ComfyUI (Local Server)" },
];

const CATEGORIES = ["textures", "ui", "skyboxes", "particles", "materials"];

const DEMO_CHARACTERS = ["Knight", "Mage", "Rogue", "Ranger", "Cleric"];

const PUBLIC_DOMAIN_PRESETS = [
  {
    name: "AliceWonderland",
    label: "Alice in Wonderland",
    style_prompt: "Alice in Wonderland aesthetic, whimsical Victorian fantasy, playing card motifs, checkerboard patterns, oversized mushrooms, teacup and pocket watch details, pastel purple and teal color palette, storybook illustration style, Cheshire cat grins, Queen of Hearts red and gold accents",
    description: "Wonderland-themed runner with playing card guards, mushroom obstacles, and rabbit-hole tunnels",
  },
  {
    name: "RobinHood",
    label: "Robin Hood",
    style_prompt: "Robin Hood medieval forest aesthetic, Sherwood Forest deep greens and earthy browns, medieval English village, wooden architecture, archery targets, wanted posters, leaf and vine motifs, golden treasure coins, rustic hand-painted texture style, Lincoln green and brown leather palette",
    description: "Sherwood Forest runner dodging the Sheriff's guards, leaping over market carts, and collecting gold coins",
  },
  {
    name: "DraculaGothic",
    label: "Dracula",
    style_prompt: "Dracula gothic horror aesthetic, Transylvanian castle architecture, dark crimson and midnight purple palette, bat silhouettes, full moon skybox, cobblestone streets, iron gates, candelabras, fog and mist particles, gothic stained glass, Victorian horror style, blood red accents on black",
    description: "Gothic Transylvania runner fleeing through moonlit castle corridors and misty graveyards",
  },
  {
    name: "WizardOfOz",
    label: "Wizard of Oz",
    style_prompt: "Wizard of Oz aesthetic, yellow brick road ground textures, emerald green Emerald City architecture, poppy field environments, tornado swirl particles, ruby red and emerald green color palette, whimsical painted storybook style, hot air balloon motifs, tin and straw material textures, rainbow skybox",
    description: "Oz-themed runner dashing down the Yellow Brick Road toward the Emerald City",
  },
  {
    name: "LittleMermaid",
    label: "The Little Mermaid",
    style_prompt: "Little Mermaid underwater kingdom aesthetic, deep ocean blues and seafoam greens, coral reef architecture, seashell and pearl UI elements, bioluminescent jellyfish particles, sunlight rays filtering through water, treasure chest and shipwreck obstacles, iridescent fish scale textures, oceanic watercolor painting style, aquamarine and coral pink palette",
    description: "Undersea runner swimming through coral kingdoms and sunken ships",
  },
];

export default function CreateJobForm({ onCreated }) {
  const [form, setForm] = useState({
    name: "",
    style_prompt: "",
    backend: "lucy",
    categories: [...CATEGORIES],
    author: "",
    description: "",
    api_key: "",
    quality: { strength: 0.75, guidance_scale: 7.5, steps: 30, preserve_pbr: true, tile_seam_fix: true, consistency_pass: true },
  });
  const [projectPath, setProjectPath] = useState("demo");
  const [useDemo, setUseDemo] = useState(true);
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
    setUploading(true);
    try {
      const result = await uploadProject(file);
      setProjectPath(result.project_path);
      setUseDemo(false);
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
      const job = await createJob(form, useDemo ? "demo" : projectPath);
      onCreated(job);
    } catch (e) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  const needsApiKey = form.backend === "stability";

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
        <label>Quick Start — Public Domain Skins</label>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {PUBLIC_DOMAIN_PRESETS.map((preset) => (
            <button
              key={preset.name}
              type="button"
              className={`btn ${form.name === preset.name ? "btn-primary" : "btn-secondary"}`}
              style={{ padding: "6px 14px", fontSize: 13 }}
              onClick={() => setForm((f) => ({
                ...f,
                name: preset.name,
                style_prompt: preset.style_prompt,
                description: preset.description,
              }))}
            >
              {preset.label}
            </button>
          ))}
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

      {/* Source project */}
      <div className="form-group">
        <label>Source Characters</label>
        <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
          <button
            type="button"
            className={`btn ${useDemo ? "btn-primary" : "btn-secondary"}`}
            onClick={() => { setUseDemo(true); setProjectPath("demo"); }}
          >
            Demo Characters (5 built-in)
          </button>
          <button
            type="button"
            className={`btn ${!useDemo ? "btn-primary" : "btn-secondary"}`}
            onClick={() => setUseDemo(false)}
          >
            Upload Custom
          </button>
        </div>

        {useDemo ? (
          <div style={{ background: "var(--bg-input)", borderRadius: 8, padding: 16 }}>
            <div style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 10 }}>
              5 characters with Body, Face, Arms, Legs, and Weapon textures each (25 total assets):
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {DEMO_CHARACTERS.map((c) => (
                <span key={c} style={{
                  padding: "4px 12px",
                  borderRadius: 6,
                  fontSize: 13,
                  fontWeight: 500,
                  background: "var(--bg-card)",
                  border: "1px solid var(--border)",
                }}>
                  {c}
                </span>
              ))}
            </div>
          </div>
        ) : (
          <div className="form-row">
            <input
              className="form-input"
              value={projectPath === "demo" ? "" : projectPath}
              onChange={(e) => setProjectPath(e.target.value)}
              placeholder="Path to UE project or upload zip"
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
        )}
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
        <button type="submit" className="btn btn-primary" disabled={submitting || !form.name || !form.style_prompt}>
          {submitting ? "Creating..." : "Start Reskin Job"}
        </button>
      </div>
    </form>
  );
}
