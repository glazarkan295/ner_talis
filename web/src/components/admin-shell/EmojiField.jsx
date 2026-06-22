import React, { useEffect, useMemo, useRef, useState } from "react";

// Эмодзи-пикер для текстовых полей админки (ТЗ §5). EmojiInput/EmojiTextarea —
// drop-in замена <input>/<textarea>: value + onChange(nextString) + disabled.
// Вставка идёт в позицию курсора; «Недавние» хранятся в localStorage.

const CATEGORIES = [
  ["Игровые", "⚔️🗡️🛡️🏹🪓🔨🔱💣🧨🪄🔮💎💍👑🏆🥇🎖️🏅🪙💰💵🎁📦🗝️🔑🚪🧭🗺️🏰🏯⛩️🛖⛺🔥💧🌪️🌍⚡❄️☠️💀👻🧙‍♂️🧝‍♀️🧛‍♂️🐉🐺🦅🐍🦂🕷️🍷🧪⚗️🧫🩸❤️‍🔥⭐🌟✨💫"],
  ["Лица", "😀😃😄😁😆😅😂🤣😊😇🙂🙃😉😌😍🥰😘😗😙😚😋😛😝😜🤪🤨🧐🤓😎🥸🤩🥳😏😒😞😔😟😕🙁☹️😣😖😫😩🥺😢😭😤😠😡🤬🤯😳🥵🥶😱😨😰😥😓🤗🤔🤭🤫🤥😶😐😑😬🙄😯😦😧😮😲🥱😴🤤😪😵🤐🥴🤢🤮🤧😷🤒🤕"],
  ["Жесты", "👍👎👌🤌🤏✌️🤞🤟🤘🤙👈👉👆👇☝️✋🤚🖐️🖖👋🤝🙏💪🦾✍️👏🙌👐🤲🫶🤜🤛✊👊"],
  ["Сердца", "❤️🧡💛💚💙💜🖤🤍🤎💔❣️💕💞💓💗💖💘💝💟♥️"],
  ["Природа", "🐶🐱🐭🐹🐰🦊🐻🐼🐨🐯🦁🐮🐷🐸🐵🙈🙉🙊🐔🐧🐦🦄🐝🦋🐌🐞🌳🌲🌴🌵🌿☘️🍀🍁🍂🍃🌸🌺🌻🌹🌷💐🌙⭐🌞🌈⛅🌧️⛈️🌩️🔥💧🌊"],
  ["Еда", "🍎🍊🍋🍌🍉🍇🍓🫐🍒🍑🥭🍍🥥🥝🍅🥕🌽🌶️🥔🍞🧀🍖🍗🥩🍤🍣🍙🍚🍜🍲🥘🍷🍺🍻🥂🍶🧉☕🍵🧪🍯"],
  ["Объекты", "📱💻⌨️🖥️🖨️🕹️💡🔦🕯️📜📃📄📋📌📍✂️🔒🔓🔑🗝️🔨⛏️⚙️🧰🧲🔭🔬⚖️🔗⛓️🧱🪜🧹🧺🧴🛎️🔔📣📢"],
  ["Символы", "✅❌⭕❗❓‼️⚠️🚫💯🔝🆕🆗🔥⭐🌟💫✨💥💢💦💨🕐⏰⌛⏳📈📉➕➖✖️➗♻️🔆🔱⚜️🔰✔️➡️⬅️⬆️⬇️"],
];

const RECENT_KEY = "ntv2_emoji_recent";
const MAX_RECENT = 24;

function loadRecent() {
  try {
    const raw = JSON.parse(window.localStorage.getItem(RECENT_KEY) || "[]");
    return Array.isArray(raw) ? raw.filter((x) => typeof x === "string").slice(0, MAX_RECENT) : [];
  } catch {
    return [];
  }
}
function pushRecent(emoji) {
  try {
    const next = [emoji, ...loadRecent().filter((x) => x !== emoji)].slice(0, MAX_RECENT);
    window.localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  } catch {
    /* localStorage недоступен — недавние просто не сохранятся */
  }
}

// Разбить строку эмодзи на отдельные графемы (учитываем составные с ZWJ/модификаторами).
function splitEmoji(str) {
  try {
    const seg = new Intl.Segmenter("ru", { granularity: "grapheme" });
    return Array.from(seg.segment(str), (s) => s.segment);
  } catch {
    return Array.from(str);
  }
}

const CATEGORY_EMOJI = CATEGORIES.map(([label, str]) => [label, splitEmoji(str)]);

export function EmojiPickerButton({ onPick, disabled }) {
  const [open, setOpen] = useState(false);
  const [recent, setRecent] = useState(loadRecent);
  const wrapRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onDoc = (e) => { if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false); };
    const onEsc = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onEsc);
    return () => { document.removeEventListener("mousedown", onDoc); document.removeEventListener("keydown", onEsc); };
  }, [open]);

  const choose = (emoji) => {
    onPick(emoji);
    pushRecent(emoji);
    setRecent(loadRecent());
  };

  return (
    <span className="ntv2-emoji-wrap" ref={wrapRef}>
      <button type="button" className="ntv2-emoji-btn" disabled={disabled} title="Вставить эмодзи"
        onClick={() => setOpen((o) => !o)}>😊</button>
      {open ? (
        <div className="ntv2-emoji-pop" role="dialog">
          {recent.length ? (
            <div className="ntv2-emoji-group">
              <div className="ntv2-emoji-group-title">Недавние</div>
              <div className="ntv2-emoji-grid">
                {recent.map((e, i) => <button type="button" key={"r" + i} className="ntv2-emoji-cell" onClick={() => choose(e)}>{e}</button>)}
              </div>
            </div>
          ) : null}
          {CATEGORY_EMOJI.map(([label, list]) => (
            <div className="ntv2-emoji-group" key={label}>
              <div className="ntv2-emoji-group-title">{label}</div>
              <div className="ntv2-emoji-grid">
                {list.map((e, i) => <button type="button" key={label + i} className="ntv2-emoji-cell" onClick={() => choose(e)}>{e}</button>)}
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </span>
  );
}

function insertAtCursor(el, value, emoji, onChange) {
  const text = value == null ? "" : String(value);
  if (!el) { onChange(text + emoji); return; }
  const start = typeof el.selectionStart === "number" ? el.selectionStart : text.length;
  const end = typeof el.selectionEnd === "number" ? el.selectionEnd : text.length;
  const next = text.slice(0, start) + emoji + text.slice(end);
  onChange(next);
  requestAnimationFrame(() => {
    try { el.focus(); const pos = start + emoji.length; el.setSelectionRange(pos, pos); } catch { /* поле могло размонтироваться */ }
  });
}

export function EmojiInput({ value, onChange, disabled, className, ...rest }) {
  const ref = useRef(null);
  return (
    <span className="ntv2-emoji-field">
      <input ref={ref} className={className} value={value ?? ""} disabled={disabled}
        onChange={(e) => onChange(e.target.value)} {...rest} />
      <EmojiPickerButton disabled={disabled} onPick={(em) => insertAtCursor(ref.current, value, em, onChange)} />
    </span>
  );
}

export function EmojiTextarea({ value, onChange, disabled, rows, className, ...rest }) {
  const ref = useRef(null);
  return (
    <span className="ntv2-emoji-field ntv2-emoji-field-area">
      <textarea ref={ref} rows={rows} className={className} value={value ?? ""} disabled={disabled}
        onChange={(e) => onChange(e.target.value)} {...rest} />
      <EmojiPickerButton disabled={disabled} onPick={(em) => insertAtCursor(ref.current, value, em, onChange)} />
    </span>
  );
}
