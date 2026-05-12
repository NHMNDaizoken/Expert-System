import { useEffect, useMemo, useState } from "react";
import { Check, Edit3, HelpCircle, RefreshCw, X } from "lucide-react";
import { adminHeaders, api } from "../api/client.js";
import DebugLogsPanel from "../components/DebugLogsPanel.jsx";
import TechnicalPayloadPanel from "../components/TechnicalPayloadPanel.jsx";

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

function statusText(suggestion = {}) {
  if (suggestion.review_status === "approved") return "Đã đồng ý";
  if (suggestion.review_status === "rejected") return "Đã từ chối";
  if (suggestion.reviewed) return "Đã kiểm duyệt";
  return "Đang chờ";
}

function systemLabel(value) {
  const labels = {
    SYS_ENGINE: "Động cơ",
    SYS_BRAKE: "Phanh",
    SYS_ELECTRICAL: "Điện",
    SYS_COOLING: "Làm mát",
    SYS_FUEL: "Nhiên liệu",
    SYS_TRANSMISSION: "Hộp số",
    "Cooling System": "Làm mát",
    "Fuel System": "Nhiên liệu",
  };
  return labels[value] || value || "Chưa rõ";
}

function reviewSummary(suggestion) {
  const tree = suggestion?.llm_output?.diagnostic_tree || {};
  const symptom = tree.level_2_primary_symptom || {};
  const root = tree.level_1_root || {};
  const diagnoses = suggestion?.llm_output?.diagnoses || tree.level_4_possible_faults || [];
  const top = diagnoses[0] || {};

  return {
    primary: symptom.symptom_label_vi || suggestion?.user_input || "Chưa rõ triệu chứng",
    system: root.system_label || top.system || "Chưa rõ",
    currentDiagnosis:
      top.fault_label_vi ||
      top.fault_label_en ||
      top.fault_label ||
      "Triệu chứng chưa được KG hiện tại phủ đủ",
    recommended:
      top.decision ||
      "Tạo ánh xạ triệu chứng mới hoặc yêu cầu thêm thông tin từ người dùng.",
    questions: tree.level_3_context?.missing_questions || [],
    summaryText: suggestion?.llm_output?.summary_vi,
  };
}

function publicError(err) {
  const detail = err.response?.data?.detail || err.message || "";
  if (/api[_ -]?key|gemini|llm fallback|module/i.test(detail)) {
    return "Không tải được dữ liệu kiểm duyệt. Xem Nhật ký gỡ lỗi để biết chi tiết kỹ thuật.";
  }
  return detail;
}

