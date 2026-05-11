export default function ConfidenceBadge({ label = "Uncertain", cf = 0 }) {
  const score = Number(cf);
  const tone =
    score >= 0.8 ? "high" : score >= 0.6 ? "good" : score >= 0.5 ? "mid" : "low";

  return (
    <span className={`confidence ${tone}`}>
      {label} · {score.toFixed(2)}
    </span>
  );
}
