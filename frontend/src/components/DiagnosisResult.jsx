import { TriangleAlert, Wrench, RefreshCw, CircleCheck } from "lucide-react";

function scoreOf(result) {
  return Number(result?.score ?? result?.final_cf ?? 0);
}

function procedureSteps(text = "") {
  return text
    .split(/\n|\./)
    .map((step) => step.trim())
    .filter(Boolean);
}

export default function DiagnosisResult({ data, results: legacyResults, onRestart = () => {} }) {
  const results = data?.results || legacyResults || [];
  const resolution = data?.resolution || results[0]?.resolution || {};

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
        <span className="result-badge">Khả năng cao nhất</span>
        <h2>{top.fault_label || top.fault_name}</h2>
        
        <div className="confidence-row">
          <div className="confidence-track">
            <div className="confidence-fill" style={{ width: `${confidence}%` }} />
          </div>
          <div className="confidence-text">Độ tin cậy: {confidence}%</div>
        </div>

        {resolution.parts && resolution.parts.length > 0 && (
          <div className="repair-section">
            <h3><Wrench size={18} /> Linh kiện cần kiểm tra/thay thế</h3>
            <ul>
              {resolution.parts.map((part) => (
                <li key={part}>{part}</li>
              ))}
            </ul>
          </div>
        )}

        {resolution.procedure && (
          <div className="repair-section">
            <h3><CircleCheck size={18} /> Các bước kiểm tra & Sửa chữa</h3>
            <ol>
              {procedureSteps(resolution.procedure).map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
          </div>
        )}
      </div>

      {others.length > 0 && (
        <div style={{ marginTop: "16px" }}>
          <h3 style={{ color: "var(--text-secondary)", fontSize: "1rem", marginBottom: "12px" }}>
            Các nguyên nhân khả nghi khác
          </h3>
          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            {others.map((result) => (
              <div className="secondary-result-card" key={result.fault_id || result.fault_name}>
                <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                  <TriangleAlert size={18} color="var(--warning-base)" />
                  <h3>{result.fault_label || result.fault_name}</h3>
                </div>
                <span className="secondary-result-score">{Math.round(scoreOf(result) * 100)}%</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <button className="secondary-btn" onClick={onRestart} style={{ alignSelf: "center", marginTop: "24px", minWidth: "200px", justifyContent: "center" }}>
        <RefreshCw size={18} />
        Chẩn đoán lỗi khác
      </button>
    </section>
  );
}
