# Нер-Талис — ТЗ для Claude Code: расширение конструктора эффектов, метки, зависимость и привыкание

Версия: 1.0  
Назначение: отдельное техническое задание для расширения конструктора эффектов в админ-панели, рантайме игры и базе данных.

Документ не заменяет общий список эффектов. Он описывает новые универсальные механики и расширение архитектуры конструктора, чтобы через админ-панель можно было настраивать сложные эффекты без правки кода под каждый отдельный случай.

---

# 1. Главные цели

Нужно расширить конструктор эффектов так, чтобы администратор мог создавать и настраивать:

1. Постоянные метки, которые зависят от скрытой репутации.
2. Систему зависимости: от чего возникает, куда влияет, что даёт, что запрещает, сколько длится, как усиливается и как лечится.
3. Систему привыкания: к предметам, зельям, навыкам, источникам, эффектам и действиям.
4. Гибкие типы эффектов, источники, цели, условия работы, правила стака, триггеры, длительность, приоритеты, видимость для игрока и логи.

Главное правило UX: игроку не показывать формулы. Игрок видит только понятный текст, итоговые значения и предупреждения. Формулы, коэффициенты, условия и технические поля остаются в админке, документации и коде.

---

# 2. Общая архитектура конструктора эффектов

## 2.1. EffectDefinition

Добавить или расширить сущность `EffectDefinition`.

Обязательные поля:

- `effect_id` — технический ID.
- `effect_name` — название для админ-панели.
- `player_name` — название для игрока.
- `player_text` — короткое описание для игрока без формул.
- `admin_description` — подробное описание для администратора.
- `effect_category` — категория эффекта.
- `effect_type` — технический тип эффекта.
- `source_type` — источник эффекта.
- `target_type` — цель эффекта.
- `active_when` — когда работает эффект.
- `trigger_type` — когда срабатывает.
- `duration_mode` — способ длительности.
- `stack_rule` — правило стака.
- `priority` — приоритет применения.
- `visibility_mode` — видимость игроку.
- `is_enabled` — включён/выключен.
- `log_event` — писать ли срабатывания в лог.

Дополнительные поля:

- `tags` — список тегов эффекта.
- `cleanse_tags` — теги очищения.
- `resist_tags` — теги сопротивления.
- `conflict_tags` — теги конфликтов.
- `allowed_targets` — разрешённые цели.
- `blocked_targets` — запрещённые цели.
- `works_in_pve` — работает в PVE.
- `works_in_pvp` — работает в PVP.
- `works_on_players` — работает на игроков.
- `works_on_mobs` — работает на мобов.
- `works_on_bosses` — работает на боссов.
- `works_on_world_bosses` — работает на мировых боссов.
- `can_be_cleansed` — можно снять очищением.
- `can_be_dispelled` — можно развеять.
- `can_trigger_effects` — может запускать цепочки эффектов.
- `can_be_reflected` — может быть отражён.
- `can_be_blocked` — может быть заблокирован защитой.
- `admin_notes` — заметки администратора.

---

## 2.2. Категории эффектов

В конструкторе должны быть категории:

- `combat` — боевые эффекты.
- `resource` — HP, мана, Дух, энергия.
- `stat` — характеристики.
- `defense` — защита, щиты, сопротивления.
- `damage` — урон, пробой, крит.
- `control` — оглушение, паника, путаница, блокировка действий.
- `trauma` — травмы.
- `curse` — проклятья.
- `zone` — зоны.
- `zone_protection` — защита от зон.
- `craft` — ремесло.
- `alchemy` — алхимия.
- `gathering` — добыча.
- `fishing` — рыбалка.
- `trade` — торговля.
- `quest` — задания.
- `achievement` — достижения.
- `reputation` — репутация.
- `hidden_reputation` — скрытая репутация.
- `mark` — метки.
- `addiction` — зависимость.
- `tolerance` — привыкание.
- `social` — социальные и модерационные эффекты.
- `item_lifecycle` — заряды, хрупкость, износ, одноразовость.
- `summon` — призывы, клоны, тени.
- `boss_phase` — фазы боссов.
- `technical` — технические эффекты.
- `custom` — другое.

---

## 2.3. Типы эффектов

В конструкторе нужны универсальные типы:

