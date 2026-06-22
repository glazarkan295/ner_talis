"""Вывод сообщения игроку (дополнение к ТЗ) — общая модель и валидация.

Описывает, КАК конструкторы отправляют сообщение игроку: одним сообщением
(изображение + текст + кнопки) или несколькими (цепочка блоков по порядку). Слой
данных + валидация переиспользуется во всех конструкторах, где есть текст/кнопки
(город/крепость, события, NPC, штрафы, …). Предпросмотр Telegram/VK — на фронте
(MessageComposer/MessagePreview); здесь — нормализация и предупреждения о лимитах.

Изображение хранится как локальный путь файла проекта (/assets/...), не внешняя
ссылка (ТЗ доп.§2/§7).
"""

from __future__ import annotations

from typing import Any

FORMAT_SINGLE = "single"
FORMAT_MULTIPLE = "multiple"
FORMATS = (FORMAT_SINGLE, FORMAT_MULTIPLE)
FORMAT_LABELS = {FORMAT_SINGLE: "Одним сообщением", FORMAT_MULTIPLE: "Несколькими сообщениями"}

# Лимиты площадок (для предупреждений предпросмотра).
TG_TEXT_LIMIT = 4096       # обычное текстовое сообщение Telegram
TG_CAPTION_LIMIT = 1024    # подпись к фото в Telegram
VK_TEXT_LIMIT = 4096       # сообщение во ВКонтакте


def _str(value: Any) -> str:
    return str(value or "").strip()


def is_image_external(path: Any) -> bool:
    """True, если изображение задано внешней ссылкой (это запрещено ТЗ §2/§7)."""
    text = _str(path).lower()
    return text.startswith("http://") or text.startswith("https://") or text.startswith("//")


def _validate_part(part: dict[str, Any], *, label: str, errors: list[str], warnings: list[str]) -> None:
    text = _str(part.get("text"))
    image = _str(part.get("image"))
    if not text and not image:
        errors.append(f"{label}: пусто — нужен текст или изображение.")
    if image and is_image_external(part.get("image")):
        errors.append(f"{label}: изображение должно быть файлом проекта, а не внешней ссылкой.")
    # Предупреждения о лимитах площадок.
    if text and image and len(text) > TG_CAPTION_LIMIT:
        warnings.append(f"{label}: текст с изображением длиннее {TG_CAPTION_LIMIT} символов — в Telegram подпись к фото обрежется (отправьте отдельным сообщением).")
    if text and len(text) > TG_TEXT_LIMIT:
        warnings.append(f"{label}: текст длиннее {TG_TEXT_LIMIT} символов — Telegram не отправит одним сообщением.")
    elif text and len(text) > VK_TEXT_LIMIT:
        warnings.append(f"{label}: очень длинный текст — может плохо отображаться.")


def validate_message_output(payload: Any) -> dict[str, Any]:
    """Проверка объекта вывода сообщения. Пустой/отсутствующий payload — это ок
    (поле необязательно): {ok: True}. Возвращает {ok, errors, warnings}."""
    errors: list[str] = []
    warnings: list[str] = []
    if not payload:
        return {"ok": True, "errors": errors, "warnings": warnings}
    if not isinstance(payload, dict):
        return {"ok": False, "errors": ["Некорректный формат вывода сообщения."], "warnings": warnings}

    fmt = _str(payload.get("format")) or FORMAT_SINGLE
    if fmt not in FORMATS:
        errors.append(f"Неизвестный формат отправки: {fmt}.")

    if fmt == FORMAT_MULTIPLE:
        blocks = payload.get("blocks")
        if not isinstance(blocks, list) or not blocks:
            errors.append("Для режима «несколькими сообщениями» добавьте хотя бы один блок.")
        else:
            orders = []
            for index, block in enumerate(blocks, start=1):
                if not isinstance(block, dict):
                    errors.append(f"Блок {index}: некорректные данные.")
                    continue
                _validate_part(block, label=f"Блок {index}", errors=errors, warnings=warnings)
                order = block.get("order")
                if order not in (None, ""):
                    try:
                        orders.append(float(order))
                    except (TypeError, ValueError):
                        errors.append(f"Блок {index}: порядок — не число.")
            if len(orders) != len(set(orders)) and orders:
                warnings.append("У некоторых блоков совпадает порядок отправки.")
    else:
        # Одним сообщением — изображение + текст (+ кнопки описываются отдельно).
        if _str(payload.get("text")) or _str(payload.get("image")):
            _validate_part(payload, label="Сообщение", errors=errors, warnings=warnings)

    return {"ok": not errors, "errors": errors, "warnings": warnings}


def meta() -> dict[str, Any]:
    return {
        "formats": [{"value": f, "label": FORMAT_LABELS[f]} for f in FORMATS],
        "limits": {"tgText": TG_TEXT_LIMIT, "tgCaption": TG_CAPTION_LIMIT, "vkText": VK_TEXT_LIMIT},
    }
