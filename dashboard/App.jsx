import { useState, useEffect, useRef, useCallback } from "react";

const API_URL = import.meta.env.VITE_API_URL || "";

// ──────────────────────────────────────────────
// Theme & Design Tokens
// ──────────────────────────────────────────────
const theme = {
  bg: "#0a0a0f",
  bgCard: "#12121a",
  bgHover: "#1a1a2e",
  bgInput: "#0d0d14",
  border: "#1e1e30",
  borderActive: "#4f46e5",
  text: "#e2e2e8",
  textMuted: "#6b6b80",
  textDim: "#44445a",
  accent: "#6366f1",
  accentGlow: "rgba(99,102,241,0.15)",
  success: "#22c55e",
  successBg: "rgba(34,197,94,0.1)",
  warning: "#f59e0b",
  warningBg: "rgba(245,158,11,0.1)",
  error: "#ef4444",
  errorBg: "rgba(239,68,68,0.1)",
  info: "#3b82f6",
  infoBg: "rgba(59,130,246,0.1)",
};

const agentColors = {
  architect: "#a78bfa",
  intake: "#60a5fa",
  modeler: "#34d399",
  backend_builder: "#f472b6",
  frontend_builder: "#fb923c",
  reviewer: "#facc15",
  tester: "#2dd4bf",
  fixer: "#f87171",
  doc_writer: "#94a3b8",
};

const TIER_LABELS = { low: "Low", medium: "Medium", high: "High", critical: "Critical" };
const TIER_COLORS = { low: "#22c55e", medium: "#3b82f6", high: "#f59e0b", critical: "#ef4444" };
const PROVIDER_ICONS = { openrouter: "🔀", anthropic: "🧠", openai: "⚡", google: "🔮" };
const PROVIDER_COLORS = { openrouter: "#7c3aed", anthropic: "#d97706", openai: "#059669", google: "#2563eb" };