- `stat_modifier`
- `resource_modifier`
- `max_resource_modifier`
- `resource_regeneration`
- `periodic_damage`
- `instant_heal`
- `instant_resource_restore`
- `damage_modifier`
- `damage_taken_modifier`
- `crit_chance_modifier`
- `crit_damage_modifier`
- `accuracy_modifier`
- `dodge_modifier`
- `defense_modifier`
- `shield`
- `barrier`
- `control_effect`
- `action_block`
- `slot_block`
- `cooldown_modifier`
- `bonus_action_modifier`
- `encounter_chance_modifier`
- `event_chance_modifier`
- `loot_modifier`
- `craft_modifier`
- `trade_modifier`
- `quest_modifier`
- `achievement_passive`
- `reputation_modifier`
- `hidden_reputation_modifier`
- `mark_effect`
- `addiction_effect`
- `tolerance_effect`
- `zone_effect`
- `zone_protection`
- `summon_effect`
- `item_charge_effect`
- `item_durability_effect`
- `item_binding_effect`
- `conditional_unlock`
- `notification_effect`
- `scripted_effect`

---

## 2.4. Источники эффектов

Поле: `source_type`.

Варианты:

- `item`
- `equipped_item`
- `inventory_item`
- `special_slot_item`
- `pouch_item`
- `consumable`
- `potion`
- `food`
- `skill`
- `passive_skill`
- `mob_skill`
- `mob_trait`
- `boss_phase`
- `curse`
- `trauma`
- `zone`
- `location`
- `city`
- `region`
- `world_event`
- `quest`
- `achievement`
- `reputation`
- `hidden_reputation`
- `mark`
- `addiction`
- `tolerance`
- `admin`
- `system`
- `moderation`
- `home`
- `guild`
- `faction`
- `custom`

---

## 2.5. Цели эффекта

Поле: `target_type`.

Варианты:

- `self`
- `enemy`
- `ally`
- `party`
- `raid`
- `all_enemies`
- `all_allies`
- `all_participants`
- `random_enemy`
- `random_ally`
- `player`
- `mob`
- `boss`
- `location`
- `city`
- `region`
- `item`
- `skill`
- `service`
- `inventory_slot`
- `weapon_slot_1`
- `weapon_slot_2`
- `pouch`
- `home`
- `quest`
- `faction`
- `custom`

---

## 2.6. Когда работает эффект

Поле: `active_when`.

Варианты:

- `always`
- `equipped`
- `in_inventory`
- `in_special_slot`
- `in_pouch`
- `consumed`
- `activated`
- `in_battle`
- `outside_battle`
- `on_location`
- `in_city`
- `in_region`
- `in_zone`
- `during_world_event`
- `during_quest`
- `after_quest_completed`
- `after_achievement_unlocked`
- `while_mark_active`
- `while_addiction_active`
- `while_tolerance_active`
- `while_hidden_reputation_stage_active`
- `on_low_hp`
- `on_death`
- `after_death`
- `on_attack`
- `on_receive_damage`
- `on_deal_damage`
- `on_use_skill`
- `on_use_item`
- `on_trade`
- `on_craft`
- `on_gather`
- `on_fishing`
- `on_rest`
- `on_home_rest`
- `on_admin_apply`
- `custom_condition`

---

## 2.7. Триггеры эффекта

Поле: `trigger_type`.

Варианты:

- `manual`
- `automatic`
- `on_apply`
- `on_remove`
- `on_tick`
- `each_turn`
- `each_action`
- `each_search`
- `each_minute`
- `each_hour`
- `battle_start`
- `turn_start`
- `turn_end`
- `before_attack`
- `after_attack`
- `before_damage`
- `after_damage`
- `before_heal`
- `after_heal`
- `on_resource_change`
- `on_reputation_change`
- `on_hidden_reputation_change`
- `on_mark_stage_change`
- `on_addiction_stage_change`
- `on_tolerance_stage_change`
- `on_level_up`
- `on_quest_start`
- `on_quest_complete`
- `on_quest_fail`
- `on_item_equip`
- `on_item_unequip`
- `on_item_consume`
- `on_location_enter`
- `on_location_leave`
- `on_service_use`
- `custom`

---

## 2.8. Длительность

Поле: `duration_mode`.

Варианты:

- `instant`
- `turns`
- `seconds`
- `minutes`
- `hours`
- `days`
- `until_battle_end`
- `until_location_leave`
- `until_zone_leave`
- `until_item_removed`
- `while_condition_true`
- `permanent`
- `until_cleansed`
- `until_stage_changed`
- `until_admin_remove`
- `custom`

Поля:

- `duration_turns`
- `duration_seconds`
- `duration_min_seconds`
- `duration_max_seconds`
- `expires_at`
- `remove_on_death`
- `remove_on_battle_end`
- `remove_on_location_leave`
- `linger_duration_seconds`

---

## 2.9. Стаки и конфликты

Поле: `stack_rule`.

Варианты:

