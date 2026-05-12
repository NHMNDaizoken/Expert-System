import { useState } from "react";
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
  if (!progress) {
    return { label: "Bước 1", percent: 15 };
  }
  const current = Number(String(progress).split("/")[0]);
  const step = Number.isFinite(current) && current > 0 ? current : 1;
  const percent = Math.min(90, 15 + (step - 1) * 15);
  return { label: `Bước ${step}`, percent };
}

function friendlyLabel(value) {
  if (!value) return "";
  const raw = String(value);
  if (/diagnostic procedure/i.test(raw)) {
    return raw
      .replace(/diagnostic procedure/i, "Quy trình kiểm tra")
      .replace(/step/i, "bước");
  }
  if (raw === "procedure_tree") return "Quy trình kiểm tra";
  if (raw === "information_gain") return "Hỏi thêm triệu chứng";
  const normalized = raw.replace(/^SYM_/i, "").replace(/_/g, " ").toLowerCase();
  return SYSTEM_LABELS[normalized] || normalized;
}

function breadcrumbParts(data) {
  const system =
    data?.detected_systems?.[0] ||
    data?.reasoning_trace?.normalization?.detected_systems?.[0];
  const primarySymptom = data?.primary_symptom;
  const step = data?.step_context || data?.next_question?.mode;
  return [friendlyLabel(system), friendlyLabel(primarySymptom), friendlyLabel(step)].filter(
    Boolean
  );
}

function questionText(data) {
  const question = data?.next_question?.question || data?.next_question;
  if (!question) return "Bạn có thấy dấu hiệu này không?";
  if (data?.next_question?.mode === "information_gain" && data?.next_question?.label) {
    return `Bạn có thấy thêm dấu hiệu: ${data.next_question.label.toLowerCase()} không?`;
  }
  return question;
}

function questionType(data) {
  const type = data?.next_question?.type;
  if (type) return type;
  if (typeof data?.next_question === "string") return "yes_no";
  if (data?.next_question && typeof data.next_question === "object" && !data.next_question.type) {
    return "yes_no";
  }
  return "yes_no";
}

function extractChoices(data) {
  const q = data?.next_question;
  const raw = q?.choices || q?.options || q?.answers;
  if (!raw) return [];
  if (Array.isArray(raw)) {
    return raw
      .map((item) => {
        if (typeof item === "string") return { value: item, label: item };
        if (item && typeof item === "object") {
          const value = item.value ?? item.id ?? item.key ?? item.label;
          const label = item.label ?? item.text ?? item.name ?? String(value ?? "");
          if (value == null || label == null) return null;
          return { value: String(value), label: String(label) };
        }
        return null;
      })
      .filter(Boolean);
  }
  if (typeof raw === "object") {
    return Object.entries(raw).map(([value, label]) => ({
      value: String(value),
      label: String(label),
    }));
  }
  return [];
}

function whyAsking(data) {
  const q = data?.next_question;
  const why = q?.why || q?.rationale || q?.explain || q?.reason;
  if (!why) return null;
  if (Array.isArray(why)) return why.map(String).filter(Boolean);
  if (typeof why === "string") return [why];
  return null;
}

