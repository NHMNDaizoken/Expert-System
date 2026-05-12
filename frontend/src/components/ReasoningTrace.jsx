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

  return (
    <section className="trace">
      <h2>Vết suy luận</h2>
      <div className="trace-grid">
        {sections.map(([key, label]) => (
          <details key={key}>
            <summary>{label}</summary>
            <pre>{JSON.stringify(trace[key] ?? null, null, 2)}</pre>
          </details>
        ))}
      </div>
    </section>
  );
}
