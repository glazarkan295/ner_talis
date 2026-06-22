import React, { useMemo, useState } from "react";
import { EmojiTextarea } from "./EmojiField.jsx";
import { ImageUploadField } from "./ImageUploadField.jsx";

// Конструктор вывода сообщения игроку (дополнение к ТЗ): изображение + формат
// «одним/несколькими сообщениями» + цепочка блоков + предпросмотр Telegram/VK.
// value — объект { format, image, text, buttons[], blocks[] }; onChange(obj).
// Переиспользуемый: подключается в любой конструктор с текстом/кнопками.

const TG_TEXT = 4096;
const TG_CAPTION = 1024;

export function emptyMessage() {
  return { format: "single", image: "", text: "", buttons: [], blocks: [] };
}

function partWarnings(part) {
  const w = [];
  const text = String(part.text || "");
  const image = String(part.image || "");
  if (!text && !image) w.push("пусто — нужен текст или изображение");
  if (image && /^(https?:)?\/\//i.test(image)) w.push("изображение должно быть файлом, а не ссылкой");
  if (text && image && text.length > TG_CAPTION) w.push(`подпись к фото в Telegram обрежется (> ${TG_CAPTION})`);
  if (text && text.length > TG_TEXT) w.push(`текст не влезет в одно сообщение Telegram (> ${TG_TEXT})`);
  return w;
}

function PreviewCard({ platform, part, buttons }) {
  const w = partWarnings(part);
  return (
    <div className={`ntv2-msg-preview ntv2-msg-${platform}`}>
      <div className="ntv2-msg-platform">{platform === "tg" ? "Telegram" : "VK"}</div>
      {part.image ? <div className="ntv2-msg-image"><img src={part.image} alt="" /></div> : null}
      {part.text ? <div className="ntv2-msg-text">{part.text}</div> : <div className="ntv2-hint">— без текста —</div>}
      {(buttons || []).filter(Boolean).length ? (
        <div className="ntv2-msg-buttons">
          {(buttons || []).filter(Boolean).map((b, i) => <span key={i} className="ntv2-msg-btn">{b}</span>)}
        </div>
      ) : null}
      {w.length ? <div className="ntv2-msg-warn">{w.map((x, i) => <div key={i}>⚠️ {x}</div>)}</div> : null}
    </div>
  );
}

function Preview({ value }) {
  const parts = value.format === "multiple"
    ? [...(value.blocks || [])].sort((a, b) => (Number(a.order) || 0) - (Number(b.order) || 0))
    : [{ image: value.image, text: value.text, buttons: value.buttons }];
  return (
    <div className="ntv2-panel">
      <h4 className="ntv2-subhead">Предпросмотр (Telegram / VK)</h4>
      {parts.map((p, i) => (
        <div key={i} className="ntv2-msg-row">
          {value.format === "multiple" ? <div className="ntv2-hint">Сообщение {i + 1}</div> : null}
          <div className="ntv2-msg-grid">
            <PreviewCard platform="tg" part={p} buttons={p.buttons} />
            <PreviewCard platform="vk" part={p} buttons={p.buttons} />
          </div>
        </div>
      ))}
    </div>
  );
}

function ButtonsEditor({ label, value, onChange, disabled }) {
  const list = Array.isArray(value) ? value : [];
  return (
    <div className="ntv2-field">
      <span>{label}</span>
      {list.map((b, i) => (
        <div className="ntv2-form-row" key={i} style={{ gap: 6, alignItems: "center" }}>
          <input value={b} disabled={disabled} onChange={(e) => onChange(list.map((x, idx) => (idx === i ? e.target.value : x)))} />
          {!disabled ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => onChange(list.filter((_, idx) => idx !== i))}>✕</button> : null}
        </div>
      ))}
      {!disabled ? <button type="button" className="ntv2-btn" onClick={() => onChange([...list, ""])}>＋ Кнопка</button> : null}
    </div>
  );
}

