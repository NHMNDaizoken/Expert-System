import { useEffect, useMemo, useState } from "react";
import { Check, RefreshCw, X } from "lucide-react";
import { adminHeaders, api } from "../api/client.js";

function makeSymptomId(text) {
  const slug = String(text || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_|_$/g, "");
  return `SYM_${slug || "LLM_SUGGESTION"}`;
}

function buildApprovedPayload(suggestion) {
  const diagnoses = suggestion?.llm_output?.diagnoses || [];
  const firstDiagnosis = diagnoses[0] || {};
  return {
    symptom_id:
      firstDiagnosis.matched_rules?.[0]?.symptom_id?.startsWith("SYM_")
        ? firstDiagnosis.matched_rules[0].symptom_id
        : makeSymptomId(suggestion?.user_input),
    label_vi: suggestion?.user_input || "",
    aliases: suggestion?.user_input ? [suggestion.user_input] : [],
    system_id: firstDiagnosis.system_id || firstDiagnosis.system || "SYS_ENGINE",
    diagnoses,
    questions: [],
  };
}

function statusText(suggestion) {
  if (suggestion.review_status === "approved") return "Đã đồng ý";
  if (suggestion.review_status === "rejected") return "Đã từ chối";
  if (suggestion.reviewed) return "Đã kiểm duyệt";
  return "Đang chờ";
}

