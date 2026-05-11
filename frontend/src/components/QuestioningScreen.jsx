import { CircleCheckBig, CircleHelp, CircleX } from "lucide-react";

const SYSTEM_LABELS = {
  engine: "Động cơ",
  brakes: "Phanh",
  brake: "Phanh",
  electrical: "Điện",
  cooling: "Làm mát",
  hvac: "Điều hòa",
  transmission: "Hộp số",
  suspension: "Gầm",
  fuel: "Nhiên liệu",
};

function parseProgress(progress) {
  if (!progress || !progress.includes("/")) {
    return { label: "Bước 1", percent: 15 };
  }
  const [current, total] = progress.split("/").map((part) => Number(part));
  const percent = total > 0 ? Math.min(100, Math.round((current / total) * 100)) : 15;
  return { label: `Bước ${current} / ${total}`, percent };
}

function friendlyLabel(value) {
  if (!value) return "";
  const raw = String(value);
  if (/diagnostic procedure/i.test(raw)) {
    return raw.replace(/diagnostic procedure/i, "Quy trình kiểm tra").replace(/step/i, "bước");
  }
  if (raw === "procedure_tree") return "Quy trình kiểm tra";
  if (raw === "information_gain") return "Hỏi thêm triệu chứng";
  const normalized = raw.replace(/^SYM_/i, "").replace(/_/g, " ").toLowerCase();
  return SYSTEM_LABELS[normalized] || normalized;
}

function breadcrumbParts(data) {
  const system = data?.detected_systems?.[0] || data?.reasoning_trace?.normalization?.detected_systems?.[0];
  const primarySymptom = data?.primary_symptom;
  const step = data?.step_context || data?.next_question?.mode;
  return [friendlyLabel(system), friendlyLabel(primarySymptom), friendlyLabel(step)].filter(Boolean);
}

function questionText(data) {
  const question = data?.next_question?.question || data?.next_question;
  if (!question) return "Bạn có thấy dấu hiệu này không?";
  if (data?.next_question?.mode === "information_gain" && data?.next_question?.label) {
    return `Bạn có thấy thêm dấu hiệu: ${data.next_question.label.toLowerCase()} không?`;
  }
  return question;
}

export default function QuestioningScreen({ data, onAnswer, loading }) {
  const progress = parseProgress(data?.step_progress);
  const crumbs = breadcrumbParts(data);

  return (
    <section className="questioning-section">
      {crumbs.length > 0 && (
        <nav className="diagnosis-breadcrumb" aria-label="Tiến trình chẩn đoán">
          {crumbs.map((crumb, index) => (
            <span key={`${crumb}-${index}`}>{crumb}</span>
          ))}
        </nav>
      )}

      <div className="progress-container">
        <div className="progress-header">
          <span>{progress.label}</span>
          <span>{friendlyLabel(data?.step_context || data?.mode) || "Đang chẩn đoán"}</span>
        </div>
        <div className="progress-track">
          <div className="progress-fill" style={{ width: `${progress.percent}%` }} />
        </div>
      </div>

      <div className="question-card glass-panel">
        <span className="eyebrow">Câu hỏi tiếp theo</span>
        <h2>{questionText(data)}</h2>
        
        <div className="answer-buttons">
          <button className="answer-btn btn-yes" disabled={loading} onClick={() => onAnswer(true)}>
            <CircleCheckBig size={20} />
            Có
          </button>
          <button className="answer-btn btn-no" disabled={loading} onClick={() => onAnswer(false)}>
            <CircleX size={20} />
            Không
          </button>
        </div>
        
        <button className="btn-skip" disabled={loading} onClick={() => onAnswer(null)}>
          <CircleHelp size={16} style={{ display: 'inline', verticalAlign: 'text-bottom', marginRight: '4px' }} />
          Không rõ / Bỏ qua câu này
        </button>
      </div>
    </section>
  );
}
