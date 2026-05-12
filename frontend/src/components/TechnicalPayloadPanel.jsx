export default function TechnicalPayloadPanel({
  title = "Chi tiết kỹ thuật",
  payload,
  editable = false,
  value = "",
  onChange,
  rows = 14,
  defaultOpen = false,
}) {
  const renderedValue = editable ? value : JSON.stringify(payload ?? {}, null, 2);

  return (
    <details className="technical-panel" defaultOpen={defaultOpen}>
      <summary>{title}</summary>
      {editable ? (
        <textarea
          className="json-editor"
          value={renderedValue}
          onChange={(event) => onChange?.(event.target.value)}
          rows={rows}
          spellCheck={false}
        />
      ) : (
        <pre>{renderedValue}</pre>
      )}
    </details>
  );
}
