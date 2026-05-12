const sections = [
  ["normalization", "Chuẩn hóa triệu chứng"],
  ["hypothesis_generation", "Giả thuyết lỗi"],
  ["question_selection", "Chọn câu hỏi"],
  ["backward_chaining", "Suy luận lùi"],
  ["cf_calculation_steps", "Các bước tính CF"],
  ["final_decision", "Kết luận cuối"],
  ["ranking", "Xếp hạng"],
];

export default function ReasoningTrace({ trace }) {
  if (!trace) {
    return null;
  }

  const summary = buildSummary(trace);

  return (
    <section className="trace">
      <h2>Vết suy luận</h2>
      {summary?.length ? (
        <div className="trace-card-grid">
          {summary.map((item, idx) => (
            <article className="trace-card" key={`${item.title}-${idx}`}>
              <span className="eyebrow">{item.title}</span>
              <p>{item.value}</p>
            </article>
          ))}
        </div>
      ) : null}

      {confidenceChanges(trace).length > 0 && (
        <div className="trace-summary">
          <div className="eyebrow">Thay đổi độ tin cậy</div>
          <ul>
            {confidenceChanges(trace).map((line, idx) => (
              <li key={`${line}-${idx}`}>{line}</li>
            ))}
          </ul>
        </div>
      )}

      {whyAskMore(trace) && (
        <div className="trace-summary">
          <div className="eyebrow">Vì sao cần hỏi thêm</div>
          <p>{whyAskMore(trace)}</p>
        </div>
      )}

      <details className="trace-technical">
        <summary>Gỡ lỗi (raw)</summary>
        <div className="trace-grid">
          {sections.map(([key, label]) => (
            <details key={key}>
              <summary>{label}</summary>
              <pre>{JSON.stringify(trace[key] ?? null, null, 2)}</pre>
            </details>
          ))}
        </div>
      </details>
    </section>
  );
}

function buildSummary(trace) {
  if (Array.isArray(trace)) {
    return trace
      .map(String)
      .filter(Boolean)
      .slice(0, 4)
      .map((value, index) => ({ title: `Bước ${index + 1}`, value }));
  }

  const summary = [];
  const detected =
    trace?.normalization?.detected_systems?.[0] ||
    trace?.normalization?.detected_system ||
    trace?.detected_systems?.[0];
  if (detected) {
    summary.push({ title: "Hệ thống có thể", value: String(detected) });
  }

  const primary = trace?.normalization?.primary_symptom || trace?.primary_symptom;
  if (primary) {
    summary.push({ title: "Triệu chứng khớp", value: String(primary) });
  }

  const ranked =
    trace?.ranking?.top_faults ||
    trace?.ranking?.ranked_faults ||
    trace?.final_decision?.top_faults ||
    trace?.final_decision?.ranked_faults;
  if (Array.isArray(ranked) && ranked.length) {
    const top = ranked
      .slice(0, 3)
      .map((f) => {
        if (typeof f === "string") return f;
        if (f && typeof f === "object") {
          const name = f.fault || f.label || f.name || f.id;
          const cf = f.cf ?? f.confidence ?? f.score;
          if (name && cf != null) return `${name} (${Math.round(Number(cf) * 100)}%)`;
          return name ?? null;
        }
        return null;
      })
      .filter(Boolean);
    if (top.length) {
      summary.push({ title: "Lỗi đã xếp hạng", value: top.join(", ") });
    }
  }

  const questions = trace?.question_selection?.asked || trace?.question_selection?.questions;
  if (Array.isArray(questions) && questions.length) {
    summary.push({
      title: "Câu hỏi đã hỏi",
      value: `${questions.length} câu để phân biệt nguyên nhân.`,
    });
  }

  return summary.slice(0, 12);
}

function confidenceChanges(trace) {
  const steps = trace?.cf_calculation_steps || trace?.confidence_changes || [];
  if (!Array.isArray(steps)) return [];
  return steps
    .map((step) => {
      if (typeof step === "string") return step;
      const name = step.fault || step.fault_id || step.name || "Ứng viên";
      const before = step.before ?? step.previous_cf;
      const after = step.after ?? step.final_cf ?? step.cf;
      if (after == null) return null;
      if (before == null) return `${name}: ${Math.round(Number(after) * 100)}%`;
      return `${name}: ${Math.round(Number(before) * 100)}% → ${Math.round(Number(after) * 100)}%`;
    })
    .filter(Boolean)
    .slice(0, 6);
}

function whyAskMore(trace) {
  const selected = trace?.question_selection?.selected || trace?.question_selection?.next_question;
  if (!selected) return null;
  if (typeof selected === "string") return selected;
  return (
    selected.why ||
    selected.rationale ||
    selected.reason ||
    "Câu hỏi này giúp phân biệt các lỗi có triệu chứng gần giống nhau trước khi kết luận."
  );
}
