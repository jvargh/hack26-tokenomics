import { useState, useEffect } from "react";
import { api } from "../api/client";
import type { FoundryConfig, FoundryTestResult, PriceTableEntry } from "../api/types";
import { useRun } from "../state/runContext";

interface FoundryConfigModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function FoundryConfigModal({ isOpen, onClose }: FoundryConfigModalProps) {
  const { refreshHealth } = useRun();
  const [config, setConfig] = useState<FoundryConfig | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [testingEfficient, setTestingEfficient] = useState(false);
  const [efficientResult, setEfficientResult] = useState<FoundryTestResult | null>(null);

  const [testingAdvanced, setTestingAdvanced] = useState(false);
  const [advancedResult, setAdvancedResult] = useState<FoundryTestResult | null>(null);

  useEffect(() => {
    if (isOpen) {
      loadConfig();
    }
  }, [isOpen]);

  const loadConfig = async () => {
    setLoading(true);
    setErrorMessage(null);
    setSaveSuccess(false);
    try {
      const data = await api.getFoundryConfig();
      setConfig(data);
      setApiKeyInput("");
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to load Foundry configuration.");
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  const handleSave = async () => {
    if (!config) return;
    setSaving(true);
    setErrorMessage(null);
    setSaveSuccess(false);
    try {
      const payload: Partial<FoundryConfig> & { api_key?: string } = {
        model_mode: config.model_mode,
        foundry_base_url: config.foundry_base_url,
        foundry_auth_mode: config.foundry_auth_mode,
        foundry_token_scope: config.foundry_token_scope,
        efficient_deployment: config.efficient_deployment,
        advanced_deployment: config.advanced_deployment,
        price_table: config.price_table
      };
      if (apiKeyInput.trim()) {
        payload.api_key = apiKeyInput.trim();
      }
      const updated = await api.updateFoundryConfig(payload);
      setConfig(updated);
      setSaveSuccess(true);
      await refreshHealth();
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to save configuration.");
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async (type: "efficient" | "advanced") => {
    if (type === "efficient") {
      setTestingEfficient(true);
      setEfficientResult(null);
      try {
        const res = await api.testFoundry("efficient");
        setEfficientResult(res);
      } catch (err) {
        setEfficientResult({
          success: false,
          error: err instanceof Error ? err.message : "Network error"
        });
      } finally {
        setTestingEfficient(false);
      }
    } else {
      setTestingAdvanced(true);
      setAdvancedResult(null);
      try {
        const res = await api.testFoundry("advanced");
        setAdvancedResult(res);
      } catch (err) {
        setAdvancedResult({
          success: false,
          error: err instanceof Error ? err.message : "Network error"
        });
      } finally {
        setTestingAdvanced(false);
      }
    }
  };

  const updatePrice = (deployment: string, field: keyof PriceTableEntry, value: string | number) => {
    if (!config) return;
    const currentEntry = config.price_table[deployment] || {
      input_per_1m_usd: 0,
      output_per_1m_usd: 0
    };
    setConfig({
      ...config,
      price_table: {
        ...config.price_table,
        [deployment]: {
          ...currentEntry,
          [field]: typeof value === "string" && (field === "input_per_1m_usd" || field === "output_per_1m_usd")
            ? parseFloat(value) || 0
            : value
        }
      }
    });
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal-card foundry-config-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="foundry-config-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <div>
            <h2 id="foundry-config-title" className="modal-title">
              Microsoft Foundry & AI Model Configuration
            </h2>
            <p className="muted modal-subtitle">
              Configure Azure AI Foundry endpoints, model routing tiers, authentication, and price tables.
            </p>
          </div>
          <button type="button" className="btn btn-icon" onClick={onClose} aria-label="Close modal">
            ✕
          </button>
        </div>

        {loading ? (
          <div className="modal-body muted" style={{ padding: "2rem", textAlign: "center" }}>
            Loading configuration from local TokenOS control plane…
          </div>
        ) : config ? (
          <div className="modal-body foundry-config-body">
            {saveSuccess ? (
              <div className="config-banner is-success">
                ✓ Configuration updated. Live routing and price table reloaded immediately.
              </div>
            ) : null}

            {errorMessage ? (
              <div className="config-banner is-error">
                ⚠ {errorMessage}
              </div>
            ) : null}

            {/* Quick Live Health / Ping Section */}
            <div className="config-section">
              <h3 className="config-section-title">Live Connectivity & Health Ping</h3>
              <p className="muted" style={{ fontSize: "0.85rem", marginBottom: "0.75rem" }}>
                Send a real test request to verify Azure AI Foundry authentication, deployment responsiveness, and token metrics.
              </p>
              <div className="ping-test-grid">
                <div className="ping-card">
                  <div className="ping-card-header">
                    <strong>Efficient Tier:</strong> <code>{config.efficient_deployment}</code>
                    <button
                      type="button"
                      className="btn btn-small btn-secondary"
                      disabled={testingEfficient || !config.foundry_available}
                      onClick={() => void handleTest("efficient")}
                    >
                      {testingEfficient ? "Pinging…" : "Ping Efficient"}
                    </button>
                  </div>
                  {efficientResult ? (
                    <div className={`ping-result ${efficientResult.success ? "is-ok" : "is-failed"}`}>
                      {efficientResult.success ? (
                        <>
                          <div>✓ <strong>Online:</strong> {efficientResult.latency_ms}ms latency · Model: {efficientResult.model_version}</div>
                          <div className="muted" style={{ fontSize: "0.8rem" }}>
                            Usage: {efficientResult.input_tokens} prompt / {efficientResult.output_tokens} completion tokens (${efficientResult.cost_usd?.toFixed(6)})
                          </div>
                          <div className="ping-preview">"{efficientResult.response_preview}"</div>
                        </>
                      ) : (
                        <div>✗ <strong>Failed:</strong> {efficientResult.error}</div>
                      )}
                    </div>
                  ) : null}
                </div>

                <div className="ping-card">
                  <div className="ping-card-header">
                    <strong>Advanced Tier:</strong> <code>{config.advanced_deployment}</code>
                    <button
                      type="button"
                      className="btn btn-small btn-secondary"
                      disabled={testingAdvanced || !config.foundry_available}
                      onClick={() => void handleTest("advanced")}
                    >
                      {testingAdvanced ? "Pinging…" : "Ping Advanced"}
                    </button>
                  </div>
                  {advancedResult ? (
                    <div className={`ping-result ${advancedResult.success ? "is-ok" : "is-failed"}`}>
                      {advancedResult.success ? (
                        <>
                          <div>✓ <strong>Online:</strong> {advancedResult.latency_ms}ms latency · Model: {advancedResult.model_version}</div>
                          <div className="muted" style={{ fontSize: "0.8rem" }}>
                            Usage: {advancedResult.input_tokens} prompt / {advancedResult.output_tokens} completion tokens (${advancedResult.cost_usd?.toFixed(6)})
                          </div>
                          <div className="ping-preview">"{advancedResult.response_preview}"</div>
                        </>
                      ) : (
                        <div>✗ <strong>Failed:</strong> {advancedResult.error}</div>
                      )}
                    </div>
                  ) : null}
                </div>
              </div>
            </div>

            {/* General Connection Settings */}
            <div className="config-section">
              <h3 className="config-section-title">Endpoint & Authentication</h3>
              <div className="form-grid">
                <div className="form-group">
                  <label htmlFor="cfg-model-mode">Execution Mode</label>
                  <select
                    id="cfg-model-mode"
                    className="form-control"
                    value={config.model_mode}
                    onChange={(e) => setConfig({ ...config, model_mode: e.target.value })}
                  >
                    <option value="foundry">Foundry Hybrid (Rules + Azure AI Foundry)</option>
                    <option value="local">Local Rules Only (No AI Model Route)</option>
                  </select>
                  <span className="form-hint">Hybrid mode enables bounded AI extraction and escalation.</span>
                </div>

                <div className="form-group">
                  <label htmlFor="cfg-auth-mode">Authentication Mode</label>
                  <select
                    id="cfg-auth-mode"
                    className="form-control"
                    value={config.foundry_auth_mode}
                    onChange={(e) => setConfig({ ...config, foundry_auth_mode: e.target.value })}
                  >
                    <option value="entra">Microsoft Entra ID (Token Credential - Recommended)</option>
                    <option value="api_key">API Key (AZURE_INFERENCE_CREDENTIAL)</option>
                  </select>
                  <span className="form-hint">Entra ID authenticates via Azure CLI / Managed Identity.</span>
                </div>

                <div className="form-group full-width">
                  <label htmlFor="cfg-base-url">Foundry / Azure OpenAI Base URL</label>
                  <input
                    id="cfg-base-url"
                    type="text"
                    className="form-control"
                    placeholder="https://<resource>.openai.azure.com/openai/v1/"
                    value={config.foundry_base_url}
                    onChange={(e) => setConfig({ ...config, foundry_base_url: e.target.value })}
                  />
                  <span className="form-hint">OpenAI v1 compatible endpoint for Azure AI Foundry.</span>
                </div>

                {config.foundry_auth_mode === "entra" ? (
                  <div className="form-group full-width">
                    <label htmlFor="cfg-token-scope">Entra ID Token Scope</label>
                    <input
                      id="cfg-token-scope"
                      type="text"
                      className="form-control"
                      value={config.foundry_token_scope}
                      onChange={(e) => setConfig({ ...config, foundry_token_scope: e.target.value })}
                    />
                    <span className="form-hint">Default is https://cognitiveservices.azure.com/.default</span>
                  </div>
                ) : (
                  <div className="form-group full-width">
                    <label htmlFor="cfg-api-key">API Key Override</label>
                    <input
                      id="cfg-api-key"
                      type="password"
                      className="form-control"
                      placeholder={config.has_api_key ? "•••••••••••• (Configured on server)" : "Enter Azure API key"}
                      value={apiKeyInput}
                      onChange={(e) => setApiKeyInput(e.target.value)}
                    />
                    <span className="form-hint">Leave blank to keep existing key.</span>
                  </div>
                )}
              </div>
            </div>

            {/* Model Deployments & Routing */}
            <div className="config-section">
              <h3 className="config-section-title">Model Deployment Routing</h3>
              <div className="form-grid">
                <div className="form-group">
                  <label htmlFor="cfg-eff-dep">Efficient Tier Deployment</label>
                  <input
                    id="cfg-eff-dep"
                    type="text"
                    className="form-control"
                    value={config.efficient_deployment}
                    onChange={(e) => setConfig({ ...config, efficient_deployment: e.target.value })}
                  />
                  <span className="form-hint">Used for fast first-pass extraction (e.g. tokenos-gpt41-nano)</span>
                </div>

                <div className="form-group">
                  <label htmlFor="cfg-adv-dep">Advanced Tier Deployment</label>
                  <input
                    id="cfg-adv-dep"
                    type="text"
                    className="form-control"
                    value={config.advanced_deployment}
                    onChange={(e) => setConfig({ ...config, advanced_deployment: e.target.value })}
                  />
                  <span className="form-hint">Used only for complex escalations (e.g. tokenos-gpt4o)</span>
                </div>
              </div>
            </div>

            {/* Price Table Configuration */}
            <div className="config-section">
              <h3 className="config-section-title">Price Table (Per 1 Million Tokens)</h3>
              <p className="muted" style={{ fontSize: "0.85rem", marginBottom: "0.75rem" }}>
                TokenOS calculates cost from real token usage using these rates. Versioned by model and region.
              </p>
              <div className="price-table-grid">
                {Object.entries(config.price_table).filter(([k]) => !k.startsWith("_")).map(([dep, entry]) => (
                  <div key={dep} className="price-entry-card">
                    <div className="price-entry-header">
                      <strong>{dep}</strong>
                      <span className="badge badge-muted">{entry.model || dep}</span>
                    </div>
                    <div className="price-entry-inputs">
                      <div className="price-input-row">
                        <label>Input $/1M:</label>
                        <input
                          type="number"
                          step="0.01"
                          className="form-control form-control-sm"
                          value={entry.input_per_1m_usd}
                          onChange={(e) => updatePrice(dep, "input_per_1m_usd", e.target.value)}
                        />
                      </div>
                      <div className="price-input-row">
                        <label>Output $/1M:</label>
                        <input
                          type="number"
                          step="0.01"
                          className="form-control form-control-sm"
                          value={entry.output_per_1m_usd}
                          onChange={(e) => updatePrice(dep, "output_per_1m_usd", e.target.value)}
                        />
                      </div>
                      <div className="price-input-row">
                        <label>Region:</label>
                        <input
                          type="text"
                          className="form-control form-control-sm"
                          value={entry.region || ""}
                          onChange={(e) => updatePrice(dep, "region", e.target.value)}
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        ) : null}

        <div className="modal-footer">
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Close
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={saving || loading || !config}
            onClick={() => void handleSave()}
          >
            {saving ? "Saving…" : "Save Configuration"}
          </button>
        </div>
      </div>
    </div>
  );
}