- `none`
- `refresh`
- `strongest_only`
- `newest_only`
- `oldest_only`
- `stack_limited`
- `additive_limited`
- `multiplicative_limited`
- `unique_only`
- `per_source`
- `per_tag`
- `replace_same_source`
- `separate_instances`
- `custom`

Поля:

- `max_stacks`
- `stack_decay_rule`
- `stack_duration_refresh`
- `stack_power_rule`
- `max_total_bonus_percent`
- `max_total_penalty_percent`
- `conflict_group_id`
- `conflict_resolution: block_new / replace_old / keep_stronger / keep_weaker / merge`

---

# 3. Постоянная метка от скрытой репутации

## 3.1. Назначение

Нужен эффект метки, который работает постоянно и зависит от скрытой репутации игрока.

Метка может быть видимой или скрытой. Она не обязательно является обычным бафом/дебафом. Это постоянный статус, который меняется автоматически, когда меняется скрытая репутация.

Примеры:

- Метка подозрения стражи.
- Метка доверия Искателей.
- Метка тёмного следа.
- Метка древних руин.
- Метка охотника.
- Метка подполья.
- Метка проклятого свидетеля.
- Метка торгового доверия.

---

## 3.2. HiddenReputationDefinition

Добавить сущность скрытой репутации.

Поля:

- `hidden_reputation_id`
- `name_admin`
- `name_player_optional`
- `description_admin`
- `owner_scope: player / faction / city / location / npc / system`
- `min_value`
- `max_value`
- `default_value`
- `is_visible_to_player`
- `visibility_mode: hidden / vague_text / exact_value / stage_only`
- `decay_enabled`
- `decay_per_day`
- `decay_to_value`
- `log_changes`

---

## 3.3. PlayerHiddenReputation

Поля состояния игрока:

- `player_id`
- `hidden_reputation_id`
- `current_value`
- `current_stage_id`
- `last_changed_at`
- `last_decay_at`
- `change_reason`
- `source_id`

Формула изменения:

`new_value = clamp(current_value + reputation_delta, min_value, max_value)`

Формула спада:

`days_passed = floor((current_time - last_decay_at) / 86400)`  
`new_value = move_towards(current_value, decay_to_value, days_passed * decay_per_day)`

---

## 3.4. MarkEffectDefinition

Добавить тип эффекта:

`effect_type: mark_effect`

Поля:

- `mark_id`
- `mark_name_admin`
- `mark_name_player`
- `mark_description_admin`
- `player_text`
- `linked_hidden_reputation_id`
- `mark_visibility: hidden / visible / visible_after_stage / admin_only`
- `is_permanent: true`
- `recalculate_on_hidden_reputation_change: true`
- `remove_when_reputation_stage_missing: true / false`
- `stage_rules`
- `effects_by_stage`
- `unlock_rules`
- `block_rules`
- `notification_rules`

---

## 3.5. Стадии метки

Каждая метка должна иметь стадии.

Поля стадии:

- `stage_id`
- `stage_name_admin`
- `stage_name_player`
- `min_reputation_value`
- `max_reputation_value`
- `player_text`
- `admin_description`
- `applied_effects`
- `unlocked_actions`
- `blocked_actions`
- `npc_reactions`
- `location_event_modifiers`
- `trade_modifiers`
- `quest_modifiers`
- `combat_modifiers`

Пример стадий:

- `neutral` — обычное состояние.
- `noticed` — игрок замечен.
- `trusted` — игроку доверяют.
- `suspected` — игрок вызывает подозрение.
- `wanted` — игрок под надзором.
- `marked` — игрок несёт сильную метку.

---

## 3.6. Формула работы метки

Метка всегда пересчитывается от скрытой репутации.

`hidden_rep = get_hidden_reputation(player_id, linked_hidden_reputation_id)`  
`stage = find_stage_by_value(hidden_rep.current_value)`  
`apply_mark_stage_effects(player_id, mark_id, stage)`

Если стадия изменилась:

`remove_previous_stage_effects()`  
`apply_new_stage_effects()`  
`send_notification_if_enabled()`

---

## 3.7. Что может давать метка

Метка может:

- открывать диалоги NPC;
- скрывать диалоги NPC;
- менять цены;
- менять шанс облавы;
- менять шанс скрытых событий;
- менять шанс PVE/PVP встреч;
- открывать задания;
- закрывать задания;
- давать бафы;
- давать дебафы;
- менять реакцию фракции;
- менять тексты в локациях;
- влиять на награды;
- влиять на штрафы;
- запускать особые уведомления;
- блокировать сервисы профиля;
- разрешать особые действия.

---

## 3.8. Пример: Метка подозрения стражи

**Для чего подходит:**  
Криминальные действия, облавы, штрафы, тёмные переулки, подпольное казино, чёрный рынок.

