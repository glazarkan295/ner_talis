import React from "react";

// Переиспользуемая подсказка у поля (ТЗ 11 §5.4): «ⓘ» с пояснением.
// Нативный tooltip (title) — доступно, без состояния и без риска вёрстки.
export function HintTip({ text }) {
  if (!text) return null;
  return (
    <span className="nt-hint-tip" role="img" aria-label="Подсказка" title={text}>ⓘ</span>
  );
}

export const HINT_TIP_CSS = `
.nt-hint-tip{display:inline-block;margin-left:6px;cursor:help;color:var(--gold,#b8860b);opacity:.7;font-size:12px}
.nt-hint-tip:hover{opacity:1}
`;