export default function QuestioningScreen({ data, onAnswer, loading }) {
  const progress = parseProgress(data?.step_progress);
  const crumbs = breadcrumbParts(data);
  const type = questionType(data);
  const choices = extractChoices(data);
  const why = whyAsking(data);
  const unit = data?.next_question?.unit || data?.next_question?.units;
  const min = data?.next_question?.min;
  const max = data?.next_question?.max;

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

        {why?.length ? (
          <div className="question-why">
            <div className="eyebrow">Vì sao cần hỏi?</div>
            <ul>
              {why.map((line, idx) => (
                <li key={`${line}-${idx}`}>{line}</li>
              ))}
            </ul>
          </div>
        ) : null}

        {type === "yes_no" && (
          <>
            <div className="answer-buttons">
              <button
                className="answer-btn btn-yes"
                disabled={loading}
                onClick={() => onAnswer(true)}
              >
                <CircleCheckBig size={20} />
                Có
              </button>
              <button
                className="answer-btn btn-no"
                disabled={loading}
                onClick={() => onAnswer(false)}
              >
                <CircleX size={20} />
                Không
              </button>
            </div>

            <button className="btn-skip" disabled={loading} onClick={() => onAnswer(null)}>
              <CircleHelp
                size={16}
                style={{ display: "inline", verticalAlign: "text-bottom", marginRight: "4px" }}
              />
              Không rõ / Bỏ qua câu này
            </button>
          </>
        )}

        {type === "multiple_choice" && (
          <MultipleChoiceAnswer
            disabled={loading}
            choices={choices}
            onSubmit={(value) => onAnswer(value)}
            onSkip={() => onAnswer(null)}
          />
        )}

        {type === "free_text" && (
          <FreeTextAnswer
            disabled={loading}
            onSubmit={(value) => onAnswer(value)}
            onSkip={() => onAnswer(null)}
          />
        )}

        {(type === "number" || type === "measurement") && (
          <NumberAnswer
            disabled={loading}
            unit={unit}
            min={min}
            max={max}
            onSubmit={(value) => onAnswer(value)}
            onSkip={() => onAnswer(null)}
          />
        )}
      </div>
    </section>
  );
}

function MultipleChoiceAnswer({ choices, onSubmit, onSkip, disabled }) {
  const safeChoices = choices?.length
    ? choices
    : [
        { value: "not_sure", label: "Không chắc" },
        { value: "unknown", label: "Không rõ" },
      ];
  return (
    <div className="answer-form">
      <div className="choice-grid" role="group" aria-label="Chọn đáp án">
        {safeChoices.map((c) => (
          <button
            key={c.value}
            className="answer-btn btn-choice"
            type="button"
            disabled={disabled}
            onClick={() => onSubmit(c.value)}
          >
            {c.label}
          </button>
        ))}
      </div>
      <button className="btn-skip" disabled={disabled} onClick={onSkip}>
        <CircleHelp
          size={16}
          style={{ display: "inline", verticalAlign: "text-bottom", marginRight: "4px" }}
        />
        Bỏ qua câu này
      </button>
    </div>
  );
}

function FreeTextAnswer({ onSubmit, onSkip, disabled }) {
  return (
    <TextSubmitAnswer
      placeholder="Nhập thêm thông tin (ví dụ: khi nào xảy ra, tần suất, điều kiện...)"
      disabled={disabled}
      onSubmit={onSubmit}
      onSkip={onSkip}
    />
  );
}

function NumberAnswer({ onSubmit, onSkip, disabled, unit, min, max }) {
  return (
    <TextSubmitAnswer
      inputType="number"
      placeholder={unit ? `Nhập giá trị (${unit})` : "Nhập giá trị"}
      disabled={disabled}
      onSubmit={(value) => {
        if (value == null || value === "") {
          onSubmit(null);
          return;
        }
        const parsed = Number(value);
        onSubmit(Number.isFinite(parsed) ? parsed : value);
      }}
      onSkip={onSkip}
      min={min}
      max={max}
      unit={unit}
    />
  );
}

function TextSubmitAnswer({
  inputType = "text",
  placeholder,
  disabled,
  onSubmit,
  onSkip,
  min,
  max,
  unit,
}) {
  const [value, setValue] = useState("");

  return (
    <form
      className="answer-form"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(value?.trim?.() ?? value);
      }}
    >
      <div className="input-row">
        <input
          className="answer-input"
          type={inputType}
          placeholder={placeholder}
          value={value}
          disabled={disabled}
          min={inputType === "number" ? min : undefined}
          max={inputType === "number" ? max : undefined}
          onChange={(e) => setValue(e.target.value)}
        />
        {unit ? <span className="input-unit">{String(unit)}</span> : null}
      </div>
      <div className="answer-buttons">
        <button className="answer-btn btn-yes" type="submit" disabled={disabled}>
          <CircleCheckBig size={20} />
          Gửi
        </button>
        <button className="answer-btn btn-no" type="button" disabled={disabled} onClick={onSkip}>
          <CircleHelp size={20} />
          Bỏ qua
        </button>
      </div>
    </form>
  );
}