**Описание:**  
Чем выше скрытая репутация подозрения, тем чаще игрок сталкивается с проверками, облавами и ограничениями.

**Формулы:**

`raid_chance = base_raid_chance + suspicion_stage_raid_bonus`  
`fine_multiplier = 1 + suspicion_stage_fine_bonus_percent / 100`  
`final_fine = base_fine * fine_multiplier`

**Стадии:**

- 0–20: стража не обращает внимания.
- 21–50: стража иногда присматривается.
- 51–80: шанс облавы выше.
- 81–100: игрок под сильным подозрением, часть услуг может быть закрыта.

---

## 3.9. Пример: Метка доверия Искателей

**Для чего подходит:**  
Застава Искателей, рейды, дальние походы, доска объявлений, найм команды.

**Описание:**  
Чем выше скрытое доверие Искателей, тем больше походов, заданий и услуг открывается игроку.

**Формулы:**

`raid_access_allowed = hidden_trust >= required_trust`  
`hire_cost = base_hire_cost * (1 - trust_discount_percent / 100)`  
`quest_reward = base_reward * (1 + trust_reward_bonus_percent / 100)`

---

# 4. Зависимость

## 4.1. Назначение

Нужен универсальный эффект зависимости, который можно настраивать в админ-панели.

Зависимость должна отвечать на вопросы:

- От чего появляется?
- Куда влияет?
- Что даёт?
- Что запрещает?
- Сколько длится?
- Как накапливается?
- Какие стадии имеет?
- Что даёт на каждой стадии?
- Какие штрафы появляются без источника зависимости?
- Как лечится?
- Как снижается со временем?
- Какие действия блокируются?
- Что показывать игроку?

---

## 4.2. AddictionDefinition

Добавить тип эффекта:

`effect_type: addiction_effect`

Поля:

- `addiction_id`
- `name_admin`
- `name_player`
- `description_admin`
- `player_text`
- `source_tags`
- `source_item_ids`
- `source_effect_ids`
- `source_skill_ids`
- `source_action_types`
- `addiction_scope: player / item_group / potion_group / skill_group / custom`
- `addiction_value_min`
- `addiction_value_max`
- `default_value`
- `gain_per_use`
- `gain_per_trigger`
- `gain_cooldown_seconds`
- `daily_gain_limit`
- `decay_enabled`
- `decay_per_day`
- `decay_delay_seconds`
- `withdrawal_enabled`
- `treatment_enabled`
- `visibility_mode`
- `stages`
- `stage_effects`
- `stage_unlocks`
- `stage_blocks`
- `log_changes`

---

## 4.3. PlayerAddictionState

Поля состояния игрока:

- `player_id`
- `addiction_id`
- `current_value`
- `current_stage_id`
- `last_gain_at`
- `last_decay_at`
- `last_source_used_at`
- `withdrawal_active`
- `treatment_active`
- `created_at`
- `updated_at`

Формула накопления:

`new_value = clamp(current_value + gain_amount, addiction_value_min, addiction_value_max)`

Формула спада:

`if current_time - last_source_used_at >= decay_delay_seconds:`  
`new_value = max(addiction_value_min, current_value - days_passed * decay_per_day)`

---

## 4.4. Источники зависимости

Зависимость можно привязать к:

- конкретному предмету;
- группе предметов;
- тегу предмета;
- зелью;
- стимулятору;
- еде;
- напитку;
- навыку;
- эффекту;
- зоне;
- локации;
- действию;
- торговле;
- азартной игре;
- проклятью;
- заданию;
- админскому статусу;
- кастомному событию.

Поля:

- `addiction_source_type`
- `required_source_tags`
- `required_source_ids`
- `ignored_source_tags`
- `ignored_source_ids`
- `gain_on: use / consume / equip / win / lose / action / tick / battle_end / custom`

---

## 4.5. Что зависимость может давать

Зависимость не всегда только плохая. На ранних стадиях она может давать бонус, а позже — штраф.

Может давать:

- временное усиление после употребления источника;
- бонус к урону;
- бонус к скорости восстановления;
- бонус к шансу редких событий;
- снижение страха/паники;
- повышение энергии;
- повышение Духа;
- повышение маны;
- увеличение риска побочных эффектов;
- снижение характеристик без источника;
- запрет действий;
- штраф к торговле;
- штраф к ремеслу;
- штраф к опыту;
- штраф к монетам;
- ограничение использования сервисов;
- появление ломки.

---

## 4.6. Что зависимость может запрещать

Поля блокировок:

- `blocked_actions`
- `blocked_items`
- `blocked_skills`
- `blocked_services`
- `blocked_locations`
- `blocked_trades`
- `blocked_craft_types`
- `blocked_dialogues`
- `blocked_quest_actions`

