const sections = [
  ["normalization", "Normalization"],
  ["hypothesis_generation", "Hypotheses"],
  ["question_selection", "Question Selection"],
  ["backward_chaining", "Backward Chaining"],
  ["cf_calculation_steps", "CF Steps"],
  ["final_decision", "Final Decision"],
  ["ranking", "Ranking"],
];

export default function ReasoningTrace({ trace }) {
  if (!trace) {
    return null;
  }

  return (
    <section className="trace">
      <h2>Reasoning Trace</h2>
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
