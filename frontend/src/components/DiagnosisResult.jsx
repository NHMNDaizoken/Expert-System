import { TriangleAlert, Wrench, RefreshCw, CircleCheck, Send } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import DebugLogsPanel from "./DebugLogsPanel.jsx";
import TechnicalPayloadPanel from "./TechnicalPayloadPanel.jsx";

function scoreOf(result) {
  return Number(result?.confidence ?? result?.score ?? result?.final_cf ?? 0);
}

function procedureSteps(text = "") {
  return text
    .split(/\n|\./)
    .map((step) => step.trim())
    .filter(Boolean);
}

export default function DiagnosisResult({
  data,
  results: legacyResults,
  onRestart = () => {},
}) {
  const normalized = data || {};
  const results = normalized?.results || legacyResults || [];
  const resolution = normalized?.resolution || results[0]?.resolution || {};
  const mode = normalized.mode || normalized._raw?.source || "kg";
  const isKgSource =
    mode === "kg" ||
    mode === "knowledge_graph" ||
    mode === "staging_files_kg" ||
    normalized._raw?.source === "knowledge_graph" ||
    normalized._raw?.source === "staging_files_kg";
  const isReviewNeeded = normalized.expert_review?.candidate_ready || normalized._raw?.status === "review_needed";
  const navigate = useNavigate();

  if (isReviewNeeded) {
    const question = normalized?.current_question?.question || normalized._raw?.next_question?.question || "Vui lòng cung cấp thêm thông tin để chuyên gia kiểm duyệt.";
    const debug = normalized?.debug || { notes: normalized?._raw?.notes || normalized?._raw?.fallback_notes || [] };

    return (
      <section className="result-section">
        <div className="primary-result-card review-needed-card glass-panel">
          <span className="result-badge">Cần thêm thông tin</span>
          <h2>Triệu chứng chưa có đủ tri thức đã xác minh</h2>
          <p className="muted">{data?.explanation_summary || "Hệ thống chưa thể đưa ra chẩn đoán cuối cho triệu chứng này."}</p>
          <div className="repair-section">
            <h3>
              <TriangleAlert size={18} /> Cần hỏi thêm
            </h3>
            <p>{question}</p>
          </div>
          <div className="action-row action-row-between">
            <Link className="secondary-btn" to="/review">
              Mở hàng chờ kiểm duyệt
            </Link>
            <button className="secondary-btn" onClick={onRestart}>
              <RefreshCw size={18} />
              Chẩn đoán lại
            </button>
          </div>
        </div>
        <TechnicalPayloadPanel title="Chi tiết kỹ thuật" payload={data?.debug || data} />
        <DebugLogsPanel logs={debug} />
      </section>
    );
  }

  if (!results.length) {
    return (
      <div className="result-section glass-panel" style={{ padding: "32px", textAlign: "center" }}>
        <p className="muted">Chưa tìm thấy lỗi phù hợp. Vui lòng thử cung cấp thêm triệu chứng.</p>
        <button className="primary-btn" onClick={onRestart} style={{ marginTop: "16px" }}>
          <RefreshCw size={18} /> Chẩn đoán lại
        </button>
      </div>
    );
  }

  const [top, ...others] = results.slice(0, 3);
  const confidence = Math.round(scoreOf(top) * 100);

  return (
    <section className="result-section">
      <div className="primary-result-card glass-panel">
        <span className="result-badge">
          {isKgSource ? "Từ cây tri thức" : mode === "llm_fallback" ? "LLM đề xuất - cần chuyên gia duyệt" : "Kết hợp KG + LLM"}
        </span>
        <h2>{top.fault_label_vi || top.fault_label || top.fault_name}</h2>

        <div className="confidence-row">
          <div className="confidence-track">
            <div className="confidence-fill" style={{ width: `${confidence}%` }} />
          </div>
          <div className="confidence-text">Độ tin cậy: {confidence}%</div>
        </div>

        {normalized?.repair_plan ? (
          <>
            {data.repair_plan.inspect_or_replace && data.repair_plan.inspect_or_replace.length > 0 && (
              <div className="repair-section">
                <h3>
                  <Wrench size={18} /> Linh kiện cần kiểm tra/thay thế
                </h3>
                <ul>
                  {data.repair_plan.inspect_or_replace.map((part) => (
                    <li key={part}>{part}</li>
                  ))}
                </ul>
              </div>
            )}

            {data.repair_plan.checks && data.repair_plan.checks.length > 0 && (
              <div className="repair-section">
                <h3>
                  <CircleCheck size={18} /> Kế hoạch kiểm tra
                </h3>
                <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                  {data.repair_plan.checks.map((check, idx) => (
                    <div key={idx} style={{ 
                      padding: "12px 16px", 
                      borderRadius: "8px", 
                      backgroundColor: "rgba(255, 255, 255, 0.05)",
                      border: "1px solid rgba(255, 255, 255, 0.1)"
                    }}>
                      <h4 style={{ margin: "0 0 8px 0", color: "var(--text-primary)", fontSize: "1rem" }}>
                        {check.action}
                      </h4>
                      {check.possible_result && check.possible_result !== "Không xác định" && (
                        <div style={{ display: "flex", flexDirection: "column", gap: "6px", fontSize: "0.9rem" }}>
                          <div style={{ color: "var(--warning-light)" }}>
                            <strong>Trạng thái:</strong> {check.possible_result}
                          </div>
                          <div style={{ color: "var(--text-secondary)" }}>
                            <strong>Ý nghĩa:</strong> {check.meaning}
                          </div>
                          <div style={{ color: "var(--primary-light)" }}>
                            <strong>Xử lý:</strong> {check.recommended_fix}
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        ) : (
          <>
            {resolution.parts && resolution.parts.length > 0 && (
              <div className="repair-section">
                <h3>
                  <Wrench size={18} /> Linh kiện cần kiểm tra/thay thế
                </h3>
                <ul>
                  {resolution.parts.map((part) => (
                    <li key={part}>{part}</li>
                  ))}
                </ul>
              </div>
            )}

            {resolution.procedure && (
              <div className="repair-section">
                <h3>
                  <CircleCheck size={18} /> Các bước kiểm tra & Sửa chữa
                </h3>
                <ol>
                  {procedureSteps(resolution.procedure).map((step) => (
                    <li key={step}>{step}</li>
                  ))}
                </ol>
              </div>
            )}
          </>
        )}
      </div>

      {others.length > 0 && (
        <div style={{ marginTop: "16px" }}>
          <h3
            style={{
              color: "var(--text-secondary)",
              fontSize: "1rem",
              marginBottom: "12px",
            }}
          >
            Các nguyên nhân khả nghi khác
          </h3>
          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            {others.map((result) => (
              <div
                className="secondary-result-card"
                key={result.fault_id || result.fault_name}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                  <TriangleAlert size={18} color="var(--warning-base)" />
                  <h3>{result.fault_label_vi || result.fault_label || result.fault_name}</h3>
                </div>
                <span className="secondary-result-score">
                  {Math.round(scoreOf(result) * 100)}%
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <button
        className="secondary-btn"
        onClick={onRestart}
        style={{
          alignSelf: "center",
          marginTop: "24px",
          minWidth: "200px",
          justifyContent: "center",
        }}
      >
        <RefreshCw size={18} />
        Chẩn đoán lỗi khác
      </button>
      {normalized?.expert_review?.candidate_ready && (
        <div style={{ display: "flex", justifyContent: "center", marginTop: "12px" }}>
          <button
            className="primary-btn"
            onClick={() => {
              // Navigate to review page with payload draft
              try {
                const payload = normalized.expert_review.payload || { root_symptom: normalized.root_symptom, results };
                navigate("/review", { state: { draftSuggestion: { user_input: normalized.root_symptom?.label, llm_output: payload } } });
              } catch (e) {
                // fallback: open review page
                navigate("/review");
              }
            }}
          >
            <Send size={18} />
            Gửi chuyên gia duyệt
          </button>
        </div>
      )}
    </section>
  );
}