Примеры:

- Запрет использовать сильные зелья без очищения.
- Запрет входа в священную зону.
- Запрет некоторых услуг NPC.
- Запрет быстрого отдыха.
- Запрет передачи предметов при тяжёлой зависимости.

---

## 4.7. Стадии зависимости

Стадии должны настраиваться.

Поля стадии:

- `stage_id`
- `stage_name_admin`
- `stage_name_player`
- `min_value`
- `max_value`
- `player_text`
- `admin_description`
- `positive_effects`
- `negative_effects`
- `withdrawal_effects`
- `blocked_actions`
- `required_treatment`
- `notification_text`

Пример стадий:

### Стадия 0 — Нет зависимости

- Значение: 0–9.
- Эффектов нет.

### Стадия 1 — Привязанность

- Значение: 10–29.
- После использования источника небольшой бонус.
- Без источника штрафов нет или они слабые.

### Стадия 2 — Тяга

- Значение: 30–59.
- После источника бонус выше.
- Без источника появляется слабый штраф.

### Стадия 3 — Сильная зависимость

- Значение: 60–89.
- После источника сильный краткий бонус.
- Без источника штраф к точности, уклонению, восстановлению или энергии.

### Стадия 4 — Разрушительная зависимость

- Значение: 90–100.
- Сильные штрафы без источника.
- Возможны блокировки действий, сервисов и квестов.
- Требуется лечение, ритуал, NPC или длительный отказ.

---

## 4.8. Ломка

Ломка — отдельный режим зависимости, который включается, если игрок долго не использует источник зависимости.

Формула:

`if addiction_value >= withdrawal_min_value and current_time - last_source_used_at >= withdrawal_delay_seconds:`  
`withdrawal_active = true`

Эффекты ломки:

- снижение точности;
- снижение уклонения;
- снижение восстановления энергии;
- снижение восстановления HP/маны/Духа;
- снижение опыта;
- снижение монет с добычи;
- повышение шанса паники;
- повышение шанса ошибки ремесла;
- запрет части действий.

Формула штрафа:

`withdrawal_power = addiction_value * withdrawal_power_multiplier`  
`final_stat = base_stat * (1 - withdrawal_power / 100)`

---

## 4.9. Лечение зависимости

Зависимость должна лечиться разными способами.

Варианты:

- зелье очищения зависимости;
- NPC-лекарь;
- священная зона;
- дом/отдых;
- ритуал;
- задание;
- время без источника;
- админ-снятие.

Поля лечения:

- `treatment_method`
- `treatment_cost`
- `treatment_duration_seconds`
- `treatment_reduce_flat`
- `treatment_reduce_percent`
- `can_remove_stage`
- `can_fully_remove`
- `relapse_chance`
- `treatment_cooldown_seconds`

Формула:

`new_value = max(addiction_value_min, current_value - reduce_flat - current_value * reduce_percent / 100)`

---

## 4.10. Пример: зависимость от боевого стимулятора

**Источник:** предметы с тегом `combat_stimulant`.

**Что даёт после использования:**

- временно повышает физический урон навыков Духа;
- временно повышает максимум энергии;
- может повышать точность.

**Что даёт при ломке:**

- снижает точность;
- снижает уклонение;
- снижает восстановление энергии;
- повышает шанс паники.

**Формулы:**

`addiction_value += 5`  
`final_spirit_skill_damage = base_physical_skill_damage * (1 + stimulant_bonus_percent / 100)`  
`withdrawal_accuracy = base_accuracy - addiction_value * 0.1`

Важно: Дух — ресурс физических боевых навыков, стоек и приёмов. Не трактовать Дух как магический урон.

---

## 4.11. Пример: зависимость от азартной игры

**Источник:** подпольное казино, игровые автоматы, ставки, рискованные мини-игры.

**Что даёт:**

- может повышать азартный бонус при редких выигрышах;
- повышает желание повторять действие;
- при высоких стадиях может блокировать часть торговых решений или повышать потери.

**Формулы:**

`addiction_value += casino_gain_per_play`  
`if addiction_stage >= 3: casino_loss_multiplier = 1 + loss_bonus_percent / 100`  
`final_loss = base_loss * casino_loss_multiplier`

---

# 5. Привыкание

## 5.1. Назначение

Привыкание — это не то же самое, что зависимость.

Зависимость — накопительная тяга и последствия.  
Привыкание — снижение или изменение эффекта при частом повторном использовании одного источника.

Привыкание должно быть настраиваемым:

