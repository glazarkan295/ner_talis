import React, { useEffect, useRef, useState } from "react";

// Reusable confirmation modal for V2. Every mutating/dangerous action funnels
// through here so the operator must read what will happen and (for dangerous
// actions) type a reason that is stored in the audit trail.
export function ConfirmModal({
  open,
  title,
  body,
  confirmLabel = "Подтвердить",
  cancelLabel = "Отмена",
  dangerous = false,
  requireReason = false,
  requireConfirmText = "",
  onConfirm,
  onCancel,
}) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [confirmText, setConfirmText] = useState("");
  const reasonRef = useRef(null);

  useEffect(() => {
    if (open) {
      setReason("");
      setBusy(false);
      setError("");
      setConfirmText("");
      requestAnimationFrame(() => reasonRef.current?.focus());
    }
  }, [open]);

  if (!open) return null;

  const needReason = requireReason || dangerous;
  const canConfirm = !busy
    && (!needReason || reason.trim().length >= 3)
    && (!requireConfirmText || confirmText === requireConfirmText);

  async function confirm() {
    if (!canConfirm) return;
    setBusy(true);
    setError("");
    try {
      await onConfirm?.(reason.trim());
    } catch (e) {
      setError(e?.message || "Действие не выполнено.");
      setBusy(false);
    }
  }

  return (
    <div className="ntv2-modal-overlay" role="dialog" aria-modal="true">
      <div className={`ntv2-modal${dangerous ? " ntv2-modal-danger" : ""}`}>
        <h3>{title}</h3>
        {dangerous ? <p className="ntv2-modal-danger-tag">⚠️ Опасное действие</p> : null}
        <div className="ntv2-modal-body">{body}</div>
        {needReason ? (
          <label className="ntv2-field">
            <span>Причина {dangerous ? "(обязательно)" : ""}</span>
            <textarea
              ref={reasonRef}
              rows={2}
              value={reason}
              placeholder="Зачем выполняется действие — попадёт в журнал аудита"
              onChange={(e) => setReason(e.target.value)}
            />
          </label>
        ) : null}
        {requireConfirmText ? (
          <label className="ntv2-field">
            <span>Введите точный ID: <b className="ntv2-mono">{requireConfirmText}</b></span>
            <input
              value={confirmText}
              autoComplete="off"
              onChange={(e) => setConfirmText(e.target.value)}
            />
          </label>
        ) : null}
        {error ? <div className="ntv2-error">{error}</div> : null}
        <div className="ntv2-modal-actions">
          <button type="button" className="ntv2-btn" onClick={onCancel} disabled={busy}>
            {cancelLabel}
          </button>
          <button
            type="button"
            className={`ntv2-btn ${dangerous ? "ntv2-btn-danger" : "ntv2-btn-primary"}`}
            onClick={confirm}
            disabled={!canConfirm}
          >
            {busy ? "Выполняется…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
