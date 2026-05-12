function normalizeLogs(logs) {
  if (!logs) return [];
  if (Array.isArray(logs)) return logs.map(String).filter(Boolean);
  if (typeof logs === "string") return [logs];
  if (typeof logs === "object") {
    return Object.entries(logs)
      .map(([key, value]) => `${key}: ${typeof value === "string" ? value : JSON.stringify(value)}`)
      .filter(Boolean);
  }
  return [String(logs)];
}

export default function DebugLogsPanel({ logs, defaultOpen = false }) {
  const normalized = normalizeLogs(logs);

  if (!normalized.length) {
    return null;
  }

  return (
    <details className="technical-panel debug-logs-panel" open={defaultOpen}>
      <summary>Nhật ký gỡ lỗi</summary>
      <ul>
        {normalized.map((line, index) => (
          <li key={`${line}-${index}`}>{line}</li>
        ))}
      </ul>
    </details>
  );
}
