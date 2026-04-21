import React, { useState, useEffect, useRef, useCallback } from "react";

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
  async deleteProject(id, deleteFiles = false) {
    const r = await fetch(`${API_URL}/api/projects/${id}?delete_files=${deleteFiles}`, { method: "DELETE" });
    return r.json();
  },
  async controlBuild(id, action) {
    const r = await fetch(`${API_URL}/api/projects/${id}/control`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action }),
    });
    return r.json();
  },
  async resumeBuild(id) {
    const r = await fetch(`${API_URL}/api/projects/${id}/resume`, { method: "POST" });
    return r.json();
  },
  async getFileContent(projectId, filePath) {
    const r = await fetch(`${API_URL}/api/projects/${projectId}/file/${encodeURIComponent(filePath)}`);
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
  // LLM Limits & Usage
  async getLLMUsage() {
    const r = await fetch(`${API_URL}/api/llm/usage`);
    return r.json();
  },
  async getLLMLimits() {
    const r = await fetch(`${API_URL}/api/llm/limits`);
    return r.json();
  },
  async setModelLimits(modelId, data) {
    const r = await fetch(`${API_URL}/api/llm/limits/${encodeURIComponent(modelId)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    return r.json();
  },
  async getFailoverEvents(limit = 50) {
    const r = await fetch(`${API_URL}/api/llm/failover-events?limit=${limit}`);
    return r.json();
  },
  async addLLMProvider(data) {
    const r = await fetch(`${API_URL}/api/llm/providers`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    return r.json();
  },
  async deleteLLMProvider(providerId) {
    const r = await fetch(`${API_URL}/api/llm/providers/${encodeURIComponent(providerId)}`, { method: "DELETE" });
    return r.json();
  },
  // Per-provider key management
  async getProviderKeys(providerId) {
    const r = await fetch(`${API_URL}/api/llm/providers/${encodeURIComponent(providerId)}/keys`);
    return r.json();
  },
  async addProviderKey(providerId, label, apiKey) {
    const r = await fetch(`${API_URL}/api/llm/providers/${encodeURIComponent(providerId)}/keys`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label, api_key: apiKey }),
    });
    return r.json();
  },
  async deleteProviderKey(providerId, label) {
    const r = await fetch(`${API_URL}/api/llm/providers/${encodeURIComponent(providerId)}/keys/${encodeURIComponent(label)}`, { method: "DELETE" });
    return r.json();
  },
  async resetProviderKey(providerId, label) {
    const r = await fetch(`${API_URL}/api/llm/providers/${encodeURIComponent(providerId)}/keys/${encodeURIComponent(label)}/reset`, { method: "POST" });
    return r.json();
  },
  // Per-key usage & limits
  async getKeyUsage(providerId) {
    const r = await fetch(`${API_URL}/api/llm/providers/${encodeURIComponent(providerId)}/keys/usage`);
    return r.json();
  },
  async setKeyLimits(providerId, label, dailyLimit, monthlyLimit) {
    const r = await fetch(
      `${API_URL}/api/llm/providers/${encodeURIComponent(providerId)}/keys/${encodeURIComponent(label)}/limits`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ daily_limit_tokens: dailyLimit, monthly_limit_tokens: monthlyLimit }),
      }
    );
    return r.json();
  },
  async resetKeyUsage(providerId, label) {
    const r = await fetch(
      `${API_URL}/api/llm/providers/${encodeURIComponent(providerId)}/keys/${encodeURIComponent(label)}/reset-usage`,
      { method: "POST" }
    );
    return r.json();
  },
  async getLogs(id) {
    const r = await fetch(`${API_URL}/api/projects/${id}/logs`);
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
  const [editProvider, setEditProvider] = useState(null);

  // Model add/edit state
  const [showAddModel, setShowAddModel] = useState(false);
  const [newModel, setNewModel] = useState({ model_id: "", name: "", provider: "openrouter", description: "", enabled: true });
  const [editModel, setEditModel] = useState(null);

  // Routing drag state
  const [dragItem, setDragItem] = useState(null);

  // Usage & Limits state
  const [usageData, setUsageData] = useState([]);
  const [failoverEvents, setFailoverEvents] = useState([]);
  const [limitsData, setLimitsData] = useState([]);
  const [editLimits, setEditLimits] = useState({});
  const [savingLimits, setSavingLimits] = useState({});

  // Delete model confirmation
  const [deletingModel, setDeletingModel] = useState(null);

  // Custom provider add state
  const [showAddProvider, setShowAddProvider] = useState(false);
  const [newProvider, setNewProvider] = useState({
    id: "", name: "", base_url: "", api_key: "",
    model_prefix: "", compatible_with: "openai", description: "",
  });
  const [deletingProvider, setDeletingProvider] = useState(null);

  // Multi-key management state
  const [providerKeys, setProviderKeys] = useState({});        // { providerId: [keyStatus, ...] }
  const [expandedKeys, setExpandedKeys] = useState({});        // { providerId: bool }
  const [loadingKeys, setLoadingKeys] = useState({});          // { providerId: bool }
  const [addKeyForm, setAddKeyForm] = useState({});            // { providerId: {label, key, open} }
  const [deletingKey, setDeletingKey] = useState(null);        // { providerId, label }
  const [keyLimitForm, setKeyLimitForm] = useState({});        // { "pid:label": {daily, monthly, open} }
  const [savingKeyLimit, setSavingKeyLimit] = useState({});    // { "pid:label": bool }

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

  const loadUsage = useCallback(async () => {
    try {
      const [usage, events, limits] = await Promise.all([
        api.getLLMUsage(),
        api.getFailoverEvents(30),
        api.getLLMLimits(),
      ]);
      setUsageData(Array.isArray(usage) ? usage : []);
      setFailoverEvents(Array.isArray(events) ? events : []);
      setLimitsData(Array.isArray(limits) ? limits : []);
      setEditLimits(prev => {
        const next = { ...prev };
        (Array.isArray(limits) ? limits : []).forEach(m => {
          if (!next[m.id]) {
            next[m.id] = {
              rpm_limit: m.rpm_limit || 0,
              max_input_tokens: m.max_input_tokens || 0,
              max_tokens_per_minute: m.max_tokens_per_minute || 0,
              max_tokens_per_day: m.max_tokens_per_day || 0,
            };
          }
        });
        return next;
      });
    } catch {}
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  useEffect(() => {
    if (tab === "usage") {
      loadUsage();
      const interval = setInterval(loadUsage, 5000);
      return () => clearInterval(interval);
    }
  }, [tab, loadUsage]);

  // ── Provider Save ──
  const handleSaveProvider = async () => {
    if (!editProvider) return;
    try {
      const data = {};
      if (editProvider.api_key) data.api_key = editProvider.api_key;
      if (editProvider.base_url !== undefined) data.base_url = editProvider.base_url;
      if (editProvider.name !== undefined) data.name = editProvider.name;
      if (editProvider.enabled !== undefined) data.enabled = editProvider.enabled;
      if (editProvider.model_prefix !== undefined) data.model_prefix = editProvider.model_prefix;
      if (editProvider.compatible_with !== undefined) data.compatible_with = editProvider.compatible_with;
      if (editProvider.description !== undefined) data.description = editProvider.description;
      await api.updateLLMProvider(editProvider.id, data);
      setEditProvider(null);
      showToast("Provider updated successfully");
      loadData();
      // Refresh keys for this provider
      loadProviderKeys(editProvider.id);
    } catch (e) {
      showToast("Failed to update provider", "error");
    }
  };

  // ── Provider Key Helpers ──
  const loadProviderKeys = async (providerId) => {
    setLoadingKeys(prev => ({ ...prev, [providerId]: true }));
    try {
      // Use /usage endpoint so we get full stats including remaining budget
      const keys = await api.getKeyUsage(providerId);
      setProviderKeys(prev => ({ ...prev, [providerId]: Array.isArray(keys) ? keys : [] }));
    } catch {
      setProviderKeys(prev => ({ ...prev, [providerId]: [] }));
    } finally {
      setLoadingKeys(prev => ({ ...prev, [providerId]: false }));
    }
  };

  const toggleExpandKeys = async (providerId) => {
    const next = !expandedKeys[providerId];
    setExpandedKeys(prev => ({ ...prev, [providerId]: next }));
    if (next && !providerKeys[providerId]) {
      await loadProviderKeys(providerId);
    }
  };

  const handleAddKey = async (providerId) => {
    const form = addKeyForm[providerId] || {};
    if (!form.label?.trim() || !form.key?.trim()) return;
    try {
      await api.addProviderKey(providerId, form.label.trim(), form.key.trim());
      setAddKeyForm(prev => ({ ...prev, [providerId]: { label: "", key: "", open: false } }));
      showToast(`Key "${form.label}" added to ${providerId}`);
      await loadProviderKeys(providerId);
      loadData(); // refresh key_count badge
    } catch (e) {
      showToast("Failed to add key", "error");
    }
  };

  const handleDeleteKey = async () => {
    if (!deletingKey) return;
    try {
      await api.deleteProviderKey(deletingKey.providerId, deletingKey.label);
      setDeletingKey(null);
      showToast(`Key "${deletingKey.label}" removed`);
      await loadProviderKeys(deletingKey.providerId);
      loadData();
    } catch (e) {
      showToast("Failed to delete key", "error");
    }
  };

  const handleResetKey = async (providerId, label) => {
    try {
      await api.resetProviderKey(providerId, label);
      showToast(`Cooldown cleared for key "${label}"`);
      await loadProviderKeys(providerId);
    } catch (e) {
      showToast("Failed to reset key", "error");
    }
  };

  const handleSetKeyLimits = async (providerId, label) => {
    const key = `${providerId}:${label}`;
    const form = keyLimitForm[key] || {};
    setSavingKeyLimit(prev => ({ ...prev, [key]: true }));
    try {
      await api.setKeyLimits(
        providerId, label,
        parseInt(form.daily || 0, 10),
        parseInt(form.monthly || 0, 10)
      );
      showToast(`Limits saved for "${label}"`);
      setKeyLimitForm(prev => ({ ...prev, [key]: { ...prev[key], open: false } }));
      await loadProviderKeys(providerId);
    } catch {
      showToast("Failed to save limits", "error");
    } finally {
      setSavingKeyLimit(prev => ({ ...prev, [key]: false }));
    }
  };

  const handleResetKeyUsage = async (providerId, label) => {
    try {
      await api.resetKeyUsage(providerId, label);
      showToast(`Usage counters reset for "${label}"`);
      await loadProviderKeys(providerId);
    } catch {
      showToast("Failed to reset usage", "error");
    }
  };

  // ── Add Custom Provider ──
  const handleAddProvider = async () => {
    if (!newProvider.id.trim() || !newProvider.name.trim() || !newProvider.base_url.trim()) return;
    try {
      await api.addLLMProvider(newProvider);
      setShowAddProvider(false);
      setNewProvider({ id: "", name: "", base_url: "", api_key: "", model_prefix: "", compatible_with: "openai", description: "" });
      showToast(`Provider "${newProvider.name}" added successfully`);
      loadData();
    } catch (e) {
      showToast("Failed to add provider", "error");
    }
  };

  // ── Delete Custom Provider ──
  const handleDeleteProvider = async (providerId) => {
    try {
      await api.deleteLLMProvider(providerId);
      setDeletingProvider(null);
      showToast("Provider deleted");
      loadData();
    } catch (e) {
      showToast(e.message || "Failed to delete provider", "error");
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
    try {
      await api.deleteLLMModel(modelId);
      setDeletingModel(null);
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
          { id: "usage", label: "📊 Usage & Limits" },
        ].map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} style={tabStyle(t.id)}>{t.label}</button>
        ))}
      </div>

      {/* ── PROVIDERS TAB ── */}
      {tab === "providers" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <SectionHeader
            title="API Providers"
            subtitle="Set your API keys and endpoint URLs for each provider. All keys and limits are persisted — they survive server restarts."
            action={
              <Button id="add-provider-btn" onClick={() => setShowAddProvider(true)} style={{ padding: "7px 16px", fontSize: 12 }}>
                + Add Custom Provider
              </Button>
            }
          />

          {/* ── Add Custom Provider Form ── */}
          {showAddProvider && (
            <Card style={{ border: `1px solid ${theme.accent}44`, background: `${theme.accentGlow}` }}>
              <div style={{ fontSize: 14, fontWeight: 700, color: theme.text, marginBottom: 18 }}>🔌 Add Custom Provider</div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                <div>
                  <Label>Provider ID <span style={{ color: theme.textDim, fontWeight: 400 }}>(slug, no spaces)</span></Label>
                  <Input value={newProvider.id} onChange={e => setNewProvider(p => ({ ...p, id: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "-") }))} placeholder="ollama, azure-east, mistral-local..." />
                </div>
                <div>
                  <Label>Display Name</Label>
                  <Input value={newProvider.name} onChange={e => setNewProvider(p => ({ ...p, name: e.target.value }))} placeholder="Ollama (Local), Azure East..." />
                </div>
                <div style={{ gridColumn: "1/-1" }}>
                  <Label>Base URL / Endpoint <span style={{ color: theme.error, fontSize: 11 }}>*required</span></Label>
                  <Input value={newProvider.base_url} onChange={e => setNewProvider(p => ({ ...p, base_url: e.target.value }))} placeholder="http://localhost:11434/v1  or  https://your-azure.openai.azure.com/..." />
                </div>
                <div>
                  <Label>API Key <span style={{ color: theme.textDim, fontWeight: 400 }}>(leave blank for local/no-auth)</span></Label>
                  <Input type="password" value={newProvider.api_key} onChange={e => setNewProvider(p => ({ ...p, api_key: e.target.value }))} placeholder="sk-... or bearer token" />
                </div>
                <div>
                  <Label>LiteLLM Model Prefix</Label>
                  <Input value={newProvider.model_prefix} onChange={e => setNewProvider(p => ({ ...p, model_prefix: e.target.value }))} placeholder="ollama, openai, mistral..." />
                  <div style={{ fontSize: 10, color: theme.textDim, marginTop: 4 }}>Prepended to model names when calling LiteLLM, e.g. "ollama/llama3"</div>
                </div>
                <div>
                  <Label>API Compatibility</Label>
                  <select value={newProvider.compatible_with} onChange={e => setNewProvider(p => ({ ...p, compatible_with: e.target.value }))}
                    style={{ width: "100%", padding: "10px 14px", background: theme.bgInput, border: `1px solid ${theme.border}`, borderRadius: 8, color: theme.text, fontSize: 14, outline: "none" }}>
                    <option value="openai">OpenAI-compatible (Ollama, vLLM, LM Studio, Azure...)</option>
                    <option value="anthropic">Anthropic-compatible</option>
                    <option value="openrouter">OpenRouter-compatible</option>
                    <option value="custom">Custom / Other</option>
                  </select>
                </div>
                <div>
                  <Label>Description <span style={{ color: theme.textDim, fontWeight: 400 }}>(optional)</span></Label>
                  <Input value={newProvider.description} onChange={e => setNewProvider(p => ({ ...p, description: e.target.value }))} placeholder="Local Ollama instance, GPU server..." />
                </div>
              </div>
              {/* Quick-fill presets */}
              <div style={{ marginTop: 14, display: "flex", gap: 8, flexWrap: "wrap" }}>
                <span style={{ fontSize: 11, color: theme.textDim, alignSelf: "center" }}>Quick presets:</span>
                {[
                  { label: "🦙 Ollama", id: "ollama", name: "Ollama (Local)", base_url: "http://localhost:11434/v1", model_prefix: "ollama", compatible_with: "openai", api_key: "" },
                  { label: "🌐 LM Studio", id: "lmstudio", name: "LM Studio", base_url: "http://localhost:1234/v1", model_prefix: "openai", compatible_with: "openai", api_key: "lm-studio" },
                  { label: "⚡ Azure OpenAI", id: "azure", name: "Azure OpenAI", base_url: "https://YOUR_RESOURCE.openai.azure.com/", model_prefix: "azure", compatible_with: "openai", api_key: "" },
                  { label: "🚀 vLLM", id: "vllm", name: "vLLM Server", base_url: "http://localhost:8000/v1", model_prefix: "openai", compatible_with: "openai", api_key: "" },
                  { label: "🤖 Together AI", id: "together", name: "Together AI", base_url: "https://api.together.xyz/v1", model_prefix: "together_ai", compatible_with: "openai", api_key: "" },
                  { label: "🔥 Groq", id: "groq", name: "Groq", base_url: "https://api.groq.com/openai/v1", model_prefix: "groq", compatible_with: "openai", api_key: "" },
                ].map(preset => (
                  <button key={preset.id} onClick={() => setNewProvider(p => ({ ...p, ...preset }))}
                    style={{ padding: "4px 10px", borderRadius: 6, fontSize: 11, fontWeight: 600, background: theme.bgHover, border: `1px solid ${theme.border}`, color: theme.textMuted, cursor: "pointer" }}>
                    {preset.label}
                  </button>
                ))}
              </div>
              <div style={{ display: "flex", gap: 10, marginTop: 18 }}>
                <Button variant="ghost" onClick={() => { setShowAddProvider(false); setNewProvider({ id: "", name: "", base_url: "", api_key: "", model_prefix: "", compatible_with: "openai", description: "" }); }}>Cancel</Button>
                <Button onClick={handleAddProvider} disabled={!newProvider.id.trim() || !newProvider.name.trim() || !newProvider.base_url.trim()}>Add Provider</Button>
              </div>
            </Card>
          )}

          {/* Provider List */}
          {providers.map(prov => {
            const keys = providerKeys[prov.id] || [];
            const isExpanded = expandedKeys[prov.id];
            const keyForm = addKeyForm[prov.id] || { label: "", key: "", open: false };
            const hasKeys = (prov.key_count || 0) > 0;
            const activeKeys = keys.filter(k => k.is_available);
            const limitedKeys = keys.filter(k => !k.is_available);
            return (
            <Card key={prov.id} style={{ padding: 0, overflow: "hidden", border: prov.custom ? `1px solid ${theme.accent}33` : undefined }}>
              {/* ── Header row ── */}
              <div style={{ padding: "16px 20px", display: "flex", alignItems: "center", gap: 14 }}>
                {/* Icon */}
                <div style={{
                  width: 44, height: 44, borderRadius: 10, flexShrink: 0,
                  background: `${PROVIDER_COLORS[prov.id] || theme.accent}22`,
                  border: `1px solid ${PROVIDER_COLORS[prov.id] || theme.accent}44`,
                  display: "flex", alignItems: "center", justifyContent: "center", fontSize: 22,
                }}>
                  {PROVIDER_ICONS[prov.id] || "🔌"}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <div style={{ fontSize: 15, fontWeight: 700, color: theme.text }}>{prov.name}</div>
                    {prov.custom && <span style={{ fontSize: 9, padding: "2px 7px", borderRadius: 4, background: `${theme.accent}22`, color: theme.accent, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.5px" }}>Custom</span>}
                    {prov.compatible_with && prov.custom && <span style={{ fontSize: 9, padding: "2px 7px", borderRadius: 4, background: theme.bgHover, color: theme.textDim, fontWeight: 600 }}>{prov.compatible_with}</span>}
                    {/* Key count badge */}
                    <span style={{
                      fontSize: 10, padding: "2px 8px", borderRadius: 12, fontWeight: 700,
                      background: hasKeys ? theme.successBg : theme.errorBg,
                      color: hasKeys ? theme.success : theme.error,
                      border: `1px solid ${hasKeys ? theme.success : theme.error}33`,
                    }}>
                      🔑 {prov.key_count || 0} {prov.key_count === 1 ? "key" : "keys"}
                    </span>
                    {limitedKeys.length > 0 && (
                      <span style={{ fontSize: 10, padding: "2px 8px", borderRadius: 12, fontWeight: 700, background: theme.errorBg, color: theme.error, border: `1px solid ${theme.error}33` }}>
                        ⚠ {limitedKeys.length} rate-limited
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: 12, color: theme.textMuted, marginTop: 2, fontFamily: "monospace", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {prov.base_url}
                  </div>
                  {prov.model_prefix && <div style={{ fontSize: 10, color: theme.textDim, marginTop: 1 }}>prefix: <span style={{ fontFamily: "monospace", color: theme.accent }}>{prov.model_prefix}/</span></div>}
                  {prov.description && <div style={{ fontSize: 11, color: theme.textDim, marginTop: 2 }}>{prov.description}</div>}
                </div>
                {/* Action buttons */}
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0, flexWrap: "wrap" }}>
                  <div style={{ padding: "4px 12px", borderRadius: 20, fontSize: 11, fontWeight: 600, background: prov.enabled ? theme.accentGlow : `${theme.textDim}22`, color: prov.enabled ? theme.accent : theme.textDim, border: `1px solid ${prov.enabled ? theme.accent : theme.textDim}33` }}>
                    {prov.enabled ? "Enabled" : "Disabled"}
                  </div>
                  <Button
                    id={`keys-toggle-${prov.id}`}
                    variant="ghost"
                    onClick={() => toggleExpandKeys(prov.id)}
                    style={{ padding: "6px 14px", fontSize: 12, color: isExpanded ? theme.accent : theme.textMuted }}
                  >
                    {isExpanded ? "▲ Keys" : "▼ Keys"}
                  </Button>
                  <Button variant="ghost" onClick={() => setEditProvider({ ...prov, api_key: "" })} style={{ padding: "6px 14px", fontSize: 12 }}>Edit</Button>
                  {prov.custom && (
                    <Button variant="danger" onClick={() => setDeletingProvider(prov)} style={{ padding: "6px 12px", fontSize: 12 }}>🗑</Button>
                  )}
                </div>
              </div>

              {/* ── Expanded Keys Section ── */}
              {isExpanded && (
                <div style={{ borderTop: `1px solid ${theme.border}`, background: theme.bg, padding: "16px 20px" }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
                    <div style={{ fontSize: 12, fontWeight: 700, color: theme.textMuted, textTransform: "uppercase", letterSpacing: "0.5px" }}>API Key Pool</div>
                    <Button
                      id={`add-key-${prov.id}`}
                      style={{ padding: "5px 12px", fontSize: 11 }}
                      onClick={() => setAddKeyForm(prev => ({ ...prev, [prov.id]: { ...keyForm, open: !keyForm.open } }))}
                    >
                      {keyForm.open ? "✕ Cancel" : "+ Add Key"}
                    </Button>
                  </div>

                  {/* Add Key inline form */}
                  {keyForm.open && (
                    <div style={{ background: theme.bgCard, border: `1px solid ${theme.accent}44`, borderRadius: 10, padding: 14, marginBottom: 12, display: "grid", gridTemplateColumns: "1fr 2fr auto", gap: 10, alignItems: "flex-end" }}>
                      <div>
                        <Label>Label</Label>
                        <Input
                          id={`key-label-${prov.id}`}
                          value={keyForm.label || ""}
                          onChange={e => setAddKeyForm(prev => ({ ...prev, [prov.id]: { ...keyForm, label: e.target.value } }))}
                          placeholder="key-2, backup, account-b"
                        />
                      </div>
                      <div>
                        <Label>API Key</Label>
                        <Input
                          id={`key-value-${prov.id}`}
                          type="password"
                          value={keyForm.key || ""}
                          onChange={e => setAddKeyForm(prev => ({ ...prev, [prov.id]: { ...keyForm, key: e.target.value } }))}
                          placeholder="sk-or-v1-..."
                        />
                      </div>
                      <Button
                        id={`save-key-${prov.id}`}
                        onClick={() => handleAddKey(prov.id)}
                        disabled={!keyForm.label?.trim() || !keyForm.key?.trim()}
                        style={{ padding: "10px 18px", fontSize: 12, whiteSpace: "nowrap" }}
                      >
                        Save Key
                      </Button>
                    </div>
                  )}

                  {/* Keys list */}
                  {loadingKeys[prov.id] ? (
                    <div style={{ color: theme.textMuted, fontSize: 12, padding: "8px 0" }}>Loading keys…</div>
                  ) : keys.length === 0 ? (
                    <div style={{ color: theme.textDim, fontSize: 12, padding: "8px 0", textAlign: "center" }}>No keys configured — click "+ Add Key" to add one.</div>
                  ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                      {keys.map((k) => {
                        const isRateLimited = !k.is_available;
                        const isCurrent = k.is_current;
                        const ttl = isRateLimited ? k.status?.split(":")[1] : null;
                        const limitKey = `${prov.id}:${k.label}`;
                        const lf = keyLimitForm[limitKey] || {};
                        const hasDailyLimit = (k.daily_limit_tokens || 0) > 0;
                        const hasMonthlyLimit = (k.monthly_limit_tokens || 0) > 0;
                        const dailyPct = hasDailyLimit ? Math.min(100, ((k.tokens_used_today || 0) / k.daily_limit_tokens) * 100) : 0;
                        const monthlyPct = hasMonthlyLimit ? Math.min(100, ((k.tokens_used_this_month || 0) / k.monthly_limit_tokens) * 100) : 0;
                        const fmt = (n) => n == null ? "∞" : n >= 1_000_000 ? `${(n/1_000_000).toFixed(1)}M` : n >= 1_000 ? `${(n/1_000).toFixed(0)}K` : String(n);
                        return (
                          <div key={k.label} style={{
                            background: theme.bgCard, borderRadius: 10,
                            border: `1px solid ${isRateLimited ? theme.error + "44" : isCurrent ? theme.accent + "44" : theme.border}`,
                            overflow: "hidden",
                          }}>
                            {/* ── Row 1: identity + status + actions ── */}
                            <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px" }}>
                              <div style={{ width: 8, height: 8, borderRadius: "50%", flexShrink: 0, background: isRateLimited ? theme.error : isCurrent ? theme.success : theme.textDim }} />
                              <div style={{ fontSize: 12, fontWeight: 700, color: theme.text, minWidth: 80 }}>{k.label}</div>
                              <div style={{ fontFamily: "monospace", fontSize: 11, color: theme.textDim, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{k.masked_key}</div>
                              {/* Status badge */}
                              <span style={{
                                fontSize: 10, padding: "2px 8px", borderRadius: 12, fontWeight: 700, flexShrink: 0,
                                background: isRateLimited ? theme.errorBg : isCurrent ? theme.successBg : `${theme.textDim}22`,
                                color: isRateLimited ? theme.error : isCurrent ? theme.success : theme.textDim,
                              }}>
                                {isRateLimited ? `⏸ Rate Limited ${ttl ? `(${ttl})` : ""}` : isCurrent ? "● Active" : "◌ Standby"}
                              </span>
                              {/* Actions */}
                              {isRateLimited && (
                                <button id={`reset-key-${prov.id}-${k.label}`}
                                  onClick={() => handleResetKey(prov.id, k.label)}
                                  style={{ padding: "3px 10px", borderRadius: 6, fontSize: 10, fontWeight: 600, background: theme.warningBg, border: `1px solid ${theme.warning}44`, color: theme.warning, cursor: "pointer" }}>
                                  ↺ Reset
                                </button>
                              )}
                              <button
                                onClick={() => setKeyLimitForm(prev => ({ ...prev, [limitKey]: { daily: k.daily_limit_tokens||0, monthly: k.monthly_limit_tokens||0, open: !lf.open } }))}
                                style={{ padding: "3px 10px", borderRadius: 6, fontSize: 10, fontWeight: 600, background: theme.infoBg, border: `1px solid ${theme.info}44`, color: theme.info, cursor: "pointer" }}>
                                ⚙ Limits
                              </button>
                              <button id={`del-key-${prov.id}-${k.label}`}
                                onClick={() => setDeletingKey({ providerId: prov.id, label: k.label })}
                                style={{ padding: "3px 8px", borderRadius: 6, fontSize: 10, fontWeight: 600, background: theme.errorBg, border: `1px solid ${theme.error}33`, color: theme.error, cursor: "pointer" }}>
                                ✕
                              </button>
                            </div>

                            {/* ── Row 2: usage stats ── */}
                            <div style={{ padding: "6px 14px 10px", display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8, borderTop: `1px solid ${theme.border}` }}>
                              {[
                                { label: "Calls", value: (k.total_calls||0).toLocaleString(), icon: "📞" },
                                { label: "Tokens In", value: fmt(k.total_tokens_in||0), icon: "→" },
                                { label: "Tokens Out", value: fmt(k.total_tokens_out||0), icon: "←" },
                                { label: "Errors", value: (k.total_errors||0).toLocaleString(), icon: "⚠", color: (k.total_errors||0) > 0 ? theme.error : theme.textDim },
                              ].map(stat => (
                                <div key={stat.label} style={{ textAlign: "center" }}>
                                  <div style={{ fontSize: 15, fontWeight: 700, color: stat.color || theme.text }}>{stat.icon} {stat.value}</div>
                                  <div style={{ fontSize: 10, color: theme.textDim, marginTop: 1 }}>{stat.label}</div>
                                </div>
                              ))}
                            </div>

                            {/* ── Row 3: budget bars ── */}
                            {(hasDailyLimit || hasMonthlyLimit) && (
                              <div style={{ padding: "6px 14px 10px", borderTop: `1px solid ${theme.border}`, display: "flex", flexDirection: "column", gap: 6 }}>
                                {hasDailyLimit && (
                                  <div>
                                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: theme.textMuted, marginBottom: 3 }}>
                                      <span>Daily budget</span>
                                      <span style={{ color: dailyPct > 85 ? theme.error : dailyPct > 60 ? theme.warning : theme.success }}>
                                        {fmt(k.tokens_used_today||0)} / {fmt(k.daily_limit_tokens)} used · {fmt(k.tokens_remaining_today)} left
                                      </span>
                                    </div>
                                    <div style={{ height: 5, background: theme.border, borderRadius: 4 }}>
                                      <div style={{ height: "100%", width: `${dailyPct}%`, borderRadius: 4, transition: "width 0.4s",
                                        background: dailyPct > 85 ? theme.error : dailyPct > 60 ? theme.warning : theme.success }} />
                                    </div>
                                  </div>
                                )}
                                {hasMonthlyLimit && (
                                  <div>
                                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: theme.textMuted, marginBottom: 3 }}>
                                      <span>Monthly budget</span>
                                      <span style={{ color: monthlyPct > 85 ? theme.error : monthlyPct > 60 ? theme.warning : theme.success }}>
                                        {fmt(k.tokens_used_this_month||0)} / {fmt(k.monthly_limit_tokens)} used · {fmt(k.tokens_remaining_this_month)} left
                                      </span>
                                    </div>
                                    <div style={{ height: 5, background: theme.border, borderRadius: 4 }}>
                                      <div style={{ height: "100%", width: `${monthlyPct}%`, borderRadius: 4, transition: "width 0.4s",
                                        background: monthlyPct > 85 ? theme.error : monthlyPct > 60 ? theme.warning : theme.success }} />
                                    </div>
                                  </div>
                                )}
                                <button onClick={() => handleResetKeyUsage(prov.id, k.label)}
                                  style={{ alignSelf: "flex-end", marginTop: 2, padding: "2px 10px", borderRadius: 6, fontSize: 10, fontWeight: 600, background: "transparent", border: `1px solid ${theme.border}`, color: theme.textDim, cursor: "pointer" }}>
                                  Reset usage counters
                                </button>
                              </div>
                            )}

                            {/* ── Row 4: Set Limits inline form ── */}
                            {lf.open && (
                              <div style={{ padding: "10px 14px", borderTop: `1px solid ${theme.accent}33`, background: theme.accentGlow, display: "grid", gridTemplateColumns: "1fr 1fr auto auto", gap: 10, alignItems: "flex-end" }}>
                                <div>
                                  <div style={{ fontSize: 10, color: theme.textMuted, fontWeight: 600, marginBottom: 4, textTransform: "uppercase" }}>Daily Token Limit</div>
                                  <input type="number" min="0"
                                    value={lf.daily ?? k.daily_limit_tokens ?? 0}
                                    onChange={e => setKeyLimitForm(prev => ({ ...prev, [limitKey]: { ...lf, daily: e.target.value } }))}
                                    placeholder="0 = unlimited"
                                    style={{ width: "100%", padding: "7px 10px", background: theme.bgInput, border: `1px solid ${theme.border}`, borderRadius: 7, color: theme.text, fontSize: 13, outline: "none", boxSizing: "border-box" }}
                                  />
                                </div>
                                <div>
                                  <div style={{ fontSize: 10, color: theme.textMuted, fontWeight: 600, marginBottom: 4, textTransform: "uppercase" }}>Monthly Token Limit</div>
                                  <input type="number" min="0"
                                    value={lf.monthly ?? k.monthly_limit_tokens ?? 0}
                                    onChange={e => setKeyLimitForm(prev => ({ ...prev, [limitKey]: { ...lf, monthly: e.target.value } }))}
                                    placeholder="0 = unlimited"
                                    style={{ width: "100%", padding: "7px 10px", background: theme.bgInput, border: `1px solid ${theme.border}`, borderRadius: 7, color: theme.text, fontSize: 13, outline: "none", boxSizing: "border-box" }}
                                  />
                                </div>
                                <button onClick={() => handleSetKeyLimits(prov.id, k.label)}
                                  disabled={savingKeyLimit[limitKey]}
                                  style={{ padding: "9px 16px", borderRadius: 7, fontSize: 12, fontWeight: 700, background: theme.accent, color: "#fff", border: "none", cursor: "pointer" }}>
                                  {savingKeyLimit[limitKey] ? "…" : "Save"}
                                </button>
                                <button onClick={() => setKeyLimitForm(prev => ({ ...prev, [limitKey]: { ...lf, open: false } }))}
                                  style={{ padding: "9px 12px", borderRadius: 7, fontSize: 12, background: "transparent", border: `1px solid ${theme.border}`, color: theme.textMuted, cursor: "pointer" }}>
                                  ✕
                                </button>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </Card>
            );
          })}

          {/* Delete Key Confirmation */}
          {deletingKey && (
            <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.75)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
              <div style={{ background: theme.bgCard, border: `1px solid ${theme.error}44`, borderRadius: 16, padding: 32, width: "100%", maxWidth: 400, textAlign: "center" }}>
                <div style={{ fontSize: 30, marginBottom: 12 }}>🗑️</div>
                <div style={{ fontSize: 16, fontWeight: 700, color: theme.text, marginBottom: 8 }}>Remove API Key?</div>
                <div style={{ fontSize: 13, color: theme.textMuted, marginBottom: 24 }}>
                  Remove key <strong style={{ color: theme.text }}>«{deletingKey.label}»</strong> from <strong style={{ color: theme.text }}>{deletingKey.providerId}</strong>?<br/>
                  The gateway will stop using this key immediately.
                </div>
                <div style={{ display: "flex", gap: 10 }}>
                  <Button variant="ghost" onClick={() => setDeletingKey(null)} style={{ flex: 1 }}>Cancel</Button>
                  <Button variant="danger" onClick={handleDeleteKey} style={{ flex: 1 }}>Remove Key</Button>
                </div>
              </div>
            </div>
          )}

          {/* Edit Provider Modal */}
          {editProvider && (
            <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
              <div style={{ background: theme.bgCard, border: `1px solid ${theme.border}`, borderRadius: 16, padding: 32, width: "100%", maxWidth: 540 }}>
                <div style={{ fontSize: 18, fontWeight: 700, color: theme.text, marginBottom: 24 }}>
                  {PROVIDER_ICONS[editProvider.id] || "🔌"} Edit {editProvider.name}
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                  {editProvider.custom && (
                    <div>
                      <Label>Display Name</Label>
                      <Input value={editProvider.name || ""} onChange={e => setEditProvider(p => ({ ...p, name: e.target.value }))} placeholder="Provider name" />
                    </div>
                  )}
                  <div>
                    <Label>API Key {editProvider.has_key && <span style={{ color: theme.textDim, fontWeight: 400 }}>(leave blank to keep existing)</span>}</Label>
                    <Input type="password" value={editProvider.api_key} onChange={e => setEditProvider(p => ({ ...p, api_key: e.target.value }))} placeholder={editProvider.has_key ? "••••••••••••••••••••" : "sk-or-v1-..."} />
                  </div>
                  <div>
                    <Label>Base URL / Endpoint</Label>
                    <Input value={editProvider.base_url || ""} onChange={e => setEditProvider(p => ({ ...p, base_url: e.target.value }))} placeholder="https://openrouter.ai/api/v1/" />
                  </div>
                  {editProvider.custom && (
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                      <div>
                        <Label>Model Prefix</Label>
                        <Input value={editProvider.model_prefix || ""} onChange={e => setEditProvider(p => ({ ...p, model_prefix: e.target.value }))} placeholder="ollama, openai..." />
                      </div>
                      <div>
                        <Label>API Compatibility</Label>
                        <select value={editProvider.compatible_with || "openai"} onChange={e => setEditProvider(p => ({ ...p, compatible_with: e.target.value }))}
                          style={{ width: "100%", padding: "10px 14px", background: theme.bgInput, border: `1px solid ${theme.border}`, borderRadius: 8, color: theme.text, fontSize: 14, outline: "none" }}>
                          <option value="openai">OpenAI-compatible</option>
                          <option value="anthropic">Anthropic-compatible</option>
                          <option value="openrouter">OpenRouter-compatible</option>
                          <option value="custom">Custom / Other</option>
                        </select>
                      </div>
                      <div style={{ gridColumn: "1/-1" }}>
                        <Label>Description</Label>
                        <Input value={editProvider.description || ""} onChange={e => setEditProvider(p => ({ ...p, description: e.target.value }))} placeholder="Brief description..." />
                      </div>
                    </div>
                  )}
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", color: theme.text, fontSize: 14 }}>
                      <input type="checkbox" checked={editProvider.enabled} onChange={e => setEditProvider(p => ({ ...p, enabled: e.target.checked }))} style={{ width: 16, height: 16, accentColor: theme.accent }} />
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

          {/* Delete Confirmation Dialog */}
          {deletingProvider && (
            <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.75)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
              <div style={{ background: theme.bgCard, border: `1px solid ${theme.error}44`, borderRadius: 16, padding: 32, width: "100%", maxWidth: 420, textAlign: "center" }}>
                <div style={{ fontSize: 36, marginBottom: 12 }}>🗑️</div>
                <div style={{ fontSize: 17, fontWeight: 700, color: theme.text, marginBottom: 8 }}>Delete Provider?</div>
                <div style={{ fontSize: 13, color: theme.textMuted, marginBottom: 24 }}>
                  Are you sure you want to delete <strong style={{ color: theme.text }}>{deletingProvider.name}</strong>?<br />
                  Any models using this provider will need to be reconfigured.
                </div>
                <div style={{ display: "flex", gap: 10 }}>
                  <Button variant="ghost" onClick={() => setDeletingProvider(null)} style={{ flex: 1 }}>Cancel</Button>
                  <Button variant="danger" onClick={() => handleDeleteProvider(deletingProvider.id)} style={{ flex: 1 }}>Delete</Button>
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
                    {providers.map(prov => (
                      <option key={prov.id} value={prov.id}>{prov.name}{prov.custom ? " (custom)" : ""}</option>
                    ))}
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
                      {providers.map(prov => (
                        <option key={prov.id} value={prov.id}>{prov.name}{prov.custom ? " (custom)" : ""}</option>
                      ))}
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

          {/* Model List — grouped by all providers (built-in + custom) */}
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {/* Get all unique providers from the models list */}
            {Array.from(new Set(models.map(m => m.provider))).map(provId => {
              const provModels = models.filter(m => m.provider === provId);
              if (provModels.length === 0) return null;
              const provInfo = providers.find(p => p.id === provId);
              return (
                <div key={provId}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8, marginTop: 16 }}>
                    <span style={{ fontSize: 16 }}>{PROVIDER_ICONS[provId] || "🔌"}</span>
                    <span style={{ fontSize: 12, fontWeight: 700, color: PROVIDER_COLORS[provId] || theme.accent, textTransform: "uppercase", letterSpacing: "0.5px" }}>
                      {provInfo ? provInfo.name : provId}
                    </span>
                    {provInfo?.custom && <span style={{ fontSize: 9, padding: "1px 6px", borderRadius: 4, background: `${theme.accent}22`, color: theme.accent, fontWeight: 700 }}>CUSTOM</span>}
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
                          <Button
                            variant="danger"
                            onClick={() => setDeletingModel(model)}
                            style={{ padding: "4px 10px", fontSize: 11, opacity: model.custom ? 1 : 0.65 }}
                          >
                            🗑
                          </Button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>

          {/* Delete Model Confirmation Modal */}
          {deletingModel && (
            <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.75)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
              <div style={{ background: theme.bgCard, border: `1px solid ${theme.error}44`, borderRadius: 16, padding: 32, width: "100%", maxWidth: 420, textAlign: "center" }}>
                <div style={{ fontSize: 36, marginBottom: 12 }}>🗑️</div>
                <div style={{ fontSize: 17, fontWeight: 700, color: theme.text, marginBottom: 8 }}>Delete Model?</div>
                <div style={{ fontSize: 13, color: theme.textMuted, marginBottom: 8 }}>
                  <strong style={{ color: theme.text }}>{deletingModel.name}</strong>
                </div>
                <div style={{ fontSize: 11, color: theme.textDim, fontFamily: "monospace", marginBottom: 20, padding: "6px 12px", background: theme.bgInput, borderRadius: 6, display: "inline-block" }}>
                  {deletingModel.id}
                </div>
                {!deletingModel.custom && (
                  <div style={{ padding: "8px 14px", background: theme.warningBg, border: `1px solid ${theme.warning}44`, borderRadius: 8, marginBottom: 20, fontSize: 12, color: theme.warning }}>
                    ⚠️ This is a built-in model. Deleting it will also remove it from all routing tiers.
                  </div>
                )}
                <div style={{ display: "flex", gap: 10 }}>
                  <Button variant="ghost" onClick={() => setDeletingModel(null)} style={{ flex: 1 }}>Cancel</Button>
                  <Button variant="danger" onClick={() => handleDeleteModel(deletingModel.id)} style={{ flex: 1 }}>Delete</Button>
                </div>
              </div>
            </div>
          )}
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

      {/* ── USAGE & LIMITS TAB ── */}
      {tab === "usage" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>

          {/* Per-Model Limits Editor */}
          <div>
            <SectionHeader
              title="Per-Model Rate Limits"
              subtitle="Set RPM, per-request token cap, tokens-per-minute & daily budgets. 0 = unlimited. Auto-switches to fallback model when any limit is hit."
            />
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {limitsData.length === 0 && (
                <div style={{ padding: 32, textAlign: "center", color: theme.textDim, fontSize: 13 }}>
                  Loading... (make sure the API is running)
                </div>
              )}
              {limitsData.map(model => {
                const lim = editLimits[model.id] || { rpm_limit: 0, max_input_tokens: 0, max_tokens_per_minute: 0, max_tokens_per_day: 0 };
                const isSaving = savingLimits[model.id];
                const liveStats = model.live_stats || {};
                const usage = model.usage || {};
                const perMin = usage.per_minute || {};
                const perDay = usage.per_day || {};
                const perWeek = usage.per_week || {};
                const rpmUsedPct = lim.rpm_limit > 0 ? Math.min(100, (liveStats.rpm_current || 0) / lim.rpm_limit * 100) : 0;
                const rpmColor = rpmUsedPct > 85 ? theme.error : rpmUsedPct > 60 ? theme.warning : theme.success;

                const handleLimitChange = (field, val) => {
                  setEditLimits(prev => ({ ...prev, [model.id]: { ...lim, [field]: Math.max(0, parseInt(val) || 0) } }));
                };

                const handleSaveLimits = async () => {
                  setSavingLimits(prev => ({ ...prev, [model.id]: true }));
                  try {
                    await api.setModelLimits(model.id, lim);
                    showToast(`Limits saved for ${model.name || model.id}`);
                    loadUsage();
                  } catch { showToast("Failed to save limits", "error"); }
                  finally { setSavingLimits(prev => ({ ...prev, [model.id]: false })); }
                };

                return (
                  <Card key={model.id} style={{ padding: 0, overflow: "hidden" }}>
                    <div style={{ padding: "12px 16px", display: "flex", alignItems: "center", gap: 12, borderBottom: `1px solid ${theme.border}` }}>
                      <div style={{ width: 8, height: 8, borderRadius: "50%", background: model.enabled ? theme.success : theme.textDim, flexShrink: 0 }} />
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: 13, fontWeight: 700, color: theme.text }}>{model.name || model.id}</div>
                        <div style={{ fontSize: 10, color: theme.textDim, fontFamily: "monospace" }}>{model.id}</div>
                      </div>
                      {lim.rpm_limit > 0 && (
                        <div style={{ textAlign: "right" }}>
                          <div style={{ fontSize: 10, color: theme.textMuted }}>Live RPM</div>
                          <div style={{ fontSize: 16, fontWeight: 800, color: rpmColor }}>{liveStats.rpm_current || 0}/{lim.rpm_limit}</div>
                          <div style={{ width: 72, height: 4, background: theme.border, borderRadius: 2, marginTop: 2 }}>
                            <div style={{ width: `${rpmUsedPct}%`, height: "100%", borderRadius: 2, background: rpmColor, transition: "width 0.5s" }} />
                          </div>
                        </div>
                      )}
                    </div>
                    <div style={{ padding: 16 }}>
                      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 14 }}>
                        {[
                          { field: "rpm_limit", label: "Max RPM", hint: "requests / min" },
                          { field: "max_input_tokens", label: "Max Input Tokens", hint: "per request" },
                          { field: "max_tokens_per_minute", label: "Token Budget / Min", hint: "in + out tokens" },
                          { field: "max_tokens_per_day", label: "Daily Token Budget", hint: "in + out tokens" },
                        ].map(({ field, label, hint }) => (
                          <div key={field}>
                            <div style={{ fontSize: 10, fontWeight: 700, color: theme.textMuted, textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: 3 }}>{label}</div>
                            <div style={{ fontSize: 9, color: theme.textDim, marginBottom: 5 }}>{hint} — 0 = unlimited</div>
                            <input
                              type="number" min="0"
                              value={lim[field] || 0}
                              onChange={e => handleLimitChange(field, e.target.value)}
                              style={{ width: "100%", padding: "8px 10px", background: theme.bgInput, border: `1px solid ${theme.border}`, borderRadius: 6, color: theme.text, fontSize: 14, fontWeight: 600, outline: "none", boxSizing: "border-box" }}
                              onFocus={e => e.target.style.borderColor = theme.accent}
                              onBlur={e => e.target.style.borderColor = theme.border}
                            />
                          </div>
                        ))}
                      </div>
                      {((perMin.requests || 0) + (perDay.requests || 0)) > 0 && (
                        <div style={{ display: "flex", gap: 12, marginBottom: 14, padding: "10px 12px", background: theme.bgInput, borderRadius: 8 }}>
                          {[
                            { label: "Requests (min)", val: perMin.requests || 0, max: lim.rpm_limit },
                            { label: "Tokens (min)", val: (perMin.input_tokens || 0) + (perMin.output_tokens || 0), max: lim.max_tokens_per_minute },
                            { label: "Tokens (day)", val: (perDay.input_tokens || 0) + (perDay.output_tokens || 0), max: lim.max_tokens_per_day },
                            { label: "Tokens (week)", val: (perWeek.input_tokens || 0) + (perWeek.output_tokens || 0), max: 0 },
                          ].map(({ label, val, max }) => {
                            const pct = max > 0 ? Math.min(100, val / max * 100) : 0;
                            const barColor = pct > 90 ? theme.error : pct > 70 ? theme.warning : theme.accent;
                            return (
                              <div key={label} style={{ flex: 1 }}>
                                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
                                  <span style={{ fontSize: 10, color: theme.textDim }}>{label}</span>
                                  <span style={{ fontSize: 10, fontWeight: 600, color: max > 0 && pct > 80 ? theme.error : theme.textMuted }}>
                                    {val > 999 ? `${(val / 1000).toFixed(1)}K` : val}
                                    {max > 0 ? ` / ${max > 999 ? `${(max / 1000).toFixed(0)}K` : max}` : ""}
                                  </span>
                                </div>
                                <div style={{ height: 4, background: theme.border, borderRadius: 2 }}>
                                  {max > 0 && <div style={{ width: `${pct}%`, height: "100%", background: barColor, borderRadius: 2, transition: "width 0.4s" }} />}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      )}
                      <div style={{ display: "flex", justifyContent: "flex-end" }}>
                        <Button onClick={handleSaveLimits} disabled={isSaving} style={{ padding: "7px 18px", fontSize: 12 }}>
                          {isSaving ? "Saving..." : "💾 Save Limits"}
                        </Button>
                      </div>
                    </div>
                  </Card>
                );
              })}
            </div>
          </div>

          {/* Failover Event Log */}
          <div>
            <SectionHeader
              title="⚡ Failover Events"
              subtitle="Auto model-switches triggered by rate limits or failures. Full context window is forwarded to replacement model."
              action={<Button variant="ghost" onClick={loadUsage} style={{ padding: "5px 12px", fontSize: 11 }}>↻ Refresh</Button>}
            />
            {failoverEvents.length === 0 ? (
              <Card style={{ textAlign: "center", padding: 32, color: theme.textDim }}>
                <div style={{ fontSize: 28, marginBottom: 8 }}>✅</div>
                <div style={{ fontSize: 14, fontWeight: 600, color: theme.textMuted }}>No failovers recorded</div>
                <div style={{ fontSize: 12, color: theme.textDim, marginTop: 4 }}>All models operating within limits</div>
              </Card>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                {failoverEvents.map((ev, i) => {
                  const reasonColor = ev.reason.includes("rpm") ? theme.warning : ev.reason.includes("token") ? theme.info : theme.error;
                  const reasonLabel = { rpm_limit: "RPM Limit", token_limit: "Token Budget", api_error: "API Error", timeout: "Timeout", unavailable: "Unavailable", fallback_success: "Fallback OK", token_per_minute_limit: "TPM Limit", token_per_day_limit: "Day Budget" }[ev.reason] || ev.reason;
                  const agoStr = ev.ago_seconds < 60 ? `${ev.ago_seconds}s ago` : ev.ago_seconds < 3600 ? `${Math.round(ev.ago_seconds / 60)}m ago` : new Date(ev.timestamp * 1000).toLocaleTimeString();
                  return (
                    <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", background: theme.bgCard, border: `1px solid ${theme.border}`, borderLeft: `3px solid ${reasonColor}`, borderRadius: "0 8px 8px 0" }}>
                      <div style={{ fontSize: 10, color: theme.textDim, minWidth: 56, fontFamily: "monospace" }}>{agoStr}</div>
                      <div style={{ fontSize: 11, color: theme.textMuted, fontFamily: "monospace", maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{ev.from_model.split("/").pop()}</div>
                      <span style={{ fontSize: 14, color: reasonColor }}>→</span>
                      <div style={{ fontSize: 11, color: theme.accent, fontFamily: "monospace", maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{ev.to_model.split("/").pop()}</div>
                      <span style={{ padding: "2px 7px", borderRadius: 4, fontSize: 10, fontWeight: 700, background: `${reasonColor}22`, color: reasonColor, textTransform: "uppercase", flexShrink: 0 }}>{reasonLabel}</span>
                      <span style={{ fontSize: 10, color: theme.textDim, marginLeft: "auto", flexShrink: 0 }}>~{ev.context_tokens > 999 ? `${(ev.context_tokens / 1000).toFixed(1)}K` : ev.context_tokens} ctx</span>
                      {ev.task_hint && <span style={{ fontSize: 10, color: theme.textDim, maxWidth: 140, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={ev.task_hint}>"{ev.task_hint}"</span>}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Global Usage Summary */}
          {usageData.filter(m => (m.usage.total.requests > 0)).length > 0 && (
            <div>
              <SectionHeader title="📈 Usage Summary" subtitle="Aggregated token usage across all models" />
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 12 }}>
                {usageData.filter(m => (m.usage.total.requests > 0)).map(m => (
                  <Card key={m.model_id} style={{ padding: 14 }}>
                    <div style={{ fontSize: 12, fontWeight: 700, color: theme.text, marginBottom: 10, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{m.model_id.split("/").pop()}</div>
                    {[{ label: "Last Min", d: m.usage.per_minute }, { label: "Today", d: m.usage.per_day }, { label: "This Week", d: m.usage.per_week }].map(({ label, d }) => (
                      <div key={label} style={{ display: "flex", justifyContent: "space-between", marginBottom: 5, paddingBottom: 5, borderBottom: `1px solid ${theme.border}` }}>
                        <span style={{ fontSize: 11, color: theme.textDim }}>{label}</span>
                        <div>
                          <span style={{ fontSize: 12, fontWeight: 600, color: theme.text }}>{((d.input_tokens || 0) + (d.output_tokens || 0)).toLocaleString()}</span>
                          <span style={{ fontSize: 10, color: theme.textDim, marginLeft: 3 }}>tok</span>
                          <span style={{ fontSize: 10, color: theme.textDim, marginLeft: 8 }}>{d.requests || 0} req</span>
                          {(d.failures || 0) > 0 && <span style={{ fontSize: 10, color: theme.error, marginLeft: 6 }}>{d.failures} fail</span>}
                        </div>
                      </div>
                    ))}
                    <div style={{ display: "flex", gap: 10, marginTop: 8 }}>
                      {[
                        { val: m.usage.total.requests, label: "Calls", color: theme.accent },
                        { val: (m.usage.total.input_tokens || 0) + (m.usage.total.output_tokens || 0), label: "Tokens", color: theme.info, short: true },
                        { val: m.usage.total.failures || 0, label: "Failures", color: theme.error },
                      ].map(({ val, label, color, short }) => (
                        <div key={label} style={{ flex: 1, textAlign: "center" }}>
                          <div style={{ fontSize: 15, fontWeight: 800, color }}>{short && val > 999 ? `${(val / 1000).toFixed(1)}K` : val}</div>
                          <div style={{ fontSize: 9, color: theme.textDim, textTransform: "uppercase" }}>{label}</div>
                        </div>
                      ))}
                    </div>
                  </Card>
                ))}
              </div>
            </div>
          )}

          {/* Info box */}
          <div style={{ padding: 16, background: theme.bgCard, border: `1px solid ${theme.border}`, borderRadius: 10 }}>
            <div style={{ fontSize: 12, color: theme.textMuted, lineHeight: 1.8 }}>
              <strong style={{ color: theme.text }}>How smart failover works:</strong><br />
              1. Every LLM call checks the model's RPM window and token budgets <em>before</em> sending — no wasted requests.<br />
              2. If a limit would be exceeded, the call is instantly routed to the next model in the fallback chain.<br />
              3. The <strong style={{ color: theme.text }}>full message history</strong> (context window) is forwarded to the replacement model — it picks up exactly where the previous one left off.<br />
              4. API failures (rate-limit errors, timeouts, unavailability) also trigger seamless failover.<br />
              5. All events are logged above in real-time with context size, reason, and task description.
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
// File Browser Component (tree + code viewer)
// ──────────────────────────────────────────────

const buildFileTree = (filePaths) => {
  const root = {};
  for (const fp of filePaths) {
    const parts = fp.split("/");
    let node = root;
    for (let i = 0; i < parts.length - 1; i++) {
      if (!node[parts[i]] || typeof node[parts[i]] === "string") {
        node[parts[i]] = {};
      }
      node = node[parts[i]];
    }
    const fname = parts[parts.length - 1];
    if (typeof node === "object" && node !== null) {
      node[fname] = fp; // leaf = full path string
    }
  }
  return root;
};

const FileTreeNode = ({ name, node, depth, selectedFile, onSelect }) => {
  const isFile = typeof node === "string";
  const [open, setOpen] = useState(depth < 2);
  const indent = depth * 14;
  if (isFile) {
    const sel = selectedFile === node;
    return (
      <div
        onClick={() => onSelect(node)}
        title={node}
        style={{
          paddingLeft: indent + 8, paddingRight: 8, paddingTop: 4, paddingBottom: 4,
          fontSize: 11.5, cursor: "pointer", borderRadius: 4,
          color: sel ? theme.accent : theme.textMuted,
          background: sel ? theme.accentGlow : "transparent",
          fontFamily: "'JetBrains Mono', monospace",
          whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
          transition: "all 0.15s",
        }}
        onMouseEnter={e => { if (!sel) e.currentTarget.style.color = theme.text; }}
        onMouseLeave={e => { if (!sel) e.currentTarget.style.color = theme.textMuted; }}
      >
        📄 {name}
      </div>
    );
  }
  return (
    <div>
      <div
        onClick={() => setOpen(o => !o)}
        style={{
          paddingLeft: indent + 4, paddingRight: 8, paddingTop: 5, paddingBottom: 5,
          fontSize: 11.5, cursor: "pointer", display: "flex", alignItems: "center", gap: 4,
          color: theme.textMuted, userSelect: "none",
          transition: "color 0.15s",
        }}
        onMouseEnter={e => e.currentTarget.style.color = theme.text}
        onMouseLeave={e => e.currentTarget.style.color = theme.textMuted}
      >
        <span style={{ fontSize: 9 }}>{open ? "▾" : "▸"}</span>
        <span style={{ fontWeight: 600 }}>📁 {name}</span>
      </div>
      {open && Object.entries(node).sort(([a, av], [b, bv]) => {
        const aDir = typeof av !== "string"; const bDir = typeof bv !== "string";
        if (aDir !== bDir) return aDir ? -1 : 1;
        return a.localeCompare(b);
      }).map(([childName, childNode]) => (
        <FileTreeNode key={childName} name={childName} node={childNode} depth={depth + 1} selectedFile={selectedFile} onSelect={onSelect} />
      ))}
    </div>
  );
};

const getLanguageHint = (path) => {
  const ext = path.split(".").pop().toLowerCase();
  const map = { dart: "Dart", py: "Python", js: "JavaScript", jsx: "JSX", ts: "TypeScript", tsx: "TSX", json: "JSON", yaml: "YAML", yml: "YAML", html: "HTML", css: "CSS", md: "Markdown", txt: "Text", xml: "XML", sql: "SQL", sh: "Shell", env: "ENV" };
  return map[ext] || ext.toUpperCase();
};

class ErrorBoundary extends React.Component {
  constructor(props) { super(props); this.state = { hasError: false, error: null }; }
  static getDerivedStateFromError(error) { return { hasError: true, error }; }
  render() {
    if (this.state.hasError) {
      return <div style={{padding: 20, color: "red", background: "#330000"}}><h1>UI Crash</h1><pre>{this.state.error?.toString()}{"\n"}{this.state.error?.stack}</pre></div>;
    }
    return this.props.children;
  }
}

const FileBrowserTabContent = ({ files }) => {
  // Defensive: ensure files is always a plain object
  const safeFiles = (files && typeof files === "object" && !Array.isArray(files)) ? files : {};
  const [selectedFile, setSelectedFile] = useState(null);
  const filePaths = Object.keys(safeFiles).sort();
  const tree = buildFileTree(filePaths);
  const fileCount = filePaths.length;

  // Auto-select first file
  React.useEffect(() => {
    if (fileCount > 0 && !selectedFile) setSelectedFile(filePaths[0]);
  }, [fileCount]);

  if (fileCount === 0) {
    return (
      <Card style={{ padding: 40, textAlign: "center" }}>
        <div style={{ fontSize: 36, marginBottom: 12 }}>📂</div>
        <div style={{ color: theme.textMuted, fontSize: 14 }}>No files generated yet</div>
        <div style={{ color: theme.textDim, fontSize: 12, marginTop: 4 }}>Start a build to see generated code here</div>
      </Card>
    );
  }

  return (
    <div style={{ display: "grid", gridTemplateColumns: "260px 1fr", gap: 12, minHeight: 480 }}>
      {/* File Tree */}
      <Card style={{ padding: "8px 4px", overflowY: "auto", maxHeight: 520 }}>
        <div style={{ fontSize: 10, fontWeight: 700, color: theme.textDim, textTransform: "uppercase", letterSpacing: "0.5px", padding: "4px 12px 8px" }}>
          {fileCount} file{fileCount !== 1 ? "s" : ""}
        </div>
        {Object.entries(tree).sort(([a, av], [b, bv]) => {
          const aDir = typeof av !== "string"; const bDir = typeof bv !== "string";
          if (aDir !== bDir) return aDir ? -1 : 1;
          return a.localeCompare(b);
        }).map(([name, node]) => (
          <FileTreeNode key={name} name={name} node={node} depth={0} selectedFile={selectedFile} onSelect={setSelectedFile} />
        ))}
      </Card>

      {/* Code Viewer */}
      <Card style={{ padding: 0, overflow: "hidden", display: "flex", flexDirection: "column" }}>
        {selectedFile ? (
          <>
            <div style={{
              padding: "8px 14px", borderBottom: `1px solid ${theme.border}`,
              display: "flex", alignItems: "center", justifyContent: "space-between",
              background: theme.bgHover, flexShrink: 0,
            }}>
              <span style={{ fontSize: 12, color: theme.textMuted, fontFamily: "monospace", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {selectedFile}
              </span>
              <span style={{ fontSize: 10, color: theme.accent, fontWeight: 700, background: theme.accentGlow, padding: "2px 8px", borderRadius: 4, flexShrink: 0, marginLeft: 8 }}>
                {getLanguageHint(selectedFile)}
              </span>
            </div>
            <pre style={{
              padding: "14px 16px", margin: 0, fontSize: 12,
              color: theme.text, fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
              lineHeight: 1.65, overflowX: "auto", overflowY: "auto",
              flex: 1, maxHeight: 470, whiteSpace: "pre", wordBreak: "normal",
            }}>
              {safeFiles[selectedFile] || ""}
            </pre>
          </>
        ) : (
          <div style={{ padding: 40, textAlign: "center", color: theme.textDim, flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
            Select a file from the tree to view its contents
          </div>
        )}
      </Card>
    </div>
  );
};

const FileBrowserTab = (props) => (
  <ErrorBoundary>
    <FileBrowserTabContent {...props} />
  </ErrorBoundary>
);


// ──────────────────────────────────────────────

// Project Detail / Build Monitor Page
// ──────────────────────────────────────────────

const ProjectDetailPage = ({ projectId, onBack }) => {

  const [project, setProject] = useState(null);
  const [events, setEvents] = useState([]);
  const [workUnits, setWorkUnits] = useState([]);
  const [files, setFiles] = useState({});
  const [tab, setTab] = useState("live");
  const [feedback, setFeedback] = useState("");
  const [feedbackSending, setFeedbackSending] = useState(false);
  const [feedbackError, setFeedbackError] = useState("");
  const eventsEndRef = useRef(null);
  const wsRef = useRef(null);
  // Tracks event IDs we've already shown to prevent duplicates on reconnect
  const seenEventIds = useRef(new Set());

  // ── Helpers ──────────────────────────────────────────────────────────────
  const addEvents = useCallback((incoming) => {
    if (!Array.isArray(incoming)) return;
    setEvents((prev) => {
      const next = [...prev];
      for (const ev of incoming) {
        if (ev && ev.id && !seenEventIds.current.has(ev.id)) {
          seenEventIds.current.add(ev.id);
          next.push(ev);
        }
      }
      return next;
    });
  }, []);

  // ── Polling + WebSocket ───────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;

    const fetchData = async () => {
      try {
        const p = await api.getProject(projectId);
        if (!cancelled) setProject(p);
        try {
          const f = await api.getFiles(projectId);
          if (!cancelled && f && typeof f.files === "object" && f.files !== null && !Array.isArray(f.files)) {
            setFiles(f.files);
          }
        } catch {}
        try {
          const wu = await api.getWorkUnits(projectId);
          if (!cancelled) setWorkUnits(Array.isArray(wu) ? wu : []);
        } catch {}
      } catch (e) {
        console.error(e);
      }
    };

    // Seed event history from DB-backed logs endpoint (survives server restarts)
    const seedEvents = async () => {
      try {
        const evts = await api.getLogs(projectId);
        if (!cancelled && Array.isArray(evts)) addEvents(evts);
      } catch {}
    };

    fetchData();
    seedEvents();
    const interval = setInterval(fetchData, 3000);

    // WebSocket for live events
    let evtPollInterval = null;
    try {
      const wsBase = API_URL || `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`;
      const wsUrl = wsBase.replace(/^http/, "ws");
      const ws = new WebSocket(`${wsUrl}/ws/projects/${projectId}`);
      ws.onmessage = (e) => {
        const event = JSON.parse(e.data);
        if (event.type !== "ping") addEvents([event]);
      };
      ws.onerror = () => {
        // WebSocket failed — fall back to polling events endpoint
        evtPollInterval = setInterval(async () => {
          try {
            const evts = await api.getEvents(projectId);
            if (!cancelled && Array.isArray(evts)) addEvents(evts);
          } catch {}
        }, 2000);
      };
      ws.onclose = () => {
        // Attempt one final REST fetch on disconnect
        if (!cancelled) {
          api.getEvents(projectId).then((evts) => {
            if (!cancelled && Array.isArray(evts)) addEvents(evts);
          }).catch(() => {});
        }
      };
      wsRef.current = ws;
    } catch {}

    return () => {
      cancelled = true;
      clearInterval(interval);
      if (evtPollInterval) clearInterval(evtPollInterval);
      wsRef.current?.close();
    };
  }, [projectId, addEvents]);

  useEffect(() => {
    if (tab === "live" && events.length > 1) {
      eventsEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [events, tab]);

  const handleFeedback = async () => {
    if (!feedback.trim()) return;
    setFeedbackSending(true);
    setFeedbackError("");
    try {
      const res = await api.submitFeedback(projectId, feedback);
      if (res && res.detail) {
        setFeedbackError(res.detail);
      } else {
        setFeedback("");
        // Refresh project to show updated feedback_history
        try {
          const p = await api.getProject(projectId);
          setProject(p);
        } catch {}
      }
    } catch (e) {
      setFeedbackError(e.message || "Failed to submit feedback");
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

  const ACTIVE_STATUSES = ["analyzing", "planning", "building", "reviewing", "testing", "fixing"];
  const CAN_RESUME = project.status === "failed" && (project.input_text || (project.input_mockups && Object.keys(project.input_mockups).length > 0));

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

        {/* Build controls for active builds */}
        {ACTIVE_STATUSES.includes(project.status) && (
          <div style={{ display: "flex", gap: 6 }}>
            <button
              onClick={() => api.controlBuild(projectId, "pause")}
              title="Pause build"
              style={{ background: theme.warning + "22", border: `1px solid ${theme.warning}`, borderRadius: 6, color: theme.warning, padding: "4px 10px", fontSize: 13, cursor: "pointer", fontWeight: 700 }}
            >⏸ Pause</button>
            <button
              onClick={() => api.controlBuild(projectId, "cancel")}
              title="Cancel build"
              style={{ background: theme.error + "22", border: `1px solid ${theme.error}`, borderRadius: 6, color: theme.error, padding: "4px 10px", fontSize: 13, cursor: "pointer", fontWeight: 700 }}
            >⏹ Cancel</button>
          </div>
        )}

        {/* Resume button for paused/cancelled builds */}
        {project.status === "building" && (
          <button
            onClick={() => api.controlBuild(projectId, "resume")}
            style={{ background: theme.success + "22", border: `1px solid ${theme.success}`, borderRadius: 6, color: theme.success, padding: "4px 10px", fontSize: 13, cursor: "pointer", fontWeight: 700 }}
          >▶ Resume</button>
        )}

        {/* Resume after failure */}
        {CAN_RESUME && (
          <Button
            variant="primary"
            onClick={async () => {
              try {
                await api.resumeBuild(projectId);
                setProject(prev => ({ ...prev, status: "analyzing" }));
              } catch (e) { console.error(e); }
            }}
            style={{ padding: "6px 12px", fontSize: 12 }}
          >
            ▶ Resume Build
          </Button>
        )}

        {project.status === "failed" && !CAN_RESUME && (
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
        <FileBrowserTab files={files} />
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
          {feedbackError && (
            <div style={{ marginTop: 10, padding: "8px 12px", borderRadius: 8, background: theme.errorBg, color: theme.error, fontSize: 13, border: `1px solid ${theme.error}33` }}>
              ⚠ {feedbackError}
            </div>
          )}
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
  const [deletingId, setDeletingId] = useState(null);
  const [deleteFilesToo, setDeleteFilesToo] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);

  const loadProjects = async () => {
    try { setProjects(await api.listProjects()); } catch {}
    try { setMetrics(await api.getMetrics()); } catch {}
  };

  useEffect(() => {
    loadProjects();
    const i = setInterval(loadProjects, 5000);
    return () => clearInterval(i);
  }, []);

  const handleDelete = async (e, id) => {
    e.stopPropagation();
    setConfirmDeleteId(id);
  };

  const confirmDelete = async () => {
    setDeletingId(confirmDeleteId);
    try {
      await api.deleteProject(confirmDeleteId, deleteFilesToo);
      setProjects(prev => prev.filter(p => p.id !== confirmDeleteId));
    } catch (err) { console.error(err); }
    setDeletingId(null);
    setConfirmDeleteId(null);
    setDeleteFilesToo(false);
  };

  const totalCalls = Object.values(metrics).reduce((s, m) => s + (m.total_calls || 0), 0);
  const totalTokens = Object.values(metrics).reduce((s, m) => s + (m.total_input_tokens || 0) + (m.total_output_tokens || 0), 0);

  const activeStatuses = ["analyzing", "planning", "building", "reviewing", "testing", "fixing"];

  return (
    <div style={{ maxWidth: 960, margin: "0 auto", padding: "40px 20px" }}>
      {/* Delete Confirmation Modal */}
      {confirmDeleteId && (
        <div style={{
          position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", zIndex: 9999,
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          <div style={{ background: theme.bgCard, border: `1px solid ${theme.border}`, borderRadius: 16, padding: 32, maxWidth: 400, width: "90%" }}>
            <div style={{ fontSize: 18, fontWeight: 700, color: theme.text, marginBottom: 8 }}>Delete Project?</div>
            <div style={{ fontSize: 13, color: theme.textMuted, marginBottom: 20 }}>
              This will permanently remove the project from the database.
            </div>
            <label style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 24, cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={deleteFilesToo}
                onChange={e => setDeleteFilesToo(e.target.checked)}
                style={{ width: 16, height: 16, accentColor: theme.error }}
              />
              <span style={{ fontSize: 13, color: theme.text }}>Also delete generated files from disk</span>
            </label>
            <div style={{ display: "flex", gap: 10 }}>
              <Button variant="ghost" onClick={() => { setConfirmDeleteId(null); setDeleteFilesToo(false); }} style={{ flex: 1 }}>Cancel</Button>
              <button
                onClick={confirmDelete}
                disabled={deletingId !== null}
                style={{
                  flex: 1, padding: "10px 16px", borderRadius: 8, border: "none",
                  background: theme.error, color: "#fff", fontWeight: 700, fontSize: 14,
                  cursor: deletingId ? "wait" : "pointer", opacity: deletingId ? 0.7 : 1,
                }}
              >
                {deletingId ? "Deleting..." : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Hero */}
      <div style={{ textAlign: "center", marginBottom: 48 }}>
        <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}>
          <button
            id="llm-settings-btn"
            onClick={onSettings}
            title="LLM Model Settings"
            style={{
              background: "none", border: `1px solid ${theme.border}`,
              borderRadius: 8, color: theme.textMuted, cursor: "pointer",
              fontSize: 13, fontWeight: 600, padding: "7px 14px",
              display: "flex", alignItems: "center", gap: 6, transition: "all 0.2s",
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
              <Card
                key={p.id}
                onClick={() => onSelectProject(p.id)}
                style={{ padding: 16, position: "relative", cursor: "pointer" }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 16, fontWeight: 700, color: theme.text }}>{p.name}</span>
                    {activeStatuses.includes(p.status) && (
                      <span style={{ fontSize: 10, color: theme.accent, animation: "pulse 1.5s infinite" }}>● LIVE</span>
                    )}
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <StatusBadge status={p.status} />
                    <button
                      onClick={e => handleDelete(e, p.id)}
                      title="Delete project"
                      style={{
                        background: "none", border: "none", cursor: "pointer",
                        color: theme.textDim, fontSize: 16, padding: "2px 6px",
                        borderRadius: 4, transition: "color 0.2s",
                      }}
                      onMouseEnter={e => e.currentTarget.style.color = theme.error}
                      onMouseLeave={e => e.currentTarget.style.color = theme.textDim}
                    >
                      🗑
                    </button>
                  </div>
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