- от чего возникает;
- куда влияет;
- что даёт;
- что запрещает;
- сколько длится;
- как накапливается;
- как спадает;
- какие пороги имеет;
- как влияет на силу эффекта;
- какие побочные эффекты добавляет.

---

## 5.2. ToleranceDefinition

Добавить тип эффекта:

`effect_type: tolerance_effect`

Поля:

- `tolerance_id`
- `name_admin`
- `name_player`
- `description_admin`
- `player_text`
- `source_tags`
- `source_item_ids`
- `source_effect_ids`
- `source_skill_ids`
- `source_action_types`
- `tolerance_scope: exact_item / item_group / effect_type / potion_type / skill_type / action_type / custom`
- `value_min`
- `value_max`
- `gain_per_use`
- `gain_per_repeated_use`
- `gain_window_seconds`
- `decay_enabled`
- `decay_per_hour`
- `decay_delay_seconds`
- `effectiveness_formula_mode`
- `min_effectiveness_percent`
- `max_penalty_percent`
- `stages`
- `stage_effects`
- `stage_blocks`
- `log_changes`

---

## 5.3. PlayerToleranceState

Поля состояния:

- `player_id`
- `tolerance_id`
- `source_key`
- `current_value`
- `current_stage_id`
- `recent_use_count`
- `last_use_at`
- `last_decay_at`
- `created_at`
- `updated_at`

`source_key` нужен, чтобы разделять привыкание к разным предметам или группам.

Пример:

- `potion:minor_healing`
- `potion:all_healing`
- `skill:fireball`
- `effect:hp_regeneration`
- `action:casino_play`

---

## 5.4. Формула накопления привыкания

`recent_use_count = count_uses(source_key, gain_window_seconds)`  
`gain = gain_per_use + max(0, recent_use_count - 1) * gain_per_repeated_use`  
`new_value = clamp(current_value + gain, value_min, value_max)`

---

## 5.5. Формула снижения эффективности

Базовая формула:

`effectiveness = max(min_effectiveness_percent, 100 - current_value * effectiveness_loss_per_value)`

Применение:

`final_effect_power = base_effect_power * effectiveness / 100`

Пример:

- Привыкание: 30.
- Потеря эффективности: 1% за 1 значение.
- Минимум эффективности: 50%.
- Итог: зелье действует на 70% силы.

---

## 5.6. Что привыкание может менять

Привыкание может:

- снижать силу лечения;
- снижать восстановление маны;
- снижать восстановление Духа;
- снижать восстановление энергии;
- снижать длительность бафа;
- снижать шанс срабатывания;
- повышать шанс побочного эффекта;
- увеличивать откат;
- повышать стоимость использования;
- требовать большую дозу;
- временно запрещать повторное использование;
- менять эффект на слабый вариант;
- превращать бонус в нейтральный эффект;
- превращать бонус в слабый дебаф при передозировке.

---

## 5.7. Что привыкание может запрещать

Поля блокировок:

- `block_same_item_use`
- `block_same_effect_use`
- `block_same_skill_use`
- `block_consumable_group`
- `block_buff_refresh`
- `block_stacking`
- `block_service_action`
- `block_craft_bonus`

Примеры:

- Нельзя выпить такое же зелье 3 хода.
- Нельзя обновить тот же баф, пока действует привыкание.
- Сильное зелье лечения временно блокируется после частого использования.
- Один и тот же навык получает увеличенный откат.

---

## 5.8. Стадии привыкания

Стадии должны быть настраиваемыми.

### Стадия 0 — Нет привыкания

- Значение: 0–9.
- Эффект работает полностью.

### Стадия 1 — Лёгкое привыкание

- Значение: 10–29.
- Сила эффекта немного снижена.

### Стадия 2 — Устойчивое привыкание

- Значение: 30–59.
- Сила эффекта заметно снижена.
- Может появиться увеличенный откат.

### Стадия 3 — Сильное привыкание

- Значение: 60–89.
- Эффект работает слабо.
- Возможны побочные эффекты.

### Стадия 4 — Почти полная невосприимчивость

- Значение: 90–100.
- Эффект почти не работает или временно блокируется.

---

## 5.9. Спад привыкания

Привыкание должно снижаться, если игрок долго не использует источник.

Формула:

`if current_time - last_use_at >= decay_delay_seconds:`  
`new_value = max(value_min, current_value - hours_passed * decay_per_hour)`

---

## 5.10. Пример: привыкание к зельям лечения

**Источник:** предметы с тегом `healing_potion`.

**Что меняет:** силу лечения.

**Формула:**

`healing_effectiveness = max(50, 100 - tolerance_value)`  
`final_heal = base_heal * healing_effectiveness / 100`

**Дополнительно:**