export function MessageComposer({ label, value, onChange, disabled, uploadKey, category = "messages" }) {
  const [preview, setPreview] = useState(false);
  const msg = useMemo(() => ({ ...emptyMessage(), ...(value || {}) }), [value]);
  const set = (k, v) => onChange({ ...msg, [k]: v });

  const setBlock = (i, k, v) => set("blocks", (msg.blocks || []).map((b, idx) => (idx === i ? { ...b, [k]: v } : b)));
  const addBlock = () => set("blocks", [...(msg.blocks || []), { order: (msg.blocks || []).length + 1, image: "", text: "", buttons: [], delay: 0, visible: true, condition: "" }]);
  const delBlock = (i) => set("blocks", (msg.blocks || []).filter((_, idx) => idx !== i));

  return (
    <div className="ntv2-panel">
      <div className="ntv2-card-head" style={{ marginBottom: 6 }}>
        <h4 className="ntv2-subhead" style={{ margin: 0 }}>{label || "Сообщение игроку"}</h4>
        <button type="button" className="ntv2-btn" onClick={() => setPreview((p) => !p)}>{preview ? "Скрыть предпросмотр" : "Предпросмотр TG/VK"}</button>
      </div>

      <label className="ntv2-field"><span>Как отправлять</span>
        <select value={msg.format} disabled={disabled} onChange={(e) => set("format", e.target.value)}>
          <option value="single">Одним сообщением</option>
          <option value="multiple">Несколькими сообщениями</option>
        </select>
      </label>

      {msg.format === "single" ? (
        <>
          <ImageUploadField label="Изображение сообщения" value={msg.image} category={category} uploadKey={`${uploadKey || "msg"}_img`} disabled={disabled} onChange={(v) => set("image", v)} />
          <label className="ntv2-field"><span>Текст</span><EmojiTextarea rows={3} value={msg.text} disabled={disabled} onChange={(v) => set("text", v)} /></label>
          <ButtonsEditor label="Кнопки под сообщением" value={msg.buttons} disabled={disabled} onChange={(v) => set("buttons", v)} />
        </>
      ) : (
        <>
          {(msg.blocks || []).map((b, i) => (
            <div className="ntv2-panel" key={i}>
              <div className="ntv2-card-head" style={{ marginBottom: 4 }}>
                <b>Сообщение {i + 1}</b>
                {!disabled ? <button type="button" className="ntv2-btn ntv2-btn-danger" onClick={() => delBlock(i)}>Удалить блок</button> : null}
              </div>
              <div className="ntv2-form-row">
                <label className="ntv2-field"><span>Порядок</span><input type="number" value={b.order ?? ""} disabled={disabled} onChange={(e) => setBlock(i, "order", e.target.value)} /></label>
                <label className="ntv2-field"><span>Задержка (сек)</span><input type="number" value={b.delay ?? ""} disabled={disabled} onChange={(e) => setBlock(i, "delay", e.target.value)} /></label>
                <label className="ntv2-check"><input type="checkbox" checked={b.visible !== false} disabled={disabled} onChange={(e) => setBlock(i, "visible", e.target.checked)} /> Показывать</label>
              </div>
              <ImageUploadField label="Изображение" value={b.image} category={category} uploadKey={`${uploadKey || "msg"}_b${i}`} disabled={disabled} onChange={(v) => setBlock(i, "image", v)} />
              <label className="ntv2-field"><span>Текст</span><EmojiTextarea rows={2} value={b.text} disabled={disabled} onChange={(v) => setBlock(i, "text", v)} /></label>
              <ButtonsEditor label="Кнопки" value={b.buttons} disabled={disabled} onChange={(v) => setBlock(i, "buttons", v)} />
              <label className="ntv2-field"><span>Условие отправки</span><input value={b.condition || ""} disabled={disabled} onChange={(e) => setBlock(i, "condition", e.target.value)} /></label>
            </div>
          ))}
          {!disabled ? <button type="button" className="ntv2-btn" onClick={addBlock}>＋ Добавить сообщение</button> : null}
        </>
      )}

      {preview ? <Preview value={msg} /> : null}
    </div>
  );
}
