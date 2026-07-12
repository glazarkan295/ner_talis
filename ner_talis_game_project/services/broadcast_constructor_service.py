"""Конструктор сохранённых массовых рассылок (ТЗ 2.0 §16–28)."""
from __future__ import annotations
from datetime import datetime,timezone
from typing import Any
from services.admin_entity_store import EntityStore
from services.constructor_status import *  # noqa: F401,F403

BROADCAST_TYPES=("information","technical","event","compensation","reward","promo","item","economy","warning","urgent","test","admin")
SEND_MODES=("single","multiple","image","image_only","text_buttons","reward_message")
FORMATS=("plain","HTML","Markdown","MarkdownV2")
AUDIENCE_MODES=("all","telegram","vk","active","inactive","level","race","location","has_achievement","without_achievement","has_quest","reputation","hidden_reputation","with_fine","without_fine","has_item","without_item","has_effect","without_effect","specific","admins")
REWARD_TYPES=("item","currency","experience","energy","skill_points","stat_points","effect","achievement","promo","access","recipe","skill")
BUTTON_ACTIONS=("open_profile","open_inventory","open_world_event","open_promo","open_location","open_event","open_news","confirm","decline","hide")

_store=EntityStore(env_var="BROADCAST_CONSTRUCTOR_PATH",default_rel="data/broadcast_constructor.json",statuses=STATUSES,transitions=TRANSITIONS,initial_status=STATUS_DRAFT)  # noqa: F405
def store():return _store
def _num(v):
 try:return float(v)
 except (TypeError,ValueError):return None
def _dt(v):
 try:
  value=datetime.fromisoformat(str(v).replace("Z","+00:00")) if v else None
  return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value
 except ValueError:return None
def validate(env:dict[str,Any])->dict[str,Any]:
 d=env.get("data") or {};errors=[];warnings=[]
 if not str(d.get("name") or "").strip():errors.append("Не заполнено название рассылки.")
 if str(d.get("broadcast_type") or "") not in BROADCAST_TYPES:errors.append("Не выбран тип рассылки.")
 if str(d.get("audience_mode") or "") not in AUDIENCE_MODES:errors.append("Не выбрана аудитория.")
 if str(d.get("send_mode") or "single") not in SEND_MODES:errors.append("Неизвестный режим отправки.")
 if str(d.get("format") or "plain") not in FORMATS:errors.append("Неизвестное форматирование.")
 if not str(d.get("text") or "").strip() and str(d.get("send_mode") or "")!="image_only":errors.append("Текст сообщения пуст.")
 if str(d.get("send_mode") or "") in ("image","image_only") and not str(d.get("image") or "").strip():errors.append("Для режима с изображением загрузите изображение.")
 if d.get("schedule_at") and not _dt(d.get("schedule_at")):errors.append("Некорректная дата расписания.")
 if not d.get("send_immediately") and not d.get("schedule_at"):warnings.append("Не выбран немедленный запуск и не задано расписание.")
 if d.get("send_in_batches") and (_num(d.get("batch_size")) or 0)<=0:errors.append("Размер пачки должен быть больше нуля.")
 if (_num(d.get("batch_delay_seconds")) or 0)<0:errors.append("Задержка между пачками не может быть отрицательной.")
 for i,row in enumerate(d.get("rewards") or [],1):
  if not isinstance(row,dict) or str(row.get("type") or "") not in REWARD_TYPES:errors.append(f"Награда #{i}: неизвестный тип.")
  elif (_num(row.get("amount")) or 0)<=0:errors.append(f"Награда #{i}: количество должно быть больше нуля.")
 for i,row in enumerate(d.get("buttons") or [],1):
  if not isinstance(row,dict) or not str(row.get("button_id") or "").strip():errors.append(f"Кнопка #{i}: нет ID.")
  elif str(row.get("action") or "") not in BUTTON_ACTIONS:errors.append(f"Кнопка #{i}: неизвестное действие.")
 if d.get("rewards") and not d.get("double_confirmation_required",True):warnings.append("Рассылка с наградами должна требовать второе подтверждение.")
 return {"ok":not errors,"errors":errors,"warnings":warnings}
def preview(data):
 return {"telegram":{"title":data.get("title"),"text":data.get("text"),"image":data.get("image"),"buttons":data.get("buttons") or []},"vk":{"title":data.get("title"),"text":data.get("text"),"image":data.get("image"),"buttons":data.get("buttons") or []},"rewards":data.get("rewards") or []}