Если привыкание выше 70:

`side_effect_chance = (tolerance_value - 70) * 1`

Побочный эффект: тошнота, снижение точности или снижение восстановления энергии.

---

## 5.11. Пример: привыкание к одному навыку

**Источник:** конкретный навык или группа навыков.

**Что меняет:** увеличивает откат при слишком частом использовании.

**Формула:**

`extra_cooldown = floor(tolerance_value / cooldown_threshold)`  
`final_cooldown = base_cooldown + extra_cooldown`

**Ограничение:**

`final_cooldown <= max_final_cooldown`

---

# 6. Расширение админ-панели конструктора эффектов

## 6.1. Основные вкладки конструктора

В конструкторе эффектов добавить вкладки:

1. Основное.
2. Источник.
3. Цель.
4. Когда работает.
5. Триггеры.
6. Длительность.
7. Стаки и конфликты.
8. Модификаторы.
9. Условия.
10. Сопротивления и очищение.
11. Видимость игроку.
12. Логи и уведомления.
13. Стадии.
14. Скрытая репутация и метки.
15. Зависимость.
16. Привыкание.
17. Проверка и предпросмотр.

---

## 6.2. Вкладка «Основное»

Поля:

- Название для админки.
- Название для игрока.
- Краткий текст для игрока.
- Подробное описание для админа.
- Категория.
- Тип.
- Теги.
- Включён/выключен.
- Редкость/важность.
- Приоритет.

---

## 6.3. Вкладка «Источник»

Поля:

- Тип источника.
- Конкретный источник.
- Разрешённые теги источника.
- Запрещённые теги источника.
- Работает от предметов.
- Работает от навыков.
- Работает от мобов.
- Работает от зон.
- Работает от заданий.
- Работает от достижений.
- Работает от скрытой репутации.
- Работает от админа.

---

## 6.4. Вкладка «Цель»

Поля:

- Цель.
- Разрешённые категории целей.
- Запрещённые категории целей.
- Работает на игроках.
- Работает на мобах.
- Работает на боссах.
- Работает на мировых боссах.
- Работает на предметах.
- Работает на навыках.
- Работает на локациях.

---

## 6.5. Вкладка «Когда работает»

Поля:

- Всегда.
- Пока экипирован.
- Пока в инвентаре.
- Пока в подсумке.
- Пока в особом слоте.
- В бою.
- Вне боя.
- В конкретной локации.
- В городе.
- В регионе.
- В зоне.
- Во время мирового события.
- При активном задании.
- При достижении.
- При стадии скрытой репутации.
- При стадии зависимости.
- При стадии привыкания.
- При кастомном условии.

---

## 6.6. Вкладка «Модификаторы»

Модификатор должен быть отдельной вложенной сущностью.

Поля модификатора:

- `modifier_id`
- `target_parameter`
- `operation`
- `flat_value`
- `percent_value`
- `min_value`
- `max_value`
- `cap_mode`
- `rounding_rule`
- `condition_id`
- `apply_order`

Операции:

- `add_flat`
- `subtract_flat`
- `add_percent_additive`
- `subtract_percent_additive`
- `multiply`
- `divide`
- `set_value`
- `min`
- `max`
- `clamp`
- `block`
- `unlock`
- `chance_modify`
- `weight_modify`

Параметры:

- HP.
- Мана.
- Дух.
- Энергия.
- Сила.
- Мудрость.
- Выносливость.
- Ловкость.
- Восприятие.
- Интеллект.
- Точность.
- Уклонение.
- Шанс крита.
- Урон крита.
- Физическая защита.
- Магическая защита.
- Броня.
- Урон.
- Получаемый урон.
- Лечение.
- Опыт.
- Монеты.
- Шанс добычи.
- Шанс события.
- Шанс встречи.
- Шанс ремесла.
- Время крафта.
- Цена покупки.
- Цена продажи.
- Комиссия.
- Откат навыка.
- Количество действий.
- Слот.
- Сервис.
- Доступ.
- Кастомный параметр.

---

## 6.7. Вкладка «Условия»

Условия должны быть универсальными.

Варианты условий:

- уровень игрока;
- характеристика;
- ресурс;
- предмет в инвентаре;
- предмет экипирован;
- предмет в подсумке;
- активный навык;
- активное задание;
- завершённое задание;
- достижение;
- скрытая репутация;
- стадия метки;
- стадия зависимости;
- стадия привыкания;
- фракционная репутация;
- локация;
- город;
- регион;
- зона;
- время суток;
- сезон;
- мировое событие;
- тип боя;
- тип моба;
- ранг моба;
- количество стаков;
- количество использований;
- кулдаун;
- кастомный флаг.

