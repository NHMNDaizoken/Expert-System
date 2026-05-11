import { useState } from "react";
import { Check, RefreshCw, X } from "lucide-react";
import { adminHeaders, api } from "../api/client.js";

export default function ExpertReview() {
  const [adminApiKey, setAdminApiKey] = useState("");
  const [rules, setRules] = useState([]);
  const [error, setError] = useState("");

  async function loadRules() {
    setError("");
    try {
      const response = await api.get("/pending-rules", adminHeaders(adminApiKey));
      setRules(response.data.rules);
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    }
  }

  async function decide(rule, status) {
    setError("");
    try {
      await api.post(
        `/rules/${encodeURIComponent(rule.rule_id)}/${status}`,
        { cf: Number(rule.cf) },
        adminHeaders(adminApiKey)
      );
      await loadRules();
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    }
  }

  function updateCf(ruleId, value) {
    setRules((current) =>
      current.map((rule) =>
        rule.rule_id === ruleId ? { ...rule, cf: value } : rule
      )
    );
  }

  return (
    <div className="page">
      <header className="toolbar-header">
        <div>
          <h1>Expert Review</h1>
          <p>Approve or reject pending knowledge before it enters the graph.</p>
        </div>
        <button onClick={loadRules} disabled={!adminApiKey.trim()}>
          <RefreshCw size={18} />
          Load
        </button>
      </header>
      <input
        className="admin-key"
        type="password"
        value={adminApiKey}
        onChange={(event) => setAdminApiKey(event.target.value)}
        placeholder="X-Admin-API-Key"
      />
      {error && <p className="error">{error}</p>}
      <div className="review-list">
        {rules.map((rule) => (
          <article className="review-card" key={rule.rule_id}>
            <div>
              <h3>{rule.fault_label || rule.fault_name}</h3>
              <p>{rule.symptom_label || rule.symptom_name}</p>
              <code>{rule.rule_id}</code>
            </div>
            <input
              type="number"
              min="0"
              max="1"
              step="0.01"
              value={rule.cf ?? 0}
              onChange={(event) => updateCf(rule.rule_id, event.target.value)}
            />
            <div className="action-row">
              <button onClick={() => decide(rule, "approve")}>
                <Check size={18} />
                Approve
              </button>
              <button className="danger" onClick={() => decide(rule, "reject")}>
                <X size={18} />
                Reject
              </button>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