// ──────────────────────────────────────────────
// API Client
// ──────────────────────────────────────────────
const api = {
  async createProject(data) {
    const r = await fetch(`${API_URL}/api/projects`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    return r.json();
  },
  async listProjects() {
    const r = await fetch(`${API_URL}/api/projects`);
    return r.json();
  },
  async getProject(id) {
    const r = await fetch(`${API_URL}/api/projects/${id}`);
    return r.json();
  },
  async getFiles(id) {
    const r = await fetch(`${API_URL}/api/projects/${id}/files`);
    return r.json();
  },
  async getTree(id) {
    const r = await fetch(`${API_URL}/api/projects/${id}/tree`);
    return r.json();
  },
  async getEvents(id) {
    const r = await fetch(`${API_URL}/api/projects/${id}/events`);
    return r.json();
  },
  async getWorkUnits(id) {
    const r = await fetch(`${API_URL}/api/projects/${id}/work-units`);
    return r.json();
  },
  async buildFromRequirements(id, requirements) {
    const r = await fetch(`${API_URL}/api/projects/${id}/build/requirements`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ requirements }),
    });
    return r.json();
  },
  async buildFromHtml(id, htmlFiles) {
    const r = await fetch(`${API_URL}/api/projects/${id}/build/html`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ html_files: htmlFiles }),
    });
    return r.json();
  },
  async submitFeedback(id, description, type = "general", screenId = null) {
    const r = await fetch(`${API_URL}/api/projects/${id}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description, feedback_type: type, screen_id: screenId }),
    });
    return r.json();
  },
  async getMetrics() {
    const r = await fetch(`${API_URL}/api/metrics`);
    return r.json();
  },
  async rebuildProject(id) {
    const r = await fetch(`${API_URL}/api/projects/${id}/rebuild`, { method: "POST" });
    return r.json();
  },
  // LLM Config
  async getLLMProviders() {
    const r = await fetch(`${API_URL}/api/llm/providers`);
    return r.json();
  },
  async updateLLMProvider(providerId, data) {
    const r = await fetch(`${API_URL}/api/llm/providers/${providerId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    return r.json();
  },
  async getLLMModels() {
    const r = await fetch(`${API_URL}/api/llm/models`);
    return r.json();
  },
  async addLLMModel(data) {
    const r = await fetch(`${API_URL}/api/llm/models`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    return r.json();
  },
  async updateLLMModel(modelId, data) {
    const r = await fetch(`${API_URL}/api/llm/models/${encodeURIComponent(modelId)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    return r.json();
  },
  async deleteLLMModel(modelId) {
    const r = await fetch(`${API_URL}/api/llm/models/${encodeURIComponent(modelId)}`, { method: "DELETE" });
    return r.json();
  },
  async getLLMRouting() {
    const r = await fetch(`${API_URL}/api/llm/routing`);
    return r.json();
  },
  async updateLLMRouting(routing) {
    const r = await fetch(`${API_URL}/api/llm/routing`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ routing }),
    });
    return r.json();
  },
  async testLLMModel(modelId) {
    const r = await fetch(`${API_URL}/api/llm/test`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_id: modelId }),
    });
    return r.json();
  },
};

// ──────────────────────────────────────────────
// Utility Components
// ──────────────────────────────────────────────
const StatusBadge = ({ status }) => {
  const colors = {
    created: { bg: theme.infoBg, text: theme.info },
    analyzing: { bg: theme.warningBg, text: theme.warning },
    planning: { bg: theme.warningBg, text: theme.warning },
    building: { bg: theme.accentGlow, text: theme.accent },
    reviewing: { bg: theme.warningBg, text: theme.warning },
    testing: { bg: theme.infoBg, text: theme.info },
    fixing: { bg: theme.errorBg, text: theme.error },
    completed: { bg: theme.successBg, text: theme.success },
    failed: { bg: theme.errorBg, text: theme.error },
    pending: { bg: `${theme.textDim}22`, text: theme.textDim },
    in_progress: { bg: theme.accentGlow, text: theme.accent },
    review: { bg: theme.warningBg, text: theme.warning },
    revision: { bg: theme.errorBg, text: theme.error },
  };
  const c = colors[status] || colors.created;
  return (
    <span
      style={{
        padding: "2px 10px",
        borderRadius: 20,
        fontSize: 11,
        fontWeight: 600,
        letterSpacing: "0.5px",
        textTransform: "uppercase",
        background: c.bg,
        color: c.text,
        border: `1px solid ${c.text}33`,
      }}
    >
      {status?.replace(/_/g, " ")}
    </span>
  );
};

const ProgressBar = ({ value, height = 6 }) => (
  <div style={{ width: "100%", background: theme.border, borderRadius: height, overflow: "hidden", height }}>
    <div
      style={{
        width: `${Math.min(100, value)}%`,
        height: "100%",
        background: `linear-gradient(90deg, ${theme.accent}, #818cf8)`,
        borderRadius: height,
        transition: "width 0.5s ease",
        boxShadow: value > 0 ? `0 0 12px ${theme.accentGlow}` : "none",
      }}
    />
  </div>
);

const Card = ({ children, style = {}, onClick }) => (
  <div
    onClick={onClick}
    style={{
      background: theme.bgCard,
      border: `1px solid ${theme.border}`,
      borderRadius: 12,
      padding: 20,
      cursor: onClick ? "pointer" : "default",
      transition: "border-color 0.2s, transform 0.15s",
      ...style,
    }}
    onMouseEnter={(e) => {
      if (onClick) {
        e.currentTarget.style.borderColor = theme.borderActive;
        e.currentTarget.style.transform = "translateY(-1px)";
      }
    }}
    onMouseLeave={(e) => {
      e.currentTarget.style.borderColor = theme.border;
      e.currentTarget.style.transform = "translateY(0)";
    }}
  >
    {children}
  </div>
);

const Button = ({ children, onClick, variant = "primary", disabled = false, style = {}, id }) => {
  const variants = {
    primary: { bg: theme.accent, color: "#fff", border: theme.accent },
    ghost: { bg: "transparent", color: theme.textMuted, border: theme.border },
    danger: { bg: theme.error, color: "#fff", border: theme.error },
    success: { bg: theme.success, color: "#fff", border: theme.success },
    warning: { bg: theme.warning, color: "#000", border: theme.warning },
  };
  const v = variants[variant] || variants.primary;
  return (
    <button
      id={id}
      onClick={onClick}
      disabled={disabled}
      style={{
        padding: "8px 20px",
        borderRadius: 8,
        fontSize: 13,
        fontWeight: 600,
        background: disabled ? theme.bgHover : v.bg,
        color: disabled ? theme.textDim : v.color,
        border: `1px solid ${disabled ? theme.border : v.border}`,
        cursor: disabled ? "not-allowed" : "pointer",
        transition: "all 0.2s",
        ...style,
      }}
    >
      {children}
    </button>
  );
};

const Input = ({ value, onChange, placeholder, type = "text", style = {} }) => (
  <input
    type={type}
    value={value}
    onChange={onChange}
    placeholder={placeholder}
    style={{
      width: "100%",
      padding: "10px 14px",
      background: theme.bgInput,
      border: `1px solid ${theme.border}`,
      borderRadius: 8,
      color: theme.text,
      fontSize: 14,
      outline: "none",
      boxSizing: "border-box",
      fontFamily: "inherit",
      transition: "border-color 0.2s",
      ...style,
    }}
    onFocus={(e) => (e.target.style.borderColor = theme.borderActive)}
    onBlur={(e) => (e.target.style.borderColor = theme.border)}
  />
);

const Label = ({ children }) => (
  <div style={{ color: theme.textMuted, fontSize: 11, fontWeight: 600, letterSpacing: "0.5px", textTransform: "uppercase", marginBottom: 6 }}>
    {children}
  </div>
);

const Toast = ({ message, type = "success", onClose }) => {
  useEffect(() => {
    const t = setTimeout(onClose, 3000);
    return () => clearTimeout(t);
  }, [onClose]);
  const colors = { success: theme.success, error: theme.error, info: theme.info };
  return (
    <div style={{
      position: "fixed", bottom: 24, right: 24, zIndex: 9999,
      background: theme.bgCard, border: `1px solid ${colors[type] || theme.border}`,
      borderRadius: 10, padding: "12px 20px", color: colors[type] || theme.text,
      fontSize: 13, fontWeight: 600, boxShadow: "0 4px 24px rgba(0,0,0,0.4)",
      display: "flex", alignItems: "center", gap: 10, maxWidth: 360,
    }}>
      <span>{type === "success" ? "✓" : type === "error" ? "✗" : "ℹ"}</span>
      <span>{message}</span>
      <button onClick={onClose} style={{ background: "none", border: "none", color: theme.textMuted, cursor: "pointer", marginLeft: "auto", fontSize: 16 }}>×</button>
    </div>
  );
};

const SectionHeader = ({ title, subtitle, action }) => (
  <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", marginBottom: 16 }}>
    <div>
      <div style={{ fontSize: 16, fontWeight: 700, color: theme.text }}>{title}</div>
      {subtitle && <div style={{ fontSize: 12, color: theme.textMuted, marginTop: 2 }}>{subtitle}</div>}
    </div>
    {action}
  </div>
);

// ──────────────────────────────────────────────
// LLM Settings Page
// ──────────────────────────────────────────────

const LLMSettingsPage = ({ onBack }) => {
  const [tab, setTab] = useState("providers");
  const [providers, setProviders] = useState([]);
  const [models, setModels] = useState([]);
  const [routing, setRouting] = useState({ low: [], medium: [], high: [], critical: [] });
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState(null);
  const [testResults, setTestResults] = useState({});
  const [testingModel, setTestingModel] = useState(null);

  // Provider edit state
  const [editProvider, setEditProvider] = useState(null); // {id, api_key, base_url, enabled}

  // Model add/edit state
  const [showAddModel, setShowAddModel] = useState(false);
  const [newModel, setNewModel] = useState({ model_id: "", name: "", provider: "openrouter", description: "", enabled: true });
  const [editModel, setEditModel] = useState(null);

  // Routing drag state
  const [dragItem, setDragItem] = useState(null); // {tier, index}

  const showToast = (message, type = "success") => setToast({ message, type });

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [provs, modls, route] = await Promise.all([
        api.getLLMProviders(),
        api.getLLMModels(),
        api.getLLMRouting(),
      ]);
      setProviders(provs);
      setModels(modls);
      setRouting(route);
    } catch (e) {
      showToast("Failed to load LLM configuration", "error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  // ── Provider Save ──
  const handleSaveProvider = async () => {
    if (!editProvider) return;
    try {
      const data = {};
      if (editProvider.api_key) data.api_key = editProvider.api_key;
      if (editProvider.base_url) data.base_url = editProvider.base_url;
      if (editProvider.enabled !== undefined) data.enabled = editProvider.enabled;
      await api.updateLLMProvider(editProvider.id, data);
      setEditProvider(null);
      showToast("Provider updated successfully");
      loadData();
    } catch (e) {
      showToast("Failed to update provider", "error");
    }
  };

  // ── Model Operations ──
  const handleAddModel = async () => {
    try {
      await api.addLLMModel(newModel);
      setShowAddModel(false);
      setNewModel({ model_id: "", name: "", provider: "openrouter", description: "", enabled: true });
      showToast("Model added successfully");
      loadData();
    } catch (e) {
      showToast(e.message || "Failed to add model", "error");
    }
  };

  const handleUpdateModel = async () => {
    if (!editModel) return;
    try {
      await api.updateLLMModel(editModel.id, {
        name: editModel.name,
        enabled: editModel.enabled,
        provider: editModel.provider,
        description: editModel.description,
      });
      setEditModel(null);
      showToast("Model updated");
      loadData();
    } catch (e) {
      showToast("Failed to update model", "error");
    }
  };

  const handleDeleteModel = async (modelId) => {
    if (!confirm(`Delete model "${modelId}"?`)) return;
    try {
      await api.deleteLLMModel(modelId);
      showToast("Model deleted");
      loadData();
    } catch (e) {
      showToast("Failed to delete model", "error");
    }
  };

  // ── Model Test ──
  const handleTestModel = async (modelId) => {
    setTestingModel(modelId);
    try {
      const result = await api.testLLMModel(modelId);
      setTestResults(prev => ({ ...prev, [modelId]: result }));
      showToast(result.success ? `✓ ${modelId} responded in ${result.elapsed_seconds}s` : `✗ ${modelId} failed`, result.success ? "success" : "error");
    } catch (e) {
      showToast("Test request failed", "error");
    } finally {
      setTestingModel(null);
    }
  };

  // ── Routing ──
  const moveModelInTier = (tier, fromIdx, toIdx) => {
    setRouting(prev => {
      const arr = [...(prev[tier] || [])];
      const [item] = arr.splice(fromIdx, 1);
      arr.splice(toIdx, 0, item);
      return { ...prev, [tier]: arr };
    });
  };

  const removeFromTier = (tier, idx) => {
    setRouting(prev => {
      const arr = [...(prev[tier] || [])];
      arr.splice(idx, 1);
      return { ...prev, [tier]: arr };
    });
  };

  const addToTier = (tier, modelId) => {
    if (!modelId) return;
    setRouting(prev => {
      const arr = prev[tier] || [];
      if (arr.includes(modelId)) return prev;
      return { ...prev, [tier]: [...arr, modelId] };
    });
  };

  const handleSaveRouting = async () => {
    try {
      await api.updateLLMRouting(routing);
      showToast("Routing configuration saved & applied");
    } catch (e) {
      showToast("Failed to save routing", "error");
    }
  };

  const tabStyle = (id) => ({
    padding: "10px 20px",
    fontSize: 13,
    fontWeight: 600,
    background: "none",
    border: "none",
    borderBottom: `2px solid ${tab === id ? theme.accent : "transparent"}`,
    color: tab === id ? theme.accent : theme.textMuted,
    cursor: "pointer",
    transition: "all 0.2s",
    whiteSpace: "nowrap",
  });

  if (loading) return (
    <div style={{ padding: 60, textAlign: "center", color: theme.textMuted }}>
      <div style={{ fontSize: 24, marginBottom: 12 }}>⚙️</div>
      Loading LLM configuration...
    </div>
  );

  return (
    <div style={{ maxWidth: 1040, margin: "0 auto", padding: "32px 20px" }}>
      {toast && <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />}

      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 32 }}>
        <button onClick={onBack} style={{ background: "none", border: "none", color: theme.textMuted, cursor: "pointer", fontSize: 18 }}>←</button>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: theme.text, margin: 0 }}>
            ⚙️ LLM Model Settings
          </h1>
          <p style={{ color: theme.textMuted, fontSize: 13, margin: "4px 0 0 0" }}>
            Configure providers, models, and routing — changes apply immediately without restart
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", borderBottom: `1px solid ${theme.border}`, marginBottom: 28, gap: 0, overflowX: "auto" }}>
        {[
          { id: "providers", label: "🔑 Providers & Keys" },
          { id: "models", label: "🤖 Models" },
          { id: "routing", label: "🔀 Task Routing" },
        ].map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} style={tabStyle(t.id)}>{t.label}</button>
        ))}
      </div>

      {/* ── PROVIDERS TAB ── */}
      {tab === "providers" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <SectionHeader
            title="API Providers"
            subtitle="Set your API keys and endpoint URLs for each provider. Keys are stored in memory only."
          />
          {providers.map(prov => (
            <Card key={prov.id} style={{ padding: 0, overflow: "hidden" }}>
              <div style={{ padding: "16px 20px", display: "flex", alignItems: "center", gap: 14 }}>
                {/* Provider icon */}
                <div style={{
                  width: 44, height: 44, borderRadius: 10, flexShrink: 0,
                  background: `${PROVIDER_COLORS[prov.id] || "#444"}22`,
                  border: `1px solid ${PROVIDER_COLORS[prov.id] || "#444"}44`,
                  display: "flex", alignItems: "center", justifyContent: "center", fontSize: 22,
                }}>
                  {PROVIDER_ICONS[prov.id] || "🔌"}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 15, fontWeight: 700, color: theme.text }}>{prov.name}</div>
                  <div style={{ fontSize: 12, color: theme.textMuted, marginTop: 2, fontFamily: "monospace" }}>
                    {prov.base_url}
                  </div>
                </div>
                {/* Key status badge */}
                <span style={{
                  padding: "4px 12px", borderRadius: 20, fontSize: 11, fontWeight: 600,
                  background: prov.has_key ? theme.successBg : theme.errorBg,
                  color: prov.has_key ? theme.success : theme.error,
                  border: `1px solid ${prov.has_key ? theme.success : theme.error}33`,
                }}>
                  {prov.has_key ? "✓ Key Set" : "No Key"}
                </span>
                {/* Enabled toggle */}
                <div style={{
                  padding: "4px 12px", borderRadius: 20, fontSize: 11, fontWeight: 600,
                  background: prov.enabled ? theme.accentGlow : `${theme.textDim}22`,
                  color: prov.enabled ? theme.accent : theme.textDim,
                  border: `1px solid ${prov.enabled ? theme.accent : theme.textDim}33`,
                }}>
                  {prov.enabled ? "Enabled" : "Disabled"}
                </div>
                <Button variant="ghost" onClick={() => setEditProvider({ ...prov, api_key: "" })} style={{ padding: "6px 14px", fontSize: 12 }}>
                  Edit
                </Button>
              </div>

              {/* Collapsible key display */}
              {prov.has_key && (
                <div style={{ padding: "0 20px 14px 78px" }}>
                  <div style={{ fontFamily: "monospace", fontSize: 12, color: theme.textDim, background: theme.bgInput, padding: "6px 12px", borderRadius: 6, display: "inline-block" }}>
                    {prov.api_key_masked}
                  </div>
                </div>
              )}
            </Card>
          ))}

          {/* Edit Provider Modal */}
          {editProvider && (
            <div style={{
              position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", zIndex: 1000,
              display: "flex", alignItems: "center", justifyContent: "center", padding: 20,
            }}>
              <div style={{ background: theme.bgCard, border: `1px solid ${theme.border}`, borderRadius: 16, padding: 32, width: "100%", maxWidth: 520 }}>
                <div style={{ fontSize: 18, fontWeight: 700, color: theme.text, marginBottom: 24 }}>
                  {PROVIDER_ICONS[editProvider.id]} Edit {editProvider.name}
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
                  <div>
                    <Label>API Key {editProvider.has_key && <span style={{ color: theme.textDim, fontWeight: 400 }}>(leave blank to keep existing)</span>}</Label>
                    <Input
                      type="password"
                      value={editProvider.api_key}
                      onChange={e => setEditProvider(p => ({ ...p, api_key: e.target.value }))}
                      placeholder={editProvider.has_key ? "••••••••••••••••••••" : "sk-or-v1-..."}
                    />
                  </div>
                  <div>
                    <Label>Base URL / Endpoint</Label>
                    <Input
                      value={editProvider.base_url}
                      onChange={e => setEditProvider(p => ({ ...p, base_url: e.target.value }))}
                      placeholder="https://openrouter.ai/api/v1/"
                    />
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", color: theme.text, fontSize: 14 }}>
                      <input
                        type="checkbox"
                        checked={editProvider.enabled}
                        onChange={e => setEditProvider(p => ({ ...p, enabled: e.target.checked }))}
                        style={{ width: 16, height: 16, accentColor: theme.accent }}
                      />
                      Enable this provider
                    </label>
                  </div>
                </div>
                <div style={{ display: "flex", gap: 10, marginTop: 28 }}>
                  <Button variant="ghost" onClick={() => setEditProvider(null)} style={{ flex: 1 }}>Cancel</Button>
                  <Button onClick={handleSaveProvider} style={{ flex: 2 }}>Save Changes</Button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── MODELS TAB ── */}
      {tab === "models" && (
        <div>
          <SectionHeader
            title="Available Models"
            subtitle="Manage the models available to FORGE. You can add custom models or disable built-in ones."
            action={
              <Button id="add-model-btn" onClick={() => setShowAddModel(true)} style={{ padding: "7px 16px", fontSize: 12 }}>
                + Add Custom Model
              </Button>
            }
          />

          {/* Add Model Panel */}
          {showAddModel && (
            <Card style={{ marginBottom: 20, border: `1px solid ${theme.accent}44`, background: `${theme.accentGlow}` }}>
              <div style={{ fontSize: 14, fontWeight: 700, color: theme.text, marginBottom: 16 }}>➕ Add Custom Model</div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                <div>
                  <Label>Model ID (LiteLLM format)</Label>
                  <Input value={newModel.model_id} onChange={e => setNewModel(p => ({ ...p, model_id: e.target.value }))} placeholder="openrouter/meta-llama/llama-3.3-70b-instruct:free" />
                </div>
                <div>
                  <Label>Display Name</Label>
                  <Input value={newModel.name} onChange={e => setNewModel(p => ({ ...p, name: e.target.value }))} placeholder="Llama 3.3 70B" />
                </div>
                <div>
                  <Label>Provider</Label>
                  <select value={newModel.provider} onChange={e => setNewModel(p => ({ ...p, provider: e.target.value }))}
                    style={{ width: "100%", padding: "10px 14px", background: theme.bgInput, border: `1px solid ${theme.border}`, borderRadius: 8, color: theme.text, fontSize: 14, outline: "none" }}>
                    <option value="openrouter">OpenRouter</option>
                    <option value="anthropic">Anthropic</option>
                    <option value="openai">OpenAI</option>
                    <option value="google">Google</option>
                  </select>
                </div>
                <div>
                  <Label>Description (optional)</Label>
                  <Input value={newModel.description} onChange={e => setNewModel(p => ({ ...p, description: e.target.value }))} placeholder="Fast, cost-effective..." />
                </div>
              </div>
              <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
                <Button variant="ghost" onClick={() => setShowAddModel(false)}>Cancel</Button>
                <Button onClick={handleAddModel} disabled={!newModel.model_id.trim() || !newModel.name.trim()}>Add Model</Button>
              </div>
            </Card>
          )}

          {/* Model Edit Modal */}
          {editModel && (
            <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
              <div style={{ background: theme.bgCard, border: `1px solid ${theme.border}`, borderRadius: 16, padding: 32, width: "100%", maxWidth: 480 }}>
                <div style={{ fontSize: 18, fontWeight: 700, color: theme.text, marginBottom: 24 }}>✏️ Edit Model</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                  <div>
                    <Label>Model ID</Label>
                    <div style={{ padding: "10px 14px", background: theme.bgHover, borderRadius: 8, fontSize: 12, color: theme.textDim, fontFamily: "monospace" }}>{editModel.id}</div>
                  </div>
                  <div>
                    <Label>Display Name</Label>
                    <Input value={editModel.name} onChange={e => setEditModel(p => ({ ...p, name: e.target.value }))} />
                  </div>
                  <div>
                    <Label>Provider</Label>
                    <select value={editModel.provider} onChange={e => setEditModel(p => ({ ...p, provider: e.target.value }))}
                      style={{ width: "100%", padding: "10px 14px", background: theme.bgInput, border: `1px solid ${theme.border}`, borderRadius: 8, color: theme.text, fontSize: 14, outline: "none" }}>
                      <option value="openrouter">OpenRouter</option>
                      <option value="anthropic">Anthropic</option>
                      <option value="openai">OpenAI</option>
                      <option value="google">Google</option>
                    </select>
                  </div>
                  <div>
                    <Label>Description</Label>
                    <Input value={editModel.description || ""} onChange={e => setEditModel(p => ({ ...p, description: e.target.value }))} />
                  </div>
                  <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", color: theme.text, fontSize: 14 }}>
                    <input type="checkbox" checked={editModel.enabled} onChange={e => setEditModel(p => ({ ...p, enabled: e.target.checked }))} style={{ width: 16, height: 16, accentColor: theme.accent }} />
                    Enabled
                  </label>
                </div>
                <div style={{ display: "flex", gap: 10, marginTop: 24 }}>
                  <Button variant="ghost" onClick={() => setEditModel(null)} style={{ flex: 1 }}>Cancel</Button>
                  <Button onClick={handleUpdateModel} style={{ flex: 2 }}>Save Changes</Button>
                </div>
              </div>
            </div>
          )}

          {/* Model List */}
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {/* Group by provider */}
            {["openrouter", "anthropic", "openai", "google"].map(provId => {
              const provModels = models.filter(m => m.provider === provId);
              if (provModels.length === 0) return null;
              return (
                <div key={provId}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8, marginTop: 16 }}>
                    <span style={{ fontSize: 16 }}>{PROVIDER_ICONS[provId]}</span>
                    <span style={{ fontSize: 12, fontWeight: 700, color: PROVIDER_COLORS[provId] || theme.textMuted, textTransform: "uppercase", letterSpacing: "0.5px" }}>
                      {provId}
                    </span>
                    <div style={{ flex: 1, height: 1, background: theme.border }} />
                  </div>
                  {provModels.map(model => {
                    const testResult = testResults[model.id];
                    const isTesting = testingModel === model.id;
                    return (
                      <div key={model.id} style={{
                        display: "flex", alignItems: "center", gap: 12,
                        padding: "12px 16px",
                        background: theme.bgCard,
                        border: `1px solid ${model.enabled ? theme.border : theme.textDim + "33"}`,
                        borderRadius: 10, marginBottom: 6,
                        opacity: model.enabled ? 1 : 0.5,
                        transition: "all 0.2s",
                      }}>
                        {/* Enable toggle dot */}
                        <div style={{
                          width: 8, height: 8, borderRadius: "50%", flexShrink: 0,
                          background: model.enabled ? theme.success : theme.textDim,
                          boxShadow: model.enabled ? `0 0 6px ${theme.success}` : "none",
                        }} />
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontSize: 13, fontWeight: 600, color: theme.text }}>{model.name}</div>
                          <div style={{ fontSize: 11, color: theme.textDim, fontFamily: "monospace", marginTop: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {model.model_id}
                          </div>
                          {model.description && <div style={{ fontSize: 11, color: theme.textMuted, marginTop: 2 }}>{model.description}</div>}
                        </div>

                        {/* Test result */}
                        {testResult && (
                          <span style={{
                            fontSize: 11, padding: "3px 8px", borderRadius: 6, fontFamily: "monospace",
                            background: testResult.success ? theme.successBg : theme.errorBg,
                            color: testResult.success ? theme.success : theme.error,
                          }}>
                            {testResult.success ? `✓ ${testResult.elapsed_seconds}s` : "✗ fail"}
                          </span>
                        )}

                        {model.custom && (
                          <span style={{ fontSize: 10, padding: "2px 6px", borderRadius: 4, background: theme.accentGlow, color: theme.accent, fontWeight: 600 }}>CUSTOM</span>
                        )}

                        {/* Actions */}
                        <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                          <Button
                            id={`test-model-${model.id}`}
                            variant="ghost"
                            disabled={isTesting}
                            onClick={() => handleTestModel(model.id)}
                            style={{ padding: "4px 10px", fontSize: 11 }}
                          >
                            {isTesting ? "⏳" : "▶ Test"}
                          </Button>
                          <Button
                            variant="ghost"
                            onClick={() => setEditModel({ ...model })}
                            style={{ padding: "4px 10px", fontSize: 11 }}
                          >
                            Edit
                          </Button>
                          {model.custom && (
                            <Button
                              variant="danger"
                              onClick={() => handleDeleteModel(model.id)}
                              style={{ padding: "4px 10px", fontSize: 11 }}
                            >
                              Del
                            </Button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── ROUTING TAB ── */}
      {tab === "routing" && (
        <div>
          <SectionHeader
            title="Task Complexity → Model Routing"
            subtitle="Configure which models handle each complexity tier. Order = fallback priority (first = primary, rest = fallbacks)."
            action={
              <Button id="save-routing-btn" onClick={handleSaveRouting} variant="success" style={{ padding: "7px 18px", fontSize: 12 }}>
                💾 Apply Routing
              </Button>
            }
          />

          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            {["low", "medium", "high", "critical"].map(tier => (
              <Card key={tier} style={{ padding: 0, overflow: "hidden", border: `1px solid ${TIER_COLORS[tier]}33` }}>
                {/* Tier header */}
                <div style={{
                  padding: "12px 20px",
                  background: `${TIER_COLORS[tier]}11`,
                  borderBottom: `1px solid ${TIER_COLORS[tier]}22`,
                  display: "flex", alignItems: "center", gap: 12,
                }}>
                  <div style={{ width: 10, height: 10, borderRadius: "50%", background: TIER_COLORS[tier], boxShadow: `0 0 8px ${TIER_COLORS[tier]}` }} />
                  <span style={{ fontSize: 14, fontWeight: 700, color: TIER_COLORS[tier] }}>
                    {TIER_LABELS[tier]} Complexity
                  </span>
                  <span style={{ fontSize: 12, color: theme.textMuted }}>
                    {(routing[tier] || []).length} model{(routing[tier] || []).length !== 1 ? "s" : ""} configured
                  </span>
                </div>

                <div style={{ padding: 16 }}>
                  {/* Model chain */}
                  <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 12 }}>
                    {(routing[tier] || []).length === 0 ? (
                      <div style={{ padding: "16px", textAlign: "center", color: theme.textDim, fontSize: 13, border: `1px dashed ${theme.border}`, borderRadius: 8 }}>
                        No models configured — add some below
                      </div>
                    ) : (
                      (routing[tier] || []).map((modelId, idx) => (
                        <div key={`${tier}-${idx}`} style={{
                          display: "flex", alignItems: "center", gap: 10,
                          padding: "10px 14px",
                          background: idx === 0 ? `${TIER_COLORS[tier]}11` : theme.bgInput,
                          border: `1px solid ${idx === 0 ? TIER_COLORS[tier] + "33" : theme.border}`,
                          borderRadius: 8,
                        }}>
                          {/* Order badge */}
                          <span style={{
                            width: 22, height: 22, borderRadius: "50%", flexShrink: 0,
                            display: "flex", alignItems: "center", justifyContent: "center",
                            fontSize: 11, fontWeight: 700,
                            background: idx === 0 ? TIER_COLORS[tier] : theme.bgHover,
                            color: idx === 0 ? "#fff" : theme.textMuted,
                          }}>
                            {idx + 1}
                          </span>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ fontSize: 13, fontWeight: 600, color: idx === 0 ? theme.text : theme.textMuted }}>
                              {models.find(m => m.id === modelId)?.name || modelId}
                            </div>
                            <div style={{ fontSize: 10, color: theme.textDim, fontFamily: "monospace", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                              {modelId}
                            </div>
                          </div>
                          {idx === 0 && (
                            <span style={{ fontSize: 10, padding: "2px 7px", borderRadius: 4, background: `${TIER_COLORS[tier]}22`, color: TIER_COLORS[tier], fontWeight: 600, textTransform: "uppercase" }}>
                              Primary
                            </span>
                          )}
                          {idx > 0 && (
                            <span style={{ fontSize: 10, padding: "2px 7px", borderRadius: 4, background: theme.bgHover, color: theme.textDim, fontWeight: 600, textTransform: "uppercase" }}>
                              Fallback {idx}
                            </span>
                          )}
                          {/* Up/Down arrows */}
                          <div style={{ display: "flex", flexDirection: "column", gap: 2, flexShrink: 0 }}>
                            <button
                              disabled={idx === 0}
                              onClick={() => moveModelInTier(tier, idx, idx - 1)}
                              style={{ background: "none", border: "none", color: idx === 0 ? theme.textDim : theme.textMuted, cursor: idx === 0 ? "default" : "pointer", fontSize: 12, lineHeight: 1, padding: "1px 4px" }}
                            >▲</button>
                            <button
                              disabled={idx === (routing[tier] || []).length - 1}
                              onClick={() => moveModelInTier(tier, idx, idx + 1)}
                              style={{ background: "none", border: "none", color: idx === (routing[tier] || []).length - 1 ? theme.textDim : theme.textMuted, cursor: idx === (routing[tier] || []).length - 1 ? "default" : "pointer", fontSize: 12, lineHeight: 1, padding: "1px 4px" }}
                            >▼</button>
                          </div>
                          <button
                            onClick={() => removeFromTier(tier, idx)}
                            style={{ background: "none", border: "none", color: theme.error, cursor: "pointer", fontSize: 14, padding: "2px 4px" }}
                          >×</button>
                        </div>
                      ))
                    )}
                  </div>

                  {/* Add model to tier */}
                  <AddModelToTier tier={tier} models={models} existing={routing[tier] || []} onAdd={addToTier} />
                </div>
              </Card>
            ))}
          </div>

          <div style={{ marginTop: 24, padding: 16, background: theme.bgCard, border: `1px solid ${theme.border}`, borderRadius: 10 }}>
            <div style={{ fontSize: 12, color: theme.textMuted, lineHeight: 1.6 }}>
              <strong style={{ color: theme.text }}>How routing works:</strong> When an agent needs to make an LLM call, it specifies a task complexity level.
              The first model in the tier's list is tried first. If it fails, the system automatically falls back to the next model in order.
              Changes here take effect immediately — no restart required.
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// Sub-component for adding a model to a tier
const AddModelToTier = ({ tier, models, existing, onAdd }) => {
  const [selected, setSelected] = useState("");
  const available = models.filter(m => m.enabled && !existing.includes(m.id));

  return (
    <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
      <select
        value={selected}
        onChange={e => setSelected(e.target.value)}
        style={{ flex: 1, padding: "8px 12px", background: theme.bgInput, border: `1px solid ${theme.border}`, borderRadius: 8, color: selected ? theme.text : theme.textDim, fontSize: 13, outline: "none" }}
      >
        <option value="">+ Add model to {tier} tier...</option>
        {["openrouter", "anthropic", "openai", "google"].map(prov => {
          const provModels = available.filter(m => m.provider === prov);
          if (provModels.length === 0) return null;
          return (
            <optgroup key={prov} label={prov.toUpperCase()}>
              {provModels.map(m => (
                <option key={m.id} value={m.id}>{m.name} ({m.model_id})</option>
              ))}
            </optgroup>
          );
        })}
      </select>
      <Button
        variant="ghost"
        disabled={!selected}
        onClick={() => { onAdd(tier, selected); setSelected(""); }}
        style={{ padding: "8px 14px", fontSize: 12, flexShrink: 0 }}
      >
        Add
      </Button>
    </div>
  );
};

// ──────────────────────────────────────────────
// Pages
// ──────────────────────────────────────────────

const CreateProjectPage = ({ onCreated, onCancel }) => {
  const [name, setName] = useState("");
  const [techStack, setTechStack] = useState("flutter");
  const [backendStack, setBackendStack] = useState("");
  const [inputType, setInputType] = useState("requirements");
  const [requirements, setRequirements] = useState("");
  const [htmlInput, setHtmlInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [step, setStep] = useState(1);

  const stacks = [
    { value: "flutter", label: "Flutter", icon: "📱" },
    { value: "react", label: "React", icon: "⚛️" },
    { value: "angular", label: "Angular", icon: "🅰️" },
    { value: "vue", label: "Vue", icon: "💚" },
    { value: "nextjs", label: "Next.js", icon: "▲" },
    { value: "dotnet", label: ".NET Blazor", icon: "🔷" },
  ];

  const backendStacks = [
    { value: "", label: "None (frontend only)" },
    { value: "fastapi", label: "FastAPI (Python)" },
    { value: "dotnet", label: ".NET Web API" },
    { value: "express", label: "Express.js" },
    { value: "django", label: "Django" },
    { value: "spring_boot", label: "Spring Boot" },
  ];

  const handleBuild = async () => {
    setLoading(true);
    try {
      const project = await api.createProject({
        name,
        tech_stack: techStack,
        backend_stack: backendStack || null,
        description: requirements.slice(0, 200),
      });

      if (inputType === "requirements") {
        await api.buildFromRequirements(project.id, requirements);
      } else {
        const files = {};
        const sections = htmlInput.split(/---\s*FILE:\s*/i).filter(Boolean);
        if (sections.length <= 1) {
          files["index.html"] = htmlInput;
        } else {
          for (const section of sections) {
            const lineEnd = section.indexOf("\n");
            const fname = section.slice(0, lineEnd).trim() || "page.html";
            files[fname] = section.slice(lineEnd + 1).trim();
          }
        }
        await api.buildFromHtml(project.id, files);
      }

      onCreated(project.id);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 720, margin: "0 auto", padding: "40px 20px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 32 }}>
        <button onClick={onCancel} style={{ background: "none", border: "none", color: theme.textMuted, cursor: "pointer", fontSize: 18 }}>←</button>
        <h1 style={{ fontSize: 24, fontWeight: 700, color: theme.text, margin: 0 }}>New Project</h1>
      </div>

      {step === 1 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          <div>
            <label style={{ color: theme.textMuted, fontSize: 12, fontWeight: 600, letterSpacing: "0.5px", textTransform: "uppercase", marginBottom: 8, display: "block" }}>
              Project Name
            </label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="My Enterprise App"
              style={{
                width: "100%",
                padding: "12px 16px",
                background: theme.bgInput,
                border: `1px solid ${theme.border}`,
                borderRadius: 8,
                color: theme.text,
                fontSize: 15,
                outline: "none",
                boxSizing: "border-box",
              }}
            />
          </div>

          <div>
            <label style={{ color: theme.textMuted, fontSize: 12, fontWeight: 600, letterSpacing: "0.5px", textTransform: "uppercase", marginBottom: 12, display: "block" }}>
              Frontend Stack
            </label>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8 }}>
              {stacks.map((s) => (
                <div
                  key={s.value}
                  onClick={() => setTechStack(s.value)}
                  style={{
                    padding: "14px 12px",
                    borderRadius: 8,
                    border: `1px solid ${techStack === s.value ? theme.accent : theme.border}`,
                    background: techStack === s.value ? theme.accentGlow : theme.bgCard,
                    cursor: "pointer",
                    textAlign: "center",
                    transition: "all 0.2s",
                  }}
                >
                  <div style={{ fontSize: 22, marginBottom: 4 }}>{s.icon}</div>
                  <div style={{ fontSize: 12, color: techStack === s.value ? theme.accent : theme.textMuted, fontWeight: 600 }}>
                    {s.label}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div>
            <label style={{ color: theme.textMuted, fontSize: 12, fontWeight: 600, letterSpacing: "0.5px", textTransform: "uppercase", marginBottom: 8, display: "block" }}>
              Backend Stack
            </label>
            <select
              value={backendStack}
              onChange={(e) => setBackendStack(e.target.value)}
              style={{
                width: "100%",
                padding: "12px 16px",
                background: theme.bgInput,
                border: `1px solid ${theme.border}`,
                borderRadius: 8,
                color: theme.text,
                fontSize: 14,
                outline: "none",
              }}
            >
              {backendStacks.map((b) => (
                <option key={b.value} value={b.value}>{b.label}</option>
              ))}
            </select>
          </div>

          <Button onClick={() => setStep(2)} disabled={!name.trim()} style={{ width: "100%", padding: "14px" }}>
            Continue →
          </Button>
        </div>
      )}

      {step === 2 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          <div>
            <label style={{ color: theme.textMuted, fontSize: 12, fontWeight: 600, letterSpacing: "0.5px", textTransform: "uppercase", marginBottom: 12, display: "block" }}>
              Input Type
            </label>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              {[
                { value: "requirements", label: "Business Requirements", desc: "Describe what to build" },
                { value: "html", label: "HTML Mockups", desc: "Paste HTML mockup code" },
              ].map((t) => (
                <div
                  key={t.value}
                  onClick={() => setInputType(t.value)}
                  style={{
                    padding: 16,
                    borderRadius: 8,
                    border: `1px solid ${inputType === t.value ? theme.accent : theme.border}`,
                    background: inputType === t.value ? theme.accentGlow : theme.bgCard,
                    cursor: "pointer",
                  }}
                >
                  <div style={{ fontSize: 14, fontWeight: 600, color: inputType === t.value ? theme.accent : theme.text, marginBottom: 4 }}>
                    {t.label}
                  </div>
                  <div style={{ fontSize: 12, color: theme.textMuted }}>{t.desc}</div>
                </div>
              ))}
            </div>
          </div>

          {inputType === "requirements" ? (
            <div>
              <label style={{ color: theme.textMuted, fontSize: 12, fontWeight: 600, letterSpacing: "0.5px", textTransform: "uppercase", marginBottom: 8, display: "block" }}>
                Business Requirements
              </label>
              <textarea
                value={requirements}
                onChange={(e) => setRequirements(e.target.value)}
                placeholder={`Describe your application in detail:\n\n• What does the app do?\n• Who are the users?\n• What are the main features?\n• What data does it manage?\n• Any specific business rules?`}
                rows={14}
                style={{
                  width: "100%",
                  padding: "14px 16px",
                  background: theme.bgInput,
                  border: `1px solid ${theme.border}`,
                  borderRadius: 8,
                  color: theme.text,
                  fontSize: 14,
                  lineHeight: 1.6,
                  resize: "vertical",
                  outline: "none",
                  fontFamily: "inherit",
                  boxSizing: "border-box",
                }}
              />
            </div>
          ) : (
            <div>
              <label style={{ color: theme.textMuted, fontSize: 12, fontWeight: 600, letterSpacing: "0.5px", textTransform: "uppercase", marginBottom: 8, display: "block" }}>
                HTML Mockup Code
              </label>
              <div style={{ fontSize: 11, color: theme.textDim, marginBottom: 8 }}>
                Paste HTML code. For multiple files, separate with: --- FILE: filename.html
              </div>
              <textarea
                value={htmlInput}
                onChange={(e) => setHtmlInput(e.target.value)}
                placeholder="<html>..."
                rows={14}
                style={{
                  width: "100%",
                  padding: "14px 16px",
                  background: theme.bgInput,
                  border: `1px solid ${theme.border}`,
                  borderRadius: 8,
                  color: theme.text,
                  fontSize: 13,
                  lineHeight: 1.5,
                  resize: "vertical",
                  outline: "none",
                  fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                  boxSizing: "border-box",
                }}
              />
            </div>
          )}

          <div style={{ display: "flex", gap: 10 }}>
            <Button variant="ghost" onClick={() => setStep(1)} style={{ flex: 1, padding: "14px" }}>← Back</Button>
            <Button
              onClick={handleBuild}
              disabled={loading || (inputType === "requirements" ? !requirements.trim() : !htmlInput.trim())}
              style={{ flex: 2, padding: "14px" }}
            >
              {loading ? "⏳ Starting Build..." : "🚀 Start Build"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
};

// ──────────────────────────────────────────────
// Project Detail / Build Monitor Page
// ──────────────────────────────────────────────

const ProjectDetailPage = ({ projectId, onBack }) => {
  const [project, setProject] = useState(null);
  const [events, setEvents] = useState([]);
  const [workUnits, setWorkUnits] = useState([]);
  const [files, setFiles] = useState({});
  const [selectedFile, setSelectedFile] = useState(null);
  const [tab, setTab] = useState("live");
  const [feedback, setFeedback] = useState("");
  const [feedbackSending, setFeedbackSending] = useState(false);
  const eventsEndRef = useRef(null);
  const wsRef = useRef(null);

  // Polling + WebSocket
  useEffect(() => {
    const fetchData = async () => {
      try {
        const p = await api.getProject(projectId);
        setProject(p);
        if (p.status === "completed" || p.status === "failed") {
          try {
            const f = await api.getFiles(projectId);
            setFiles(f.files || {});
          } catch {}
        }
        try {
          const wu = await api.getWorkUnits(projectId);
          setWorkUnits(wu);
        } catch {}
      } catch (e) {
        console.error(e);
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 3000);

    // WebSocket for events
    try {
      const wsBase = API_URL || `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`;
      const wsUrl = wsBase.replace(/^http/, "ws");
      const ws = new WebSocket(`${wsUrl}/ws/projects/${projectId}`);
      ws.onmessage = (e) => {
        const event = JSON.parse(e.data);
        if (event.type !== "ping") {
          setEvents((prev) => [...prev, event]);
        }
      };
      ws.onerror = () => {
        const pollEvents = async () => {
          try {
            const evts = await api.getEvents(projectId);
            setEvents(evts);
          } catch {}
        };
        const evtInterval = setInterval(pollEvents, 2000);
        return () => clearInterval(evtInterval);
      };
      wsRef.current = ws;
    } catch {}

    return () => {
      clearInterval(interval);
      wsRef.current?.close();
    };
  }, [projectId]);

  useEffect(() => {
    eventsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events]);

  const handleFeedback = async () => {
    if (!feedback.trim()) return;
    setFeedbackSending(true);
    try {
      await api.submitFeedback(projectId, feedback);
      setFeedback("");
    } catch (e) {
      console.error(e);
    } finally {
      setFeedbackSending(false);
    }
  };

  if (!project) {
    return (
      <div style={{ padding: 40, textAlign: "center", color: theme.textMuted }}>
        Loading project...
      </div>
    );
  }

  const tabs = [
    { id: "live", label: "Live Feed" },
    { id: "units", label: `Work Units (${workUnits.length})` },
    { id: "files", label: `Files (${Object.keys(files).length})` },
    { id: "feedback", label: "Feedback" },
  ];

  return (
    <div style={{ maxWidth: 960, margin: "0 auto", padding: "24px 20px" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
        <button onClick={onBack} style={{ background: "none", border: "none", color: theme.textMuted, cursor: "pointer", fontSize: 18 }}>←</button>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: theme.text, margin: 0, flex: 1 }}>{project.name}</h1>
        {project.status === "failed" && (
          <Button
            variant="primary"
            onClick={async () => {
              try {
                await api.rebuildProject(projectId);
                setProject(prev => ({ ...prev, status: "analyzing" }));
              } catch (e) { console.error(e); }
            }}
            style={{ padding: "6px 12px", fontSize: 12 }}
          >
            🔄 Retry Build
          </Button>
        )}
        <StatusBadge status={project.status} />
      </div>

      {/* Progress */}
      <div style={{ marginBottom: 24, paddingLeft: 32 }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6, fontSize: 12, color: theme.textMuted }}>
          <span>Wave {(project.current_wave || 0) + 1} / {project.total_waves || "?"}</span>
          <span>{project.completed_work_units} / {project.total_work_units} units</span>
        </div>
        <ProgressBar value={project.progress || 0} height={8} />
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 2, marginBottom: 20, borderBottom: `1px solid ${theme.border}` }}>
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            style={{
              padding: "10px 18px",
              fontSize: 13,
              fontWeight: 600,
              background: "none",
              border: "none",
              borderBottom: `2px solid ${tab === t.id ? theme.accent : "transparent"}`,
              color: tab === t.id ? theme.accent : theme.textMuted,
              cursor: "pointer",
              transition: "all 0.2s",
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {tab === "live" && (
        <Card style={{ maxHeight: 500, overflowY: "auto", padding: 0 }}>
          {events.length === 0 ? (
            <div style={{ padding: 40, textAlign: "center", color: theme.textDim }}>
              {project.status === "created" ? "Waiting for build to start..." : "Connecting to build stream..."}
            </div>
          ) : (
            <div style={{ padding: "8px 0" }}>
              {events.map((evt, i) => (
                <div
                  key={i}
                  style={{
                    padding: "8px 16px",
                    display: "flex",
                    gap: 10,
                    alignItems: "flex-start",
                    borderBottom: `1px solid ${theme.border}08`,
                    fontSize: 13,
                  }}
                >
                  <span style={{ color: theme.textDim, fontSize: 11, minWidth: 56, fontFamily: "monospace", paddingTop: 2 }}>
                    {new Date(evt.timestamp).toLocaleTimeString("en", { hour12: false })}
                  </span>
                  {evt.agent && (
                    <span
                      style={{
                        fontSize: 10,
                        fontWeight: 700,
                        padding: "2px 8px",
                        borderRadius: 4,
                        background: `${agentColors[evt.agent] || theme.textDim}18`,
                        color: agentColors[evt.agent] || theme.textDim,
                        minWidth: 70,
                        textAlign: "center",
                        textTransform: "uppercase",
                        letterSpacing: "0.3px",
                      }}
                    >
                      {evt.agent}
                    </span>
                  )}
                  <span style={{ color: evt.event_type === "error" ? theme.error : theme.text, flex: 1, lineHeight: 1.4 }}>
                    {evt.message}
                  </span>
                </div>
              ))}
              <div ref={eventsEndRef} />
            </div>
          )}
        </Card>
      )}

      {tab === "units" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {workUnits.length === 0 ? (
            <Card><div style={{ textAlign: "center", color: theme.textDim, padding: 20 }}>No work units yet</div></Card>
          ) : (
            workUnits.map((wu, i) => (
              <Card key={i} style={{ padding: 14 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <span style={{ fontSize: 10, color: theme.textDim, fontFamily: "monospace" }}>W{wu.wave}</span>
                    <span style={{ fontSize: 14, fontWeight: 600, color: theme.text }}>{wu.title}</span>
                  </div>
                  <StatusBadge status={wu.status} />
                </div>
                <div style={{ fontSize: 12, color: theme.textMuted, marginBottom: 4 }}>{wu.description?.slice(0, 120)}</div>
                <div style={{ display: "flex", gap: 12, fontSize: 11, color: theme.textDim }}>
                  <span>Type: {wu.type}</span>
                  {wu.assigned_agent && <span>Agent: {wu.assigned_agent}</span>}
                  {wu.review_score != null && <span>Score: {wu.review_score}/10</span>}
                  {wu.fix_attempts > 0 && <span>Fixes: {wu.fix_attempts}</span>}
                </div>
              </Card>
            ))
          )}
        </div>
      )}

      {tab === "files" && (
        <div style={{ display: "grid", gridTemplateColumns: "240px 1fr", gap: 12, minHeight: 400 }}>
          <Card style={{ padding: 8, overflowY: "auto", maxHeight: 500 }}>
            {Object.keys(files).length === 0 ? (
              <div style={{ padding: 20, textAlign: "center", color: theme.textDim, fontSize: 12 }}>
                No files generated yet
              </div>
            ) : (
              Object.keys(files).sort().map((fp) => (
                <div
                  key={fp}
                  onClick={() => setSelectedFile(fp)}
                  style={{
                    padding: "6px 10px",
                    fontSize: 12,
                    color: selectedFile === fp ? theme.accent : theme.textMuted,
                    background: selectedFile === fp ? theme.accentGlow : "transparent",
                    borderRadius: 4,
                    cursor: "pointer",
                    fontFamily: "'JetBrains Mono', monospace",
                    wordBreak: "break-all",
                  }}
                >
                  {fp}
                </div>
              ))
            )}
          </Card>
          <Card style={{ padding: 0, overflow: "hidden" }}>
            {selectedFile ? (
              <div>
                <div style={{
                  padding: "8px 14px",
                  borderBottom: `1px solid ${theme.border}`,
                  fontSize: 12,
                  color: theme.textMuted,
                  fontFamily: "monospace",
                  background: theme.bgHover,
                }}>
                  {selectedFile}
                </div>
                <pre style={{
                  padding: 14,
                  margin: 0,
                  fontSize: 12,
                  color: theme.text,
                  fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                  lineHeight: 1.6,
                  overflowX: "auto",
                  maxHeight: 440,
                  overflowY: "auto",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                }}>
                  {files[selectedFile]}
                </pre>
              </div>
            ) : (
              <div style={{ padding: 40, textAlign: "center", color: theme.textDim }}>
                Select a file to view
              </div>
            )}
          </Card>
        </div>
      )}

      {tab === "feedback" && (
        <Card>
          <div style={{ marginBottom: 16 }}>
            <label style={{ color: theme.textMuted, fontSize: 12, fontWeight: 600, letterSpacing: "0.5px", textTransform: "uppercase", marginBottom: 8, display: "block" }}>
              Describe what needs to change
            </label>
            <textarea
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              placeholder="e.g., The login button should be larger, the header color should be blue..."
              rows={5}
              style={{
                width: "100%",
                padding: "12px 14px",
                background: theme.bgInput,
                border: `1px solid ${theme.border}`,
                borderRadius: 8,
                color: theme.text,
                fontSize: 14,
                resize: "vertical",
                outline: "none",
                fontFamily: "inherit",
                boxSizing: "border-box",
              }}
            />
          </div>
          <Button onClick={handleFeedback} disabled={!feedback.trim() || feedbackSending}>
            {feedbackSending ? "Submitting..." : "Submit Feedback"}
          </Button>
          {project.feedback_history?.length > 0 && (
            <div style={{ marginTop: 20 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: theme.textMuted, marginBottom: 8, textTransform: "uppercase", letterSpacing: "0.5px" }}>
                Previous Feedback
              </div>
              {project.feedback_history.map((fb, i) => (
                <div key={i} style={{ padding: "8px 12px", borderLeft: `3px solid ${fb.resolved ? theme.success : theme.warning}`, marginBottom: 6, fontSize: 13, color: theme.text, background: theme.bgHover, borderRadius: "0 6px 6px 0" }}>
                  {fb.description}
                  <span style={{ marginLeft: 8, fontSize: 11, color: fb.resolved ? theme.success : theme.warning }}>
                    {fb.resolved ? "✓ Resolved" : "⏳ Pending"}
                  </span>
                </div>
              ))}
            </div>
          )}
        </Card>
      )}
    </div>
  );
};

// ──────────────────────────────────────────────
// Home / Project List Page
// ──────────────────────────────────────────────

const HomePage = ({ onSelectProject, onNewProject, onSettings }) => {
  const [projects, setProjects] = useState([]);
  const [metrics, setMetrics] = useState({});

  useEffect(() => {
    const fetch = async () => {
      try { setProjects(await api.listProjects()); } catch {}
      try { setMetrics(await api.getMetrics()); } catch {}
    };
    fetch();
    const i = setInterval(fetch, 5000);
    return () => clearInterval(i);
  }, []);

  const totalCalls = Object.values(metrics).reduce((s, m) => s + (m.total_calls || 0), 0);
  const totalTokens = Object.values(metrics).reduce((s, m) => s + (m.total_input_tokens || 0) + (m.total_output_tokens || 0), 0);

  return (
    <div style={{ maxWidth: 960, margin: "0 auto", padding: "40px 20px" }}>
      {/* Hero */}
      <div style={{ textAlign: "center", marginBottom: 48 }}>
        <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}>
          <button
            id="llm-settings-btn"
            onClick={onSettings}
            title="LLM Model Settings"
            style={{
              background: "none",
              border: `1px solid ${theme.border}`,
              borderRadius: 8,
              color: theme.textMuted,
              cursor: "pointer",
              fontSize: 13,
              fontWeight: 600,
              padding: "7px 14px",
              display: "flex",
              alignItems: "center",
              gap: 6,
              transition: "all 0.2s",
            }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = theme.accent; e.currentTarget.style.color = theme.accent; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = theme.border; e.currentTarget.style.color = theme.textMuted; }}
          >
            ⚙️ LLM Settings
          </button>
        </div>
        <h1 style={{ fontSize: 40, fontWeight: 800, color: theme.text, margin: "0 0 8px 0", letterSpacing: "-1px" }}>
          <span style={{ color: theme.accent }}>⚒</span> FORGE
        </h1>
        <p style={{ color: theme.textMuted, fontSize: 15, margin: 0 }}>
          Factory for Orchestrated Reliable Generation of Enterprise-software
        </p>
      </div>

      {/* Stats Bar */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, marginBottom: 32 }}>
        {[
          { label: "Projects", value: projects.length },
          { label: "LLM Calls", value: totalCalls },
          { label: "Tokens Used", value: totalTokens > 1000000 ? `${(totalTokens / 1000000).toFixed(1)}M` : totalTokens > 1000 ? `${(totalTokens / 1000).toFixed(0)}K` : totalTokens },
        ].map((s) => (
          <Card key={s.label} style={{ textAlign: "center", padding: 16 }}>
            <div style={{ fontSize: 28, fontWeight: 800, color: theme.accent }}>{s.value}</div>
            <div style={{ fontSize: 11, color: theme.textMuted, textTransform: "uppercase", letterSpacing: "0.5px" }}>{s.label}</div>
          </Card>
        ))}
      </div>

      {/* New Project Button */}
      <Button id="create-project-btn" onClick={onNewProject} style={{ width: "100%", padding: 16, fontSize: 15, marginBottom: 24 }}>
        + Create New Project
      </Button>

      {/* Project List */}
      {projects.length > 0 && (
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: theme.textMuted, textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: 12 }}>
            Projects
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {projects.map((p) => (
              <Card key={p.id} onClick={() => onSelectProject(p.id)} style={{ padding: 16 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                  <span style={{ fontSize: 16, fontWeight: 700, color: theme.text }}>{p.name}</span>
                  <StatusBadge status={p.status} />
                </div>
                <ProgressBar value={p.progress} />
                <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8, fontSize: 12, color: theme.textMuted }}>
                  <span>{p.tech_stack}</span>
                  <span>{p.completed_work_units}/{p.total_work_units} units</span>
                </div>
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

// ──────────────────────────────────────────────
// App Root
// ──────────────────────────────────────────────

export default function App() {
  const [page, setPage] = useState("home"); // "home" | "create" | "detail" | "llm-settings"
  const [selectedProject, setSelectedProject] = useState(null);

  return (
    <div style={{
      minHeight: "100vh",
      background: theme.bg,
      color: theme.text,
      fontFamily: "'DM Sans', 'Segoe UI', system-ui, sans-serif",
    }}>
      <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />

      {page === "home" && (
        <HomePage
          onSelectProject={(id) => { setSelectedProject(id); setPage("detail"); }}
          onNewProject={() => setPage("create")}
          onSettings={() => setPage("llm-settings")}
        />
      )}

      {page === "create" && (
        <CreateProjectPage
          onCreated={(id) => { setSelectedProject(id); setPage("detail"); }}
          onCancel={() => setPage("home")}
        />
      )}

      {page === "detail" && selectedProject && (
        <ProjectDetailPage
          projectId={selectedProject}
          onBack={() => setPage("home")}
        />
      )}

      {page === "llm-settings" && (
        <LLMSettingsPage onBack={() => setPage("home")} />
      )}
    </div>
  );
}