function parsePayloadText(value) {
  try {
    return { approved_payload: JSON.parse(value || "{}") };
  } catch {
    return { approved_payload: value };
  }
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
  const [debugError, setDebugError] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [rebuildOutput, setRebuildOutput] = useState(null);
  const [isEditingPayload, setIsEditingPayload] = useState(false);

  const selected = useMemo(
    () => suggestions.find((suggestion) => suggestion.id === selectedId) || suggestions[0],
    [suggestions, selectedId]
  );

  async function loadSuggestions() {
    setError("");
    setDebugError("");
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
      setError(publicError(err));
      setDebugError(err.response?.data?.detail || err.message);
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
      setError("Payload JSON không hợp lệ. Mở mục Chi tiết kỹ thuật để chỉnh lại.");
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
      setError(publicError(err));
      setDebugError(err.response?.data?.detail || err.message);
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
      setError(publicError(err));
      setDebugError(err.response?.data?.detail || err.message);
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
      setError(publicError(err));
      setDebugError(err.response?.data?.detail || err.message);
    }
  }

  useEffect(() => {
    if (selected) {
      setPayloadText(JSON.stringify(buildApprovedPayload(selected), null, 2));
      setRejectReason("");
      setIsEditingPayload(false);
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
  const summary = reviewSummary(selected);

  return (
    <div className="page review-page">
      <header className="toolbar-header">
        <div>
          <h1>Kiểm duyệt luật</h1>
          <p>Duyệt gợi ý của LLM trước khi ghi vào đồ thị tri thức.</p>
        </div>
        <div className="action-row">
          <input
            className="admin-key"
            type="password"
            value={adminApiKey}
            onChange={(event) => setAdminApiKey(event.target.value)}
            placeholder="Khóa quản trị (X-Admin-API-Key)"
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
              <p>{loading ? "Đang tải..." : `${filteredSuggestions.length} gợi ý`}</p>
            </div>
            <div className="review-filters">
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Tìm triệu chứng hoặc lý do"
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
            {loading && <p className="muted review-empty">Đang tải hàng chờ kiểm duyệt...</p>}
            {!loading && filteredSuggestions.length === 0 && (
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
                  <span className="review-item-reason">
                    Lý do:{" "}
                    {suggestion.reason || "Không khớp triệu chứng trong đồ thị tri thức"}
                  </span>
                </div>
                <div className="review-item-meta">
                  <span className={`review-status ${suggestion.review_status || "pending"}`}>
                    {statusText(suggestion)}
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
                  <p className="muted">Xem xét và chỉnh sửa nội dung trước khi đưa vào đồ thị tri thức.</p>
                  <div className="review-detail-badges">
                    <span className={`review-status ${selected.review_status || "pending"}`}>
                      {statusText(selected)}
                    </span>
                    <span className="review-promote">
                      {selected.promoted_to_kb ? "Đã thêm vào staging" : "Chưa thêm vào staging"}
                    </span>
                  </div>
                </div>
              </div>

              <section className="review-summary-grid">
                <ReviewSummaryCard title="Triệu chứng chính" value={summary.primary} />
                <ReviewSummaryCard title="Hệ thống phát hiện" value={systemLabel(summary.system)} />
                <ReviewSummaryCard title="Chẩn đoán hiện tại" value={summary.currentDiagnosis} />
                <ReviewSummaryCard title="Gợi ý xử lý" value={summary.recommended} />
              </section>

              <SymptomInfoCard summary={summary} />
              <DiagnosisCandidateCard diagnoses={diagnoses} />
              <SuggestedActionCard />

              {notes.length > 0 && (
                <section className="review-section reviewer-notes">
                  <h3>Ghi chú kiểm duyệt</h3>
                  <div className="review-notes">
                    {notes.map((note) => (
                      <p key={note}>{note}</p>
                    ))}
                  </div>
                </section>
              )}

              <TechnicalPayloadPanel
                title="Chi tiết kỹ thuật (payload)"
                editable={isEditingPayload}
                value={payloadText}
                onChange={setPayloadText}
                payload={parsePayloadText(payloadText)}
              />
              <DebugLogsPanel
                logs={{
                  error: debugError,
                  review_record: selected,
                  rebuild_output: rebuildOutput,
                }}
              />

              <div className="review-actions">
                <button onClick={approveSuggestion} disabled={!adminApiKey.trim()}>
                  <Check size={18} />
                  Phê duyệt và thêm vào KG
                </button>
                <button
                  type="button"
                  className="secondary-btn"
                  onClick={() => setIsEditingPayload((value) => !value)}
                >
                  <Edit3 size={18} />
                  {isEditingPayload ? "Đóng chỉnh sửa" : "Chỉnh sửa trước khi duyệt"}
                </button>
                <button type="button" className="secondary-btn" disabled title="Liên hệ người dùng để bổ sung thông tin ngoài ứng dụng">
                  <HelpCircle size={18} />
                  Yêu cầu thêm dữ liệu
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
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function ReviewSummaryCard({ title, value }) {
  return (
    <article className="review-info-card">
      <span>{title}</span>
      <strong>{value || "Chưa rõ"}</strong>
    </article>
  );
}

function SymptomInfoCard({ summary }) {
  return (
    <section className="review-section review-readable-card">
      <h3>Thông tin triệu chứng</h3>
      <p>{summary.summaryText || summary.primary}</p>
      {summary.questions.length > 0 && (
        <ul>
          {summary.questions.slice(0, 4).map((question) => (
            <li key={question}>{question}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

function DiagnosisCandidateCard({ diagnoses }) {
  return (
    <section className="review-section review-readable-card">
      <h3>Ứng viên chẩn đoán</h3>
      {diagnoses.length === 0 ? (
        <p className="muted">Chưa có chẩn đoán đã xác minh. Nên giữ trong hàng chờ kiểm duyệt.</p>
      ) : (
        <div className="review-diagnoses">
          {diagnoses.map((diagnosis, index) => (
            <article className="review-diagnosis" key={diagnosis.fault_id || index}>
              <div>
                <h4>
                  {diagnosis.fault_label_vi ||
                    diagnosis.fault_label ||
                    diagnosis.fault_name ||
                    "Triệu chứng chưa ánh xạ"}
                </h4>
                <p className="muted">{systemLabel(diagnosis.system)}</p>
              </div>
              <strong>
                {Math.round(Number(diagnosis.confidence ?? diagnosis.final_cf ?? 0) * 100)}%
              </strong>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function SuggestedActionCard() {
  return (
    <section className="review-section review-readable-card">
      <h3>Gợi ý thao tác</h3>
      <p>
        Xác nhận triệu chứng, hệ thống, lỗi ứng viên và các bước kiểm tra. Nếu tình huống còn mơ hồ,
        hãy thu thập thêm bối cảnh từ người lái trước khi thêm luật vào KG.
      </p>
    </section>
  );
}