export default function ExpertReview() {
  const [adminApiKey, setAdminApiKey] = useState("");
  const [suggestions, setSuggestions] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [payloadText, setPayloadText] = useState("");
  const [rejectReason, setRejectReason] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [rebuildOutput, setRebuildOutput] = useState(null);

  const selected = useMemo(
    () => suggestions.find((suggestion) => suggestion.id === selectedId) || suggestions[0],
    [suggestions, selectedId]
  );

  async function loadSuggestions() {
    setError("");
    setMessage("");
    setLoading(true);
    try {
      const response = await api.get(
        "/expert-review/suggestions",
        adminHeaders(adminApiKey)
      );
      const nextSuggestions = response.data.suggestions || [];
      setSuggestions(nextSuggestions);
      setSelectedId((current) =>
        nextSuggestions.some((suggestion) => suggestion.id === current)
          ? current
          : nextSuggestions[0]?.id || ""
      );
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  }

  async function approveSuggestion() {
    setError("");
    setMessage("");
    if (!selected) return;

    let approvedPayload;
    try {
      approvedPayload = JSON.parse(payloadText);
    } catch {
      setError("JSON approved_payload không hợp lệ.");
      return;
    }

    try {
      await api.post(
        `/expert-review/suggestions/${encodeURIComponent(selected.id)}/approve`,
        { approved_payload: approvedPayload },
        adminHeaders(adminApiKey)
      );
      setMessage("Đã đồng ý và ghi vào staging KG.");
      await loadSuggestions();
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    }
  }

  async function rejectSuggestion() {
    setError("");
    setMessage("");
    if (!selected) return;
    try {
      await api.post(
        `/expert-review/suggestions/${encodeURIComponent(selected.id)}/reject`,
        { reason: rejectReason },
        adminHeaders(adminApiKey)
      );
      setRejectReason("");
      setMessage("Đã từ chối gợi ý.");
      await loadSuggestions();
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    }
  }

  async function rebuildKnowledge() {
    setError("");
    setMessage("");
    setRebuildOutput(null);
    try {
      const response = await api.post(
        "/expert-review/rebuild",
        {},
        adminHeaders(adminApiKey)
      );
      setRebuildOutput(response.data);
      setMessage(response.data.success ? "Build lại KG hoàn tất." : "Build lại KG có lỗi.");
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    }
  }

  useEffect(() => {
    if (selected) {
      setPayloadText(JSON.stringify(buildApprovedPayload(selected), null, 2));
      setRejectReason("");
    } else {
      setPayloadText("");
    }
  }, [selected]);

  const filteredSuggestions = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (suggestions || []).filter((item) => {
      const statusOk = statusFilter === "all" || item.review_status === statusFilter;
      if (!statusOk) return false;
      if (!q) return true;
      const haystack = `${item.user_input || ""} ${item.reason || ""} ${item.id || ""}`.toLowerCase();
      return haystack.includes(q);
    });
  }, [query, statusFilter, suggestions]);

  const diagnoses = selected?.llm_output?.diagnoses || [];
  const notes = selected?.llm_output?.notes || [];

  return (
    <div className="page review-page">
      <header className="toolbar-header">
        <div>
          <h1>Kiểm duyệt luật</h1>
          <p>Duyệt gợi ý LLM vào staging KG trước khi build/import Neo4j.</p>
        </div>
        <div className="action-row">
          <input
            className="admin-key"
            type="password"
            value={adminApiKey}
            onChange={(event) => setAdminApiKey(event.target.value)}
            placeholder="X-Admin-API-Key"
          />
          <button onClick={loadSuggestions} disabled={!adminApiKey.trim() || loading}>
            <RefreshCw size={18} className={loading ? "spin" : ""} />
            Tải gợi ý
          </button>
          <button onClick={rebuildKnowledge} disabled={!adminApiKey.trim()}>
            <RefreshCw size={18} />
            Build lại KG
          </button>
        </div>
      </header>

      {(error || message) && (
        <div className="review-messages">
          {error && <p className="error">{error}</p>}
          {message && <p className="success">{message}</p>}
        </div>
      )}

      <section className="review-layout">
        <aside className="review-sidebar" aria-label="Danh sách gợi ý kiểm duyệt">
          <div className="review-sidebar-head">
            <div>
              <h2>Hàng chờ</h2>
              <p>{filteredSuggestions.length} gợi ý</p>
            </div>
            <div className="review-filters">
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Tìm theo triệu chứng / lý do / id"
              />
              <select
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value)}
                aria-label="Lọc theo trạng thái"
              >
                <option value="all">Tất cả</option>
                <option value="pending">Đang chờ</option>
                <option value="approved">Đã đồng ý</option>
                <option value="rejected">Đã từ chối</option>
              </select>
            </div>
          </div>

          <div className="review-items">
            {filteredSuggestions.length === 0 && (
              <p className="muted review-empty">Không có gợi ý phù hợp với bộ lọc hiện tại.</p>
            )}
            {filteredSuggestions.map((suggestion) => (
              <button
                key={suggestion.id}
                type="button"
                className={`review-item ${selected?.id === suggestion.id ? "active" : ""}`}
                onClick={() => setSelectedId(suggestion.id)}
              >
                <div className="review-item-main">
                  <span className="review-item-title">{suggestion.user_input}</span>
                  <span className="review-item-reason">{suggestion.reason}</span>
                </div>
                <div className="review-item-meta">
                  <span className={`review-status ${suggestion.review_status || "pending"}`}>
                    {statusText(suggestion)}
                  </span>
                  <span className="review-promote">
                    {suggestion.promoted_to_kb ? "Đã vào staging" : "Chưa promote"}
                  </span>
                </div>
              </button>
            ))}
          </div>
        </aside>

        <div className="review-detail" aria-label="Chi tiết gợi ý">
          {!selected ? (
            <div className="review-detail-empty">
              <p className="muted">Chọn một gợi ý ở cột trái để xem chi tiết.</p>
            </div>
          ) : (
            <div className="review-detail-card">
              <div className="review-detail-head">
                <div>
                  <h2>{selected.user_input}</h2>
                  <p className="muted">{selected.reason}</p>
                  <div className="review-detail-badges">
                    <span className={`review-status ${selected.review_status || "pending"}`}>
                      {statusText(selected)}
                    </span>
                    <span className="review-promote">
                      {selected.promoted_to_kb ? "promoted_to_kb=true" : "promoted_to_kb=false"}
                    </span>
                    <code>{selected.id}</code>
                  </div>
                </div>
              </div>

              <section className="review-section">
                <h3>Chẩn đoán LLM</h3>
                {diagnoses.length === 0 ? (
                  <p className="muted">Không có chẩn đoán trong output.</p>
                ) : (
                  <div className="review-diagnoses">
                    {diagnoses.map((diagnosis) => (
                      <article className="review-diagnosis" key={diagnosis.fault_id}>
                        <div>
                          <h4>{diagnosis.fault_label || diagnosis.fault_name}</h4>
                          <p className="muted">{diagnosis.system}</p>
                          <code>{diagnosis.fault_id}</code>
                        </div>
                        <strong>{Number(diagnosis.final_cf ?? 0).toFixed(2)}</strong>
                      </article>
                    ))}
                  </div>
                )}
              </section>

              {notes.length > 0 && (
                <section className="review-section">
                  <h3>Ghi chú</h3>
                  <div className="review-notes">
                    {notes.map((note) => (
                      <p key={note}>{note}</p>
                    ))}
                  </div>
                </section>
              )}

              <section className="review-section">
                <h3>approved_payload</h3>
                <textarea
                  className="json-editor"
                  value={payloadText}
                  onChange={(event) => setPayloadText(event.target.value)}
                  rows={18}
                />
              </section>

              <div className="review-actions">
                <button onClick={approveSuggestion} disabled={!adminApiKey.trim()}>
                  <Check size={18} />
                  Đồng ý
                </button>
                <input
                  className="admin-key"
                  value={rejectReason}
                  onChange={(event) => setRejectReason(event.target.value)}
                  placeholder="Lý do từ chối"
                />
                <button
                  className="danger"
                  onClick={rejectSuggestion}
                  disabled={!adminApiKey.trim()}
                >
                  <X size={18} />
                  Từ chối
                </button>
              </div>

              {rebuildOutput && (
                <section className="review-section">
                  <h3>Kết quả build</h3>
                  <pre>{JSON.stringify(rebuildOutput, null, 2)}</pre>
                </section>
              )}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
