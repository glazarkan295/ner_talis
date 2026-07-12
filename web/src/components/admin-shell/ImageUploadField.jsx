import React, { useRef, useState } from "react";
import { fileToBase64, uploadImage } from "../../api/adminUploadsApi.js";

// Поле изображения: загрузка ФАЙЛОМ (ТЗ доп.§2), а не внешней ссылкой.
// value — локальный путь /assets/admin_uploads/...; onChange(newPath).
// category — папка (items/items_models/mobs/npc/...), uploadKey — id объекта.
// Поле прямого пути оставлено как запасной вариант для разработчика.
export function ImageUploadField({ label, value, onChange, category, uploadKey, disabled }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [uploadInfo, setUploadInfo] = useState(null);
  const inputRef = useRef(null);

  async function onFile(event) {
    const file = event.target.files && event.target.files[0];
    event.target.value = "";
    if (!file) return;
    if (!uploadKey) { setError("Сначала укажите ID объекта — он используется как имя файла."); return; }
    setBusy(true);
    setError("");
    setUploadInfo(null);
    try {
      const base64 = await fileToBase64(file);
      const res = await uploadImage(category, uploadKey, base64, "загрузка из конструктора");
      if (res?.path) {
        onChange(res.path);
        setUploadInfo(res);
      }
    } catch (e) {
      setError(e?.message || "Не удалось загрузить изображение.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <label className="ntv2-field">
      <span>{label}</span>
      <div className="ntv2-image-field">
        <div className="ntv2-image-preview">
          {value ? <img src={value} alt="" /> : <span className="ntv2-hint">нет</span>}
        </div>
        <div className="ntv2-image-controls">
          {!disabled ? (
            <>
              <button type="button" className="ntv2-btn" disabled={busy} onClick={() => inputRef.current && inputRef.current.click()}>
                {busy ? "Загрузка…" : value ? "Заменить файл" : "Загрузить файл"}
              </button>
              {value ? <button type="button" className="ntv2-btn ntv2-btn-danger" disabled={busy} onClick={() => onChange("")}>Убрать</button> : null}
              <input ref={inputRef} type="file" accept="image/png,image/jpeg,image/webp" style={{ display: "none" }} onChange={onFile} />
            </>
          ) : null}
          <input className="ntv2-mono" placeholder="/assets/... (для разработчика)" value={value || ""} disabled={disabled} onChange={(e) => onChange(e.target.value)} />
        </div>
      </div>
      {error ? <span className="ntv2-error">{error}</span> : null}
      {uploadInfo ? <span className="ntv2-hint">{uploadInfo.width}×{uploadInfo.height} · {(uploadInfo.bytes / 1024).toFixed(1)} КБ · вариантов: {Object.keys(uploadInfo.variants || {}).length}</span> : null}
    </label>
  );
}
