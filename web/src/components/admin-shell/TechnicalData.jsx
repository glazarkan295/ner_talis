import React from "react";

// Raw JSON is never shown inline in V2 — it lives behind this collapse so the
// operational surface stays human-readable. Used for before/after diffs,
// payloads, anything that used to be a bare <pre>{JSON}</pre>.
export function TechnicalData({ label = "Технические данные", value }) {
  if (value === null || value === undefined) return null;
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  if (!text || text === "{}" || text === "null") return null;
  return (
    <details className="ntv2-tech">
      <summary>{label}</summary>
      <pre className="ntv2-pre">{text}</pre>
    </details>
  );
}
