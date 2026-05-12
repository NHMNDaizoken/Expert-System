const LABELS = {
  "Very likely": "Rất có khả năng",
  Likely: "Có khả năng",
  Possible: "Có thể xảy ra",
  Uncertain: "Chưa chắc chắn",
};

export default function ConfidenceBadge({ label = "Chưa chắc chắn", cf = 0 }) {
  const score = Number(cf);
  const tone = score >= 0.8 ? "high" : score >= 0.6 ? "good" : score >= 0.5 ? "mid" : "low";

  return (
    <span className={`confidence ${tone}`}>
      {LABELS[label] || label} · {score.toFixed(2)}
    </span>
  );
}