Логика условий:

- `all` — все условия.
- `any` — любое условие.
- `none` — ни одно условие.
- `nested_group` — вложенная группа условий.

---

## 6.8. Вкладка «Видимость игроку»

Поля:

- `show_to_player`
- `show_icon`
- `show_duration`
- `show_stacks`
- `show_stage`
- `show_exact_values`
- `show_vague_text`
- `show_warning`
- `hidden_until_triggered`
- `admin_only`

Варианты видимости:

- полностью скрыто;
- видно только название;
- видно название и описание;
- видно стадию;
- видно точные значения;
- видно только предупреждение;
- видно только после срабатывания.

---

## 6.9. Предпросмотр

В админке нужен предпросмотр:

- как эффект видит игрок;
- как эффект видит админ;
- какие параметры изменяются;
- какие условия не выполнены;
- какие эффекты конфликтуют;
- какие стаки применяются;
- что будет при снятии;
- что будет при смене стадии;
- что будет при смерти;
- что будет при выходе из локации;
- что будет через 1 час/1 день.

---

# 7. Логи и отладка

Нужно логировать:

- наложение эффекта;
- снятие эффекта;
- изменение стадии;
- изменение скрытой репутации;
- изменение зависимости;
- изменение привыкания;
- срабатывание триггера;
- блокировку действия;
- изменение параметров;
- ошибку условия;
- конфликт стака;
- очищение;
- админское вмешательство.

Поля лога:

- `log_id`
- `player_id`
- `target_id`
- `effect_id`
- `effect_instance_id`
- `source_type`
- `source_id`
- `trigger_type`
- `old_value`
- `new_value`
- `stage_from`
- `stage_to`
- `reason`
- `created_at`
- `payload_json`

---

# 8. Задачи для Claude Code

## 8.1. Backend

Нужно:

1. Расширить модели эффектов.
2. Добавить модели скрытой репутации.
3. Добавить модели меток.
4. Добавить модели зависимости.
5. Добавить модели привыкания.
6. Добавить универсальные условия.
7. Добавить универсальные модификаторы.
8. Добавить пересчёт активных эффектов.
9. Добавить пересчёт меток при изменении скрытой репутации.
10. Добавить накопление зависимости.
11. Добавить спад зависимости.
12. Добавить ломку.
13. Добавить лечение зависимости.
14. Добавить накопление привыкания.
15. Добавить спад привыкания.
16. Добавить снижение эффективности от привыкания.
17. Добавить логи.
18. Добавить тесты.

---

## 8.2. Admin UI

Нужно:

1. Расширить конструктор эффектов вкладками.
2. Добавить удобный выбор типа эффекта.
3. Добавить настройку источников.
4. Добавить настройку целей.
5. Добавить настройку условий.
6. Добавить настройку модификаторов.
7. Добавить настройку стака.
8. Добавить настройку стадий.
9. Добавить настройку скрытой репутации.
10. Добавить настройку меток.
11. Добавить настройку зависимости.
12. Добавить настройку привыкания.
13. Добавить предпросмотр.
14. Добавить проверку ошибок.
15. Добавить тестовое применение эффекта на игроке в админке.

---

## 8.3. Validation

Проверки:

- Нельзя создать эффект без типа.
- Нельзя создать эффект без источника, если источник обязателен.
- Нельзя создать стадию без диапазона.
- Диапазоны стадий не должны пересекаться.
- Стаки не должны быть бесконечными без лимита.
- Процентные бонусы должны иметь caps.
- Постоянные эффекты должны иметь способ снятия или условие пересчёта.
- Зависимость должна иметь максимум значения.
- Привыкание должно иметь минимум эффективности.
- Метка от скрытой репутации должна иметь linked_hidden_reputation_id.
- Эффекты с `can_trigger_effects=false` не должны запускать цепочки.
- Отражение и шипы не должны запускать бесконечные отражения.

---

# 9. Acceptance Criteria

Готово, если:

1. Админ может создать эффект метки, связанный со скрытой репутацией.
2. Метка автоматически меняет стадию при изменении скрытой репутации.
3. Метка может давать бонусы, штрафы, открывать и блокировать действия.
4. Админ может создать зависимость от предмета, группы предметов, навыка, действия или зоны.
5. Зависимость накапливается, имеет стадии, ломку, лечение и спад.
6. Админ может создать привыкание к предмету, эффекту, навыку или действию.
7. Привыкание снижает эффективность или меняет поведение источника.
8. Все новые эффекты имеют предпросмотр в админке.
9. Все изменения пишутся в лог.
10. Игроку не показываются формулы.
11. Система работает без ручного кода под каждый новый эффект.
