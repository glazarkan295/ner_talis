# Нер-Талис — свойства, эффекты и зоны для будущего конструктора

Версия: рабочая сборка по текущему списку эффектов.

Назначение файла: использовать как основу для будущего конструктора предметов, эффектов, проклятий, зон, ловушек, мобов, событий и админ-панели.

Главное правило UX: игроку не показывать формулы. Игрок видит только понятное описание и итоговые значения. Формулы, коэффициенты и внутренние поля остаются для админки, документации и кода.

---

# 1. Общие правила конструктора эффектов

## 1.1. Общие поля любого эффекта

- `effect_id` — технический ID эффекта.
- `effect_name` — название эффекта для админки.
- `player_text` — короткий текст для игрока без формул.
- `admin_description` — подробное описание для администратора.
- `effect_type` — тип эффекта.
- `source_type` — источник: предмет, навык, моб, ловушка, событие, зона, проклятье, админ.
- `target` — цель: владелец, враг, союзник, вся группа, все участники боя, случайная цель.
- `active_when` — когда работает: экипирован, в инвентаре, в бою, при входе в локацию, при смерти, при атаке, при получении урона.
- `duration_turns` — длительность в ходах.
- `duration_seconds` — длительность в секундах.
- `apply_chance_percent` — шанс наложения.
- `stack_rule` — правило стака: обновлять, только сильнейший, ограниченное сложение, уникальный эффект.
- `max_stacks` — максимальное количество стаков.
- `can_be_cleansed` — можно ли снять очищением.
- `cleanse_tags` — теги очищения: яд, огонь, кровь, проклятье, контроль, холод и т.д.
- `works_in_pve` — работает в PVE.
- `works_in_pvp` — работает в PVP.
- `show_to_player` — показывать игроку в активных эффектах.
- `log_event` — записывать срабатывание в лог.

## 1.2. Правила против бесконечных цепочек

По умолчанию периодический и ответный урон не должен запускать новые цепочки эффектов.

Для таких эффектов ставить:

- `can_trigger_effects: false`
- `can_be_reflected: false`

Это касается яда, поджога, кровотечения, аур урона, шипов, отражения, взрыва трупа и похожих эффектов.

## 1.3. Общие правила стака

- Простые бафы и дебафы: обычно `strongest_only` или `refresh`.
- Кровотечение: может быть `stack_limited`.
- Яд и поджог: лучше `refresh` или `strongest_only`.
- Ауры: чаще `strongest_only`, чтобы несколько одинаковых аур не разгоняли баланс.
- Уникальные артефактные эффекты: `unique_only`.

## 1.4. Общие правила ресурсов

Для жизни, маны и духа использовать общий тип:

`effect_type: max_resource_modifier`

А ресурс выбирать отдельно:

- `resource: hp`
- `resource: mana`
- `resource: spirit`

Положительное значение — хранилище ресурса. Отрицательное значение — утечка, истощение или ослабление.

---

# 2. Базовые эффекты, параметры и ресурсы

## 1. Отравление

Тип: отрицательный периодический эффект.

Что делает: наносит урон цели каждый ход в течение заданного количества ходов. Может действовать на игрока, моба или другого игрока.

Текст для игрока: цель отравлена и получает урон каждый ход.

Формула:

`poison_damage_per_turn = poison_flat_damage + target_max_hp * poison_percent / 100`

Баланс:

- слабое отравление: 1-2% max HP за ход;
- обычное: 2-4% max HP за ход;
- сильное: 4-6% max HP за ход;
- длительность обычно 2-5 ходов;
- общий урон без уникальных эффектов желательно ограничивать 30-40% max HP.

Поля конструктора:

- `effect_type: poison`
- `target`
- `duration_turns`
- `tick_interval: each_turn`
- `flat_damage`
- `percent_max_hp_damage`
- `stack_rule: refresh / strongest_only / stack_limited`
- `max_stacks`
- `can_be_cleansed: true`
- `cleanse_tags: poison, negative_effect`
- `total_damage_cap_percent`

## 2. Регенерация здоровья

Тип: положительный периодический эффект.

Что делает: восстанавливает здоровье каждый ход.

Текст для игрока: восстанавливает часть здоровья каждый ход.

Формула:

`heal_per_turn = heal_flat + player_max_hp * heal_percent / 100`

Баланс:

- слабая: 0.5-1% max HP за ход;
- обычная: 1-2%;
- сильная: 2-3%;
- выше 3% — только для редких навыков, зелий, уникальных предметов или временных бафов.

Поля конструктора:

- `effect_type: hp_regeneration`
- `target: self / ally / wearer`
- `duration_turns`
- `tick_interval: each_turn`
- `flat_heal`
- `percent_max_hp_heal`
- `stack_rule`
- `max_stacks`
- `can_be_dispelled`

## 3. Регенерация маны

Тип: положительный периодический эффект.

Что делает: восстанавливает ману каждый ход.

Текст для игрока: восстанавливает часть маны каждый ход.

Формула:

`mana_restore_per_turn = mana_flat + player_max_mana * mana_percent / 100`

Баланс:

- слабая: 0.5-1% max mana за ход;
- обычная: 1-2%;
- сильная: 2-3%;
- выше 3% — для редких эффектов, зелий, артефактов или уникальных предметов.

Поля конструктора:

- `effect_type: mana_regeneration`
- `target`
- `duration_turns`
- `tick_interval: each_turn`
- `flat_restore`
- `percent_max_mana_restore`
- `stack_rule`
- `max_stacks`

## 4. Регенерация духа

Тип: положительный периодический эффект.

Что делает: восстанавливает дух каждый ход.

Текст для игрока: восстанавливает часть духа каждый ход.

Формула:

`spirit_restore_per_turn = spirit_flat + player_max_spirit * spirit_percent / 100`

Баланс:

- слабая: 0.5-1% max spirit за ход;
- обычная: 1-2%;
- сильная: 2-3%;
- выше 3% — только для редких или временных эффектов.

Поля конструктора:

- `effect_type: spirit_regeneration`
- `target`
- `duration_turns`
- `tick_interval: each_turn`
- `flat_restore`
- `percent_max_spirit_restore`
- `stack_rule`
- `max_stacks`

## 5. Урон крита

Тип: параметрический эффект.

Что делает: повышает или уменьшает дополнительный урон при критическом ударе.

Текст для игрока: изменяет силу критического удара.

Формула:

`final_crit_damage = base_crit_damage + crit_damage_bonus`

Баланс:

- обычные предметы: +3-7%;
- редкие: +7-15%;
- эпические: +15-25%;
- легендарные/уникальные: вручную, обычно не выше +40-50% без штрафов;
- мягкий предел итогового критического урона: 250-300%.

Поля конструктора:

- `effect_type: crit_damage_modifier`
- `value_percent`
- `value_mode: additive_percent`
- `can_be_negative: true`
- `active_when`
- `stat_cap`

## 6. Шанс критического удара

Тип: параметрический эффект.

Что делает: повышает или уменьшает шанс критического удара.

Текст для игрока: изменяет шанс нанести критический удар.

Формула:

`final_crit_chance = min(base_crit_chance + crit_chance_bonus, 49%)`

Баланс:

- обычные предметы: +1-2%;
- редкие: +2-4%;
- эпические: +4-6%;
- общий максимум: 49%;
- минимум: 0%.

Поля конструктора:

- `effect_type: crit_chance_modifier`
- `value_percent`
- `min_value: 0`
- `max_value: 49`
- `can_be_negative: true`

## 7. Физическая защита

Тип: параметрический эффект.

Что делает: повышает или уменьшает защиту от физического урона.

Текст для игрока: изменяет защиту от физического урона.

Формула:

`final_physical_defense = base_physical_defense + flat_bonus + base_physical_defense * percent_bonus / 100`

Баланс:

- фиксированный бонус подходит для брони низких уровней;
- процентный бонус подходит для редких, эпических и уникальных предметов;
- защита не должна уходить ниже 0.

Поля конструктора:

- `effect_type: physical_defense_modifier`
- `flat_bonus`
- `percent_bonus`
- `can_be_negative: true`
- `min_value: 0`

## 8. Магическая защита

Тип: параметрический эффект.

Что делает: повышает или уменьшает защиту от магического урона.

Текст для игрока: изменяет защиту от магического урона.

Формула:

`final_magic_defense = base_magic_defense + flat_bonus + base_magic_defense * percent_bonus / 100`

Баланс:

- обычные предметы: небольшой фиксированный бонус;
- редкие и выше: фиксированный бонус + небольшой процент;
- процентный бонус обычно +1-15%.

Поля конструктора:

- `effect_type: magic_defense_modifier`
- `flat_bonus`
- `percent_bonus`
- `can_be_negative: true`
- `min_value: 0`

## 9. Точность

Тип: параметрический эффект.

Что делает: повышает или уменьшает шанс попасть по цели.

Текст для игрока: изменяет точность атак.

Формула:

`final_accuracy = clamp(base_accuracy + accuracy_bonus, 5%, 95%)`

Баланс:

- обычные предметы: +1-3%;
- редкие: +3-6%;
- эпические: +6-10%;
- минимум 5%, максимум 95%.

Поля конструктора:

- `effect_type: accuracy_modifier`
- `value_percent`
- `min_value: 5`
- `max_value: 95`
- `can_be_negative: true`

## 10. Уклонение

Тип: параметрический эффект.

Что делает: повышает или уменьшает шанс уклониться от атаки.

Текст для игрока: изменяет шанс уклониться от атаки.

Формула:

`final_dodge = clamp(base_dodge + dodge_bonus, 0%, 35%)`

Баланс:

- обычные предметы: +1-2%;
- редкие: +2-4%;
- эпические: +4-6%;
- максимум уклонения: 35%.

Поля конструктора:

- `effect_type: dodge_modifier`
- `value_percent`
- `min_value: 0`
- `max_value: 35`
- `can_be_negative: true`

## 11. Сила

Тип: бонус к характеристике.

Формула:

`final_strength = base_strength + flat_bonus + base_strength * percent_bonus / 100`

Баланс: обычные +1-3, редкие +3-7, эпические +7-12, уникальные вручную. Минимум характеристики: 1.

Поля: `effect_type: stat_modifier`, `stat: strength`, `flat_bonus`, `percent_bonus`, `can_be_negative`, `min_value: 1`.

## 12. Мудрость

Тип: бонус к характеристике.

Формула:

`final_wisdom = base_wisdom + flat_bonus + base_wisdom * percent_bonus / 100`

Баланс: обычные +1-3, редкие +3-7, эпические +7-12, уникальные вручную. Минимум: 1.

Поля: `effect_type: stat_modifier`, `stat: wisdom`, `flat_bonus`, `percent_bonus`, `can_be_negative`, `min_value: 1`.

## 13. Выносливость

Тип: бонус к характеристике.

Формула:

`final_endurance = base_endurance + flat_bonus + base_endurance * percent_bonus / 100`

Баланс: обычные +1-3, редкие +3-7, эпические +7-12, уникальные вручную. Минимум: 1.

Поля: `effect_type: stat_modifier`, `stat: endurance`, `flat_bonus`, `percent_bonus`, `can_be_negative`, `min_value: 1`.

## 14. Ловкость

Тип: бонус к характеристике.

Формула:

`final_agility = base_agility + flat_bonus + base_agility * percent_bonus / 100`

Баланс: обычные +1-3, редкие +3-7, эпические +7-12, уникальные вручную. Минимум: 1.

Поля: `effect_type: stat_modifier`, `stat: agility`, `flat_bonus`, `percent_bonus`, `can_be_negative`, `min_value: 1`.

## 15. Восприятие

Тип: бонус к характеристике.

Формула:

`final_perception = base_perception + flat_bonus + base_perception * percent_bonus / 100`

Баланс: обычные +1-3, редкие +3-7, эпические +7-12, уникальные вручную. Минимум: 1.

Поля: `effect_type: stat_modifier`, `stat: perception`, `flat_bonus`, `percent_bonus`, `can_be_negative`, `min_value: 1`.

## 16. Интеллект

Тип: бонус к характеристике.

Формула:

`final_intelligence = base_intelligence + flat_bonus + base_intelligence * percent_bonus / 100`

Баланс: обычные +1-3, редкие +3-7, эпические +7-12, уникальные вручную. Минимум: 1.

Поля: `effect_type: stat_modifier`, `stat: intelligence`, `flat_bonus`, `percent_bonus`, `can_be_negative`, `min_value: 1`.

## 17. Дополнительный слот инвентаря

Тип: пассивное свойство предмета.

Что делает: увеличивает количество доступных слотов инвентаря, пока предмет активен или экипирован.

Текст для игрока: добавляет дополнительные места в инвентаре.

Формула:

`final_inventory_slots = base_inventory_slots + bonus_inventory_slots`

Баланс:

- обычный предмет: +1 слот;
- редкий: +2-3;
- эпический: +3-5;
- артефакт/уникальный предмет: вручную.

Ограничения:

- при снятии предмета нужно обработать переполнение инвентаря;
- варианты: запретить снятие, заблокировать получение новых предметов, временное хранилище;
- одинаковые предметы не должны давать бесконечные слоты.

Поля конструктора:

- `effect_type: inventory_slot_bonus`
- `bonus_slots`
- `active_when: equipped / special_slot / activated`
- `stack_rule: strongest_only / stack_limited / unique_only`
- `on_remove_overflow_rule`

---

# 3. Боевые статусы, контроль и ответные эффекты

## 18. Поджог

Тип: отрицательный периодический эффект.

Что делает: с шансом поджигает цель. Горение наносит урон каждый ход.

Текст для игрока: цель горит и получает урон каждый ход.

Формулы:

`burn_apply_success = random(1, 100) <= burn_chance`

`burn_damage_per_turn = burn_flat_damage + target_max_hp * burn_percent / 100`

Баланс:

- шанс поджога: 5-25%;
- длительность: 2-4 хода;
- слабый: 1-2% max HP;
- обычный: 2-4%;
- сильный: 4-6%;
- выше 6% — только уникальные/боссы/редкие навыки.

Поля: `effect_type: burn`, `apply_chance_percent`, `duration_turns`, `flat_damage`, `percent_max_hp_damage`, `stack_rule`, `can_be_cleansed`, `cleanse_tags: burn, fire, negative_effect`.

## 19. Оглушение

Тип: отрицательный контроль.

Что делает: с шансом оглушает цель. Оглушённая цель пропускает ход и не может использовать основные и дополнительные действия.

Текст для игрока: цель оглушена и временно не может действовать.

Формула:

`stun_apply_success = random(1, 100) <= stun_chance * (1 - target_stun_resist / 100)`

Баланс:

- обычные предметы: 3-7%;
- редкие: 7-12%;
- эпические: 12-18%;
- длительность обычно 1 ход;
- 2 хода — только для сильных навыков, боссов или уникальных эффектов.

Поля: `effect_type: stun`, `apply_chance_percent`, `duration_turns`, `blocks_main_action`, `blocks_bonus_action`, `blocks_escape`, `resist_stat`, `immunity_after_effect_turns`, `boss_effectiveness_percent`.

## 20. Отражение

Тип: защитный ответный эффект против магического урона.

Что делает: возвращает часть полученного магического урона атакующему.

Текст для игрока: часть полученного магического урона возвращается атакующему.

Формула:

`reflected_damage = received_magic_damage * reflect_percent / 100`

Баланс:

- слабое: 3-5%;
- обычное: 5-10%;
- сильное: 10-15%;
- выше 15-20% — уникальные предметы или временные бафы.

Ограничения: отражённый урон не отражается повторно и не запускает эффекты удара.

Поля: `effect_type: magic_reflect`, `trigger: on_receive_magic_damage`, `reflect_percent`, `flat_reflect_damage`, `max_reflect_per_hit`, `can_trigger_effects: false`, `can_be_reflected: false`.

## 21. Шипы

Тип: защитный ответный эффект против физического урона.

Что делает: возвращает часть полученного физического урона атакующему.

Формула:

`thorn_damage = received_physical_damage * thorns_percent / 100`

Баланс: 3-5% слабые, 5-10% обычные, 10-15% сильные, выше — уникальные или временные.

Поля: `effect_type: thorns`, `trigger: on_receive_physical_damage`, `thorns_percent`, `flat_thorns_damage`, `max_thorns_per_hit`, `can_trigger_effects: false`, `can_be_reflected: false`.

## 22. Поглощение магии

Тип: восстановление ресурса при атаке.

Что делает: при нанесении урона поглощает часть маны цели и передаёт атакующему.

Формулы:

`mana_absorbed = min(target_current_mana, damage_dealt * absorb_percent / 100 + flat_absorb)`

`attacker_current_mana = min(attacker_max_mana, attacker_current_mana + mana_absorbed)`

Баланс: 2-4% слабое, 4-8% обычное, 8-12% сильное, выше 12-15% — уникальные.

Поля: `effect_type: mana_absorb`, `trigger: on_deal_damage`, `resource: mana`, `absorb_percent_from_damage`, `flat_absorb`, `max_absorb_per_hit`, `works_with_damage_types`, `works_with_periodic_damage: false`, `works_with_reflected_damage: false`.

## 23. Поглощение жизни

Тип: вампиризм.

Что делает: при нанесении урона восстанавливает атакующему часть здоровья.

Формулы:

`hp_absorbed = damage_dealt * lifesteal_percent / 100 + flat_lifesteal`

`attacker_current_hp = min(attacker_max_hp, attacker_current_hp + hp_absorbed)`

Баланс: 2-4% слабое, 4-8% обычное, 8-12% сильное, выше — редкие навыки/артефакты.

Поля: `effect_type: lifesteal`, `trigger: on_deal_damage`, `resource: hp`, `absorb_percent_from_damage`, `flat_absorb`, `max_absorb_per_hit`, `works_with_area_damage`, `area_damage_effectiveness_percent`, `works_with_periodic_damage: false`.

## 24. Поглощение духа

Тип: восстановление ресурса при атаке.

Что делает: при нанесении урона поглощает часть духа цели и передаёт атакующему.

Формулы:

`spirit_absorbed = min(target_current_spirit, damage_dealt * absorb_percent / 100 + flat_absorb)`

`attacker_current_spirit = min(attacker_max_spirit, attacker_current_spirit + spirit_absorbed)`

Баланс: 2-4% слабое, 4-8% обычное, 8-12% сильное, выше — уникальные.

Поля: `effect_type: spirit_absorb`, `trigger: on_deal_damage`, `resource: spirit`, `absorb_percent_from_damage`, `flat_absorb`, `max_absorb_per_hit`, `works_with_periodic_damage: false`, `works_with_reflected_damage: false`.

## 25. Аура характеристики

Тип: групповая боевая аура.

Что делает: повышает выбранную характеристику союзникам в бою. Один общий тип эффекта используется для аур Силы, Мудрости, Выносливости, Ловкости, Восприятия и Интеллекта.

Текст для игрока: усиливает выбранную характеристику союзников в бою.

Формула:

`ally_final_stat = ally_base_stat + aura_flat_bonus + ally_base_stat * aura_percent_bonus / 100`

Баланс:

- слабая: +1-3 или +1-3%;
- обычная: +3-6 или +3-5%;
- сильная: +6-10 или +5-8%;
- выше — редкие навыки, гильдейские эффекты, мировые события.

Поля:

- `effect_type: aura_stat_modifier`
- `stat: strength / wisdom / endurance / agility / perception / intelligence`
- `target_group: allies / self_and_allies / party / raid`
- `flat_bonus`
- `percent_bonus`
- `duration`
- `active_when: in_battle`
- `stack_rule: strongest_only / unique_only / stack_limited`

Варианты названий: Аура Силы, Аура Мудрости, Аура Выносливости, Аура Ловкости, Аура Восприятия, Аура Интеллекта.

## 26. Заморозка

Тип: отрицательный боевой эффект.

Что делает: снижает точность и уклонение цели на несколько ходов.

Текст для игрока: цель заморожена: её точность и уклонение снижены.

Формулы:

`final_accuracy = max(min_accuracy, base_accuracy - freeze_accuracy_penalty)`

`final_dodge = max(0, base_dodge - freeze_dodge_penalty)`

Баланс: слабая -3-5%, обычная -5-10%, сильная -10-15%, выше — уникальные/боссы/сильные навыки.

Поля: `effect_type: freeze`, `apply_chance_percent`, `duration_turns`, `accuracy_penalty_percent`, `dodge_penalty_percent`, `stack_rule`, `cleanse_tags: freeze, cold, negative_effect`, `resist_stat: cold_resistance`.

## 27. Взрыв после смерти

Тип: посмертный боевой эффект / взрыв трупа.

Что делает: с шансом при смерти владельца или цели происходит взрыв тела. Взрыв наносит небольшой урон союзникам погибшего и повышенный урон его противникам. После взрыва тело считается уничтоженным.

Текст для игрока: после смерти может произойти взрыв, наносящий урон окружающим. Тело после взрыва уничтожается.

Формулы:

`corpse_explosion_success = random(1, 100) <= explosion_chance`

`enemy_damage = explosion_flat_damage + dead_unit_max_hp * enemy_damage_percent / 100`

`ally_damage = enemy_damage * ally_damage_multiplier / 100`

Баланс: шанс 5-20%, урон противникам 5-15% max HP погибшего, союзникам 10-30% от урона по противникам.

Ограничения:

- срабатывает один раз при смерти;
- после взрыва тело получает статус `corpse_destroyed`;
- эффекты поднятия трупов и воскрешения через тело не работают;
- не запускает вампиризм, шипы, отражение, поджог, яд.

Поля: `effect_type: corpse_explosion`, `trigger: on_death`, `apply_chance_percent`, `enemy_percent_dead_unit_max_hp_damage`, `ally_damage_multiplier_percent`, `corpse_state_after_trigger: destroyed`, `blocks_corpse_raise: true`, `blocks_corpse_resurrection: true`, `can_trigger_effects: false`.

## 28. Пробой

Тип: атакующий эффект / частичное игнорирование защиты.

Что делает: малая часть наносимого урона игнорирует физическую и/или магическую защиту цели.

Формулы:

`bypass_damage = raw_damage * penetration_percent / 100`

`normal_damage = raw_damage - bypass_damage`

`final_damage = bypass_damage + damage_after_defense(normal_damage, target_defense)`

Баланс: 3-5% слабый, 5-10% обычный, 10-15% сильный, выше 15-20% — уникальное оружие/редкие навыки.

Поля: `effect_type: penetration`, `penetration_percent`, `penetrates: physical_defense / magic_defense / both`, `works_with_damage_types`, `works_with_periodic_damage`, `max_penetration_percent`.

## 29. Кровотечение

Тип: отрицательный периодический эффект.

Что делает: наносит физический периодический урон цели раз в ход. Может складываться ограниченное количество раз.

Формулы:

`bleed_damage_per_stack = bleed_flat_damage + target_max_hp * bleed_percent / 100`

`total_bleed_damage = bleed_damage_per_stack * current_stacks`

Баланс: 0.5-1.5% за стак слабое, 1.5-3% обычное, 3-4% сильное; максимум обычно 3 стака; длительность 2-5 ходов.

Ограничения: может не работать на нежить, големов, механизмы; снимается очищением, перевязкой, регенерацией или остановкой крови.

Поля: `effect_type: bleed`, `apply_chance_percent`, `duration_turns`, `flat_damage_per_stack`, `percent_max_hp_damage_per_stack`, `stack_rule: stack_limited`, `max_stacks`, `immune_target_tags: undead, construct, spirit`, `can_trigger_effects: false`.

## 30. Аура регенерации

Тип: групповая положительная аура.

Что делает: каждый ход восстанавливает здоровье всем союзникам владельца ауры.

Формула:

`heal_per_turn = aura_flat_heal + ally_max_hp * aura_heal_percent / 100`

Баланс: 0.3-0.5% слабая, 0.5-1% обычная, 1-1.5% сильная, выше — редкие навыки/гильдии/уникальные предметы.

Поля: `effect_type: regeneration_aura`, `target_group`, `flat_heal`, `percent_max_hp_heal`, `tick_interval: each_turn`, `duration`, `max_targets`, `stack_rule`, `active_when: in_battle`.

## 31. Живая броня

Тип: защитный накопительный барьер.

Что делает: каждый ход на владельце нарастает слой живой брони. Живая броня поглощает часть входящего урона. Каждый полученный удар снимает часть накопленной живой брони.

Формулы:

`living_armor_gain = armor_flat_gain + owner_max_hp * armor_gain_percent / 100`

`living_armor_max = owner_max_hp * armor_cap_percent / 100`

`absorbed_damage = min(incoming_damage * absorb_percent / 100, current_living_armor)`

`final_damage = incoming_damage - absorbed_damage`

`current_living_armor = current_living_armor - absorbed_damage - armor_loss_per_hit`

Баланс: прирост 0.5-2% max HP за ход, максимум 5-15% max HP, поглощение 20-50% пока есть запас.

Поля: `effect_type: living_armor`, `flat_gain_per_turn`, `percent_max_hp_gain_per_turn`, `armor_cap_percent_max_hp`, `absorb_percent`, `armor_loss_per_hit`, `works_against_damage_types`, `works_against_periodic_damage`, `reset_after_battle`.

## 32. Аура разложения

Тип: отрицательная аура периодического урона.

Что делает: каждый ход наносит периодический урон выбранной группе целей: врагам, союзникам, всем вокруг или владельцу тоже.

Формула:

`decay_damage_per_turn = decay_flat_damage + target_max_hp * decay_percent / 100`

Баланс: 0.5-1% слабая, 1-2% обычная, 2-3% сильная, выше — проклятые предметы/боссы/мировые события.

Поля: `effect_type: decay_aura`, `target_group`, `flat_damage`, `percent_max_hp_damage`, `tick_interval`, `duration`, `stack_rule`, `can_trigger_effects: false`, `can_be_reflected: false`.

## 33. Туманный покров

Тип: поле боя / аура снижения точности.

Что делает: создаёт облако тумана, которое снижает точность атак выбранной группы.

Формула:

`final_accuracy = max(min_accuracy, base_accuracy - fog_accuracy_penalty)`

Баланс: -3-5% слабый, -5-10% обычный, -10-15% сильный, выше — сильные навыки/редкие предметы.

Поля: `effect_type: fog_cover`, `target_group`, `accuracy_penalty_percent`, `duration_turns`, `min_accuracy`, `field_effect: true`, `stack_rule`, `can_be_dispersed`, `dispel_tags`.

## 34. Тень прошлого

Тип: призыв / повтор прошлого действия.

Что делает: с шансом призывает тень владельца эффекта. Тень повторяет одно или несколько прошлых действий владельца в течение нескольких ходов.

Формулы:

`shadow_summon_success = random(1, 100) <= shadow_chance`

`shadow_action_power = original_action_power * shadow_power_percent / 100`

Баланс: шанс 3-10%, длительность 1-3 хода, сила 30-60% от оригинала; до 75% только уникальные.

Ограничения: тень не повторяет зелья, побег, смерть, воскрешение, призыв другой тени и расходники.

Поля: `effect_type: past_shadow`, `trigger`, `summon_chance_percent`, `duration_turns`, `shadow_power_percent`, `repeat_action_count_per_turn`, `allowed_repeated_actions`, `forbidden_repeated_actions`, `cooldown_turns`.

## 35. Печать бессмертного

Тип: спасение от смерти / аварийный защитный эффект.

Что делает: когда здоровье владельца падает до 1% или ниже, эффект спасает владельца и восстанавливает часть HP, маны и духа.

Условие:

`current_hp <= max_hp * 0.01`

Формулы:

`hp_restore = max_hp * 20 / 100`

`mana_restore = max_mana * 20 / 100`

`spirit_restore = max_spirit * 20 / 100`

Баланс: восстановление 10-20%; срабатывание 1 раз за бой, 1 раз в несколько часов или одноразовое уничтожение предмета.

Поля: `effect_type: immortal_seal`, `trigger: on_hp_threshold`, `hp_threshold_percent: 1`, `restore_hp_percent`, `restore_mana_percent`, `restore_spirit_percent`, `charges`, `cooldown_turns`, `consume_item_on_trigger`, `can_trigger_once_per_battle`.

## 36. Неуязвимость

Тип: временная полная защита.

Что делает: с шансом накладывает неуязвимость. Пока эффект активен, владелец не получает новый входящий урон. Уже висящие периодические эффекты продолжают наносить урон, если отдельно не указано очищение.

Формулы:

`invulnerability_success = random(1, 100) <= invulnerability_chance`

`final_incoming_damage = 0`

Баланс: шанс 2-8%, длительность обычно 1 ход, 2 хода — редкие навыки/артефакты/боссы.

Поля: `effect_type: invulnerability`, `trigger`, `apply_chance_percent`, `duration_turns`, `blocks_new_physical_damage`, `blocks_new_magic_damage`, `blocks_new_pure_damage`, `blocks_periodic_damage_already_active: false`, `cooldown_turns`, `immunity_after_effect_turns`.

## 37. Быстрые руки

Тип: боевое свойство / увеличение дополнительных действий.

Что делает: увеличивает количество дополнительных действий в бою.

Формула:

`final_bonus_actions = base_bonus_actions + bonus_action_count`

Баланс: +1 дополнительное действие — обычный максимум; +2 только для уникальных предметов, временных бафов или редких навыков.

Ограничения: не увеличивает основные действия; не должен давать бесконечно пить зелья или использовать метательные предметы; лимит 2-3 дополнительных действия за ход.

Поля: `effect_type: bonus_action_modifier`, `bonus_action_count`, `allowed_bonus_action_types`, `max_bonus_actions_per_turn`, `stack_rule`, `works_in_pve`, `works_in_pvp`.

## 38. Хранилище маны

Тип: пассивное увеличение ресурса.

Формула:

`final_max_mana = base_max_mana + flat_bonus + base_max_mana * percent_bonus / 100`

Баланс: +2-5% обычные, +5-10% редкие, +10-15% эпические, до 20-25% уникальные.

Поля: `effect_type: max_resource_modifier`, `resource: mana`, `flat_bonus`, `percent_bonus`, `on_remove_resource_rule: clamp_to_new_max`.

## 39. Хранилище жизни

Тип: пассивное увеличение ресурса.

Формула:

`final_max_hp = base_max_hp + flat_bonus + base_max_hp * percent_bonus / 100`

Баланс: +2-5% обычные, +5-10% редкие, +10-15% эпические, до 20-25% уникальные.

Поля: `effect_type: max_resource_modifier`, `resource: hp`, `flat_bonus`, `percent_bonus`, `on_remove_resource_rule: clamp_to_new_max`.

## 40. Хранилище духа

Тип: пассивное увеличение ресурса.

Формула:

`final_max_spirit = base_max_spirit + flat_bonus + base_max_spirit * percent_bonus / 100`

Баланс: +2-5% обычные, +5-10% редкие, +10-15% эпические, до 20-25% уникальные.

Поля: `effect_type: max_resource_modifier`, `resource: spirit`, `flat_bonus`, `percent_bonus`, `on_remove_resource_rule: clamp_to_new_max`.

## 41. Клон

Тип: боевой призыв / копия владельца.

Что делает: с небольшим шансом призывает клона владельца, который сражается на его стороне. Клон имеет те же навыки, но в ослабленном варианте, а также 50% здоровья, маны и духа от оригинала.

Формулы:

`clone_summon_success = random(1, 100) <= clone_chance`

`clone_max_hp = owner_max_hp * clone_hp_percent / 100`

`clone_max_mana = owner_max_mana * clone_mana_percent / 100`

`clone_max_spirit = owner_max_spirit * clone_spirit_percent / 100`

`clone_skill_power = owner_skill_power * clone_power_percent / 100`

Баланс: шанс 2-8%, длительность 2-4 хода, ресурсы 30-50%, сила навыков 30-60%.

Ограничения: клон не призывает клона, не использует расходники, не копирует воскрешение, печать бессмертия, взрыв после смерти и сильные уникальные эффекты.

Поля: `effect_type: clone_summon`, `trigger`, `summon_chance_percent`, `duration_turns`, `clone_hp_percent_owner`, `clone_mana_percent_owner`, `clone_spirit_percent_owner`, `clone_skill_power_percent`, `max_active_clones`, `clone_can_use_items: false`, `clone_can_summon_clone: false`, `forbidden_effects`, `pvp_effectiveness_percent`.

## 42. Скрытность

Тип: локационный пассивный эффект.

Что делает: уменьшает шанс выпадения PVP и PVE боёв на локации.

Формула:

`final_battle_chance = base_battle_chance * (1 - stealth_percent / 100)`

Баланс: -3-5% слабая, -5-10% обычная, -10-15% сильная, выше — уникальные/бафы.

Ограничения: не убирает шанс боя полностью; минимальный шанс 5-10% от базового; не влияет на сюжетные/обязательные бои.

Поля: `effect_type: encounter_chance_modifier`, `encounter_type: pve_battle / pvp_battle / both`, `modifier_percent`, `mode: decrease`, `min_final_chance_percent`, `ignored_encounter_tags`.

## 43. Следопыт

Тип: локационный пассивный эффект.

Что делает: увеличивает шанс выпадения событий, не связанных с боем: находки, ресурсы, следы, травы, руды, сундуки, особые места.

Формула:

`final_non_combat_event_chance = base_non_combat_event_chance * (1 + tracker_percent / 100)`

Баланс: +3-5% слабый, +5-10% обычный, +10-15% сильный, выше — редкие/уникальные.

Поля: `effect_type: non_combat_event_chance_modifier`, `modifier_percent`, `affected_event_tags`, `rare_event_effectiveness_percent`, `works_in_locations`, `ignored_event_tags`.

---

# 4. Хрупкость и отрицательные ресурсы

## 44. Хрупкость

Тип: ограничивающее свойство предмета / разрушение после срабатывания.

Что делает: если на предмете срабатывает заданный эффект, предмет безвозвратно разрушается.

Текст для игрока: предмет может разрушиться после срабатывания своего эффекта.

Формула:

`if linked_effect_triggered == true and fragile_enabled == true: destroy_item()`

Баланс: подходит для сильных одноразовых или почти одноразовых предметов: спасение от смерти, неуязвимость, мощное очищение, взрыв после смерти, призыв клона, редкий артефактный эффект.

Ограничения: предмет уничтожается без возврата ресурсов; снимается из слота; событие пишется в лог; можно добавить шанс разрушения.

Поля: `effect_type: item_fragility`, `trigger`, `linked_effect_id`, `destroy_chance_percent`, `destroy_item_on_trigger: true`, `return_resources_on_destroy: false`, `remove_from_equipment_slot: true`, `show_warning_to_player`, `log_destroy_event`.

## 45. Утечка маны

Тип: отрицательный модификатор максимального ресурса.

Что делает: снижает максимальный запас маны.

Формула:

`final_max_mana = base_max_mana - flat_penalty - base_max_mana * percent_penalty / 100`

Баланс: -2-5% слабое, -5-10% обычное, -10-15% сильное, выше — проклятые предметы/мощные эффекты с ценой.

Поля: `effect_type: max_resource_modifier`, `resource: mana`, `flat_bonus: negative_value`, `percent_bonus: negative_value`, `min_resource_value`, `max_total_penalty_percent`, `on_apply_resource_rule: clamp_to_new_max`.

## 46. Истощение жизни

Тип: отрицательный модификатор максимального ресурса.

Что делает: снижает максимальный запас здоровья.

Формула:

`final_max_hp = base_max_hp - flat_penalty - base_max_hp * percent_penalty / 100`

Баланс: -2-5% слабое, -5-10% обычное, -10-15% сильное, выше — проклятые предметы/мощные эффекты с ценой.

Ограничение: не должно убивать игрока напрямую снижением максимального HP.

Поля: `effect_type: max_resource_modifier`, `resource: hp`, `flat_bonus: negative_value`, `percent_bonus: negative_value`, `min_resource_value: 1`, `cannot_kill_by_max_hp_reduction: true`.

## 47. Ослабление духа

Тип: отрицательный модификатор максимального ресурса.

Что делает: снижает максимальный запас духа.

Формула:

`final_max_spirit = base_max_spirit - flat_penalty - base_max_spirit * percent_penalty / 100`

Баланс: -2-5% слабое, -5-10% обычное, -10-15% сильное, выше — проклятые предметы/дебафы.

Поля: `effect_type: max_resource_modifier`, `resource: spirit`, `flat_bonus: negative_value`, `percent_bonus: negative_value`, `min_resource_value`, `max_total_penalty_percent`, `on_apply_resource_rule: clamp_to_new_max`.

---

# 5. Посмертные проклятья и долгие проклятые эффекты

## 5.1. Общая механика долгих проклятий

Тип: долгий отрицательный эффект.

Что делает: проклятья могут накладываться при смерти в PVP, а также мобами, предметами, ловушками, событиями, алтарями, неправильными действиями игрока или проклятыми локациями.

Длительность:

- слабое: 1-6 часов;
- обычное: 6-24 часа;
- сильное: 1-3 дня;
- тяжёлое: 3-7 дней;
- уникальное/сюжетное: вручную.

Общие поля:

- `effect_type: long_curse`
- `curse_id`
- `curse_name`
- `source: pvp_death / mob / item / trap / event / location / admin`
- `apply_chance_percent`
- `duration_seconds`
- `duration_mode: fixed / random_range / manual`
- `stack_rule`
- `can_be_cleansed`
- `cleanse_methods: potion / priest / ritual / quest / admin`
- `works_on_bot_actions`
- `show_to_player: true`
- `log_event: true`

## 5.2. Правило достижения для PVP

Посмертные проклятья в PVP могут накладывать только те игроки, у которых есть достижение «Проклятье? Какое проклятье?».

Проклятья от мобов, предметов, ловушек, событий, неправильных действий, локаций, алтарей и ритуалов достижения не требуют.

Проверка:

`if source == "pvp_death" and dead_player.has_achievement("Проклятье? Какое проклятье?") == true: allow_curse()`

`else if source == "pvp_death": block_curse()`

Для остальных источников:

`if source in ["mob", "boss", "item", "trap", "event", "wrong_action", "location", "altar", "ritual"]: allow_curse_without_achievement()`

Поля конструктора:

- `curse_source`
- `requires_achievement`
- `required_achievement_name`
- `achievement_checked_on: dead_player / caster / target / none`
- `achievement_required_only_for_source: pvp_death`
- `if_missing_achievement: block_effect / ignore_requirement`

Правило по умолчанию:

- для `pvp_death`: `requires_achievement: true`;
- для всех остальных источников: `requires_achievement: false`.

## 48. Проклятье неуклюжести

Тип: долгий проклятый эффект на действия в боте.

Что делает: при любых действиях в боте игрок имеет шанс потерять небольшое количество монет.

Формулы:

`coin_loss_success = random(1, 100) <= coin_loss_chance`

`coins_lost = min(player_coins, flat_coin_loss + player_level * level_coin_multiplier)`

Баланс: шанс 3-10% на действие; потеря небольшая; нужен максимум потери в день.

Поля: `effect_type: curse_clumsiness`, `trigger: on_bot_action`, `coin_loss_chance_percent`, `flat_coin_loss`, `level_coin_multiplier`, `max_loss_per_trigger`, `max_loss_per_day`, `affected_actions`, `ignored_actions`.

## 49. Путаница

Тип: проклятый боевой контроль.

Что делает: с шансом следующая атака игрока поражает случайного союзника вместо врага.

Формула:

`confusion_success = random(1, 100) <= confusion_chance`

Баланс: шанс 5-15%, длительность 3-10 ходов или несколько боёв. Не срабатывает, если союзников нет.

Поля: `effect_type: curse_confusion`, `trigger: on_attack`, `redirect_chance_percent`, `redirect_target: random_ally`, `works_with_basic_attack`, `works_with_skills`, `works_with_area_damage: false`.

## 50. Проклятье уязвимости

Тип: долгий отрицательный модификатор получаемого урона.

Что делает: увеличивает весь получаемый урон.

Формула:

`final_received_damage = incoming_damage * (1 + vulnerability_percent / 100)`

Баланс: +3-5% слабое, +5-10% обычное, +10-15% сильное, выше — тяжёлые проклятия.

Поля: `effect_type: curse_vulnerability`, `damage_taken_percent`, `affected_damage_types`, `stack_rule`, `max_total_penalty_percent`.

## 51. Гниение духа

Тип: проклятье максимального ресурса.

Что делает: снижает максимальный запас духа.

Формула:

`final_max_spirit = base_max_spirit * (1 - spirit_penalty_percent / 100) - flat_penalty`

Баланс: -5-15% max spirit; тяжёлые версии до -20%.

Поля: `effect_type: max_resource_modifier`, `resource: spirit`, `percent_bonus: negative_value`, `flat_bonus: negative_value`, `source_type: curse`, `on_apply_resource_rule: clamp_to_new_max`.

## 52. Затмение разума

Тип: проклятье максимального ресурса.

Что делает: снижает максимальный запас маны.

Формула:

`final_max_mana = base_max_mana * (1 - mana_penalty_percent / 100) - flat_penalty`

Баланс: -5-15% max mana; тяжёлые версии до -20%.

Поля: `effect_type: max_resource_modifier`, `resource: mana`, `percent_bonus: negative_value`, `flat_bonus: negative_value`, `source_type: curse`.

## 53. Иссушение

Тип: проклятье максимального ресурса.

Что делает: снижает максимальный запас здоровья.

Формула:

`final_max_hp = base_max_hp * (1 - hp_penalty_percent / 100) - flat_penalty`

Баланс: -5-15% max HP; тяжёлые версии до -20%. Не должно убивать игрока напрямую.

Поля: `effect_type: max_resource_modifier`, `resource: hp`, `percent_bonus: negative_value`, `flat_bonus: negative_value`, `source_type: curse`, `cannot_kill_by_max_hp_reduction: true`.

## 54. Клятва поражения

Тип: нарастающее проклятье смерти.

Что делает: пока проклятье действует, каждая смерть игрока накладывает дополнительные проклятья.

Формула:

`extra_curse_count = base_extra_curses + death_count_during_curse * curse_growth_per_death`

Баланс: при смерти добавлять 1 слабое проклятье; шанс 30-100%; нужен максимум дополнительных проклятий.

Поля: `effect_type: curse_defeat_oath`, `trigger: on_player_death`, `extra_curse_chance_percent`, `extra_curse_count`, `curse_pool`, `max_extra_curses`, `increase_duration_on_death`.

## 55. Печать смерти

Тип: тяжёлое проклятье смерти.

Что делает: следующая смерть во время действия проклятья приводит к потере 1 уровня.

Формула:

`if player_dies and curse_active: player_level = max(1, player_level - 1)`

Баланс: длительность 6-24 часа, 1-3 дня только для тяжёлых источников. Нужно предупреждение и способ снятия.

Поля: `effect_type: curse_death_mark`, `trigger: on_player_death`, `level_loss: 1`, `min_level_after_loss: 1`, `consume_curse_on_trigger: true`, `show_high_risk_warning: true`, `pvp_abuse_protection: true`.

## 56. Осквернённая кровь

Тип: проклятье лечения.

Что делает: все исцеляющие эффекты работают слабее.

Формула:

`final_healing = incoming_healing * (1 - healing_reduction_percent / 100)`

Баланс: -10% слабое, -20-30% обычное, -40% сильное, выше 50% только коротко.

Поля: `effect_type: curse_healing_reduction`, `healing_reduction_percent`, `affected_heal_types`, `min_healing_percent`, `can_affect_lifesteal`.

## 57. Проклятье одиночества

Тип: запрет союзных положительных эффектов.

Что делает: союзники не могут накладывать на цель положительные эффекты.

Формула:

`if buff_source == ally and target_has_curse: block_buff()`

Баланс: сильное проклятье; лучше 1-12 часов или 3-5 ходов в бою.

Поля: `effect_type: curse_loneliness`, `blocks_positive_effects_from_allies: true`, `blocks_healing_from_allies`, `blocks_cleansing_from_allies: false`, `allow_self_buffs`, `blocked_effect_tags`.

## 58. Оковы судьбы

Тип: проклятье ограничения экипировки.

Что делает: запрещает смену экипировки на время действия проклятия.

Формула:

`if curse_active and action == change_equipment: block_action()`

Баланс: 10-30 минут слабое, 1-6 часов обычное, до 24 часов сильное. На неделю — только сюжетно и со способом снятия.

Поля: `effect_type: curse_equipment_lock`, `blocked_actions: equip / unequip / swap`, `allowed_slots_exception`, `allow_broken_item_auto_remove`, `can_be_cleansed`.

## 59. Тьма веков

Тип: проклятье всех характеристик.

Что делает: снижает все основные характеристики на процент.

Формула:

`final_stat = base_stat * (1 - all_stats_penalty_percent / 100)`

Баланс: -2-3% слабое, -3-7% обычное, -7-10% сильное, выше — тяжёлые проклятия.

Поля: `effect_type: curse_all_stats_modifier`, `affected_stats`, `percent_penalty`, `flat_penalty`, `min_stat_value: 1`, `stack_rule: strongest_only`.

## 60. Проклятая душа

Тип: проклятье опыта.

Что делает: серьёзно уменьшает получение опыта во время действия проклятия.

Формула:

`final_experience_gain = base_experience_gain * (1 - experience_penalty_percent / 100)`

Баланс: -10-20% слабое, -20-40% обычное, -40-60% тяжёлое, выше 60% не использовать надолго.

Поля: `effect_type: curse_experience_gain_modifier`, `experience_penalty_percent`, `affected_sources`, `min_experience_gain_percent`, `duration_seconds`.

## 61. Тень предателя

Тип: проклятый боевой призыв против владельца.

Что делает: с высоким шансом в бою на стороне противников появляется тень игрока, которая несколько ходов сражается против него.

Формулы:

`traitor_shadow_success = random(1, 100) <= shadow_spawn_chance`

`shadow_power = player_power * shadow_power_percent / 100`

Баланс: шанс 15-40% на начало боя, длительность 2-4 хода, сила 30-60% от игрока. В PVP отключить или сильно ослабить.

Поля: `effect_type: curse_traitor_shadow`, `trigger: on_battle_start`, `spawn_chance_percent`, `duration_turns`, `shadow_power_percent`, `shadow_hp_percent_owner`, `max_spawns_per_battle: 1`, `works_in_pvp: false/limited`, `forbidden_copied_effects`.

## 62. Пустые карманы

Тип: торговое проклятье.

Что делает: при каждой сделке теряется небольшая часть монет.

Формула:

`lost_coins = transaction_value * loss_percent / 100 + flat_loss`

Баланс: 1-5% от сделки, тяжёлое до 10%. Не трогать редкие валюты без настройки.

Поля: `effect_type: curse_empty_pockets`, `trigger: on_trade`, `loss_percent`, `flat_loss`, `affected_currencies`, `max_loss_per_transaction`, `show_loss_message: true`.

## 63. Обречённая удача

Тип: проклятье критических ударов.

Что делает: все критические эффекты превращаются в обычные удары.

Формула:

`if attack_is_critical and curse_active: attack_is_critical = false`

Баланс: очень сильное проклятье; длительность 1-12 часов; можно сделать шанс подавления 50-100%.

Поля: `effect_type: curse_critical_suppression`, `trigger: on_critical_roll_success`, `suppress_chance_percent`, `turn_critical_into_normal_hit: true`, `ignored_skill_tags`.

## 64. Паническая атака

Тип: проклятый боевой контроль.

Что делает: при получении урона цель с шансом пытается сбежать с поля боя.

Формула:

`panic_success = random(1, 100) <= panic_chance`

Баланс: шанс 3-10% при получении урона, не чаще 1 раза за ход. В PVP ограничить.

Поля: `effect_type: curse_panic_escape`, `trigger: on_receive_damage`, `panic_chance_percent`, `forced_action: attempt_escape`, `max_triggers_per_turn: 1`, `works_from_periodic_damage: false`, `if_escape_blocked`.

## 65. Беспокойный дух

Тип: проклятье отдыха.

Что делает: не позволяет полностью восстановиться в лагере. HP, мана и дух восстанавливаются максимум до 70%.

Формула:

`camp_recovery_cap = max_resource * 70 / 100`

Баланс: лимит 60-80%, стандарт 70%.

Поля: `effect_type: curse_restless_spirit`, `trigger: on_camp_rest`, `hp_recovery_cap_percent`, `mana_recovery_cap_percent`, `spirit_recovery_cap_percent`, `affected_rest_types`.

## 66. Клятва крови

Тип: проклятье зелий здоровья.

Что делает: каждое использование зелья здоровья вызывает кровотечение.

Формула:

`if used_item_tag == healing_potion: apply_bleed()`

Баланс: кровотечение 1-2% max HP за ход, длительность 2-3 хода, максимум 1-3 стака.

Поля: `effect_type: curse_blood_oath`, `trigger: on_use_item`, `required_item_tags: healing_potion`, `applied_effect: bleed`, `bleed_duration_turns`, `bleed_percent_max_hp`, `max_bleed_stacks`.

## 67. Оковы времени

Тип: проклятье перезарядок / отрицательный эффект навыков.

Что делает: увеличивает откат навыков на фиксированное значение: +1, +2, +3 и так далее.

Текст для игрока: ваши навыки восстанавливаются дольше.

Формула:

`final_cooldown = base_cooldown + cooldown_flat_increase`

Пример: если навык имел откат 3 хода, а проклятье даёт +2, итоговый откат станет 5 ходов.

Баланс:

- слабое: +1 к откату;
- обычное: +2;
- сильное: +3;
- выше +3 — только короткое действие, боссы, ловушки, сильные проклятья или события.

Ограничения: не влияет на обычный удар, если он не имеет отката; не должно делать навык полностью недоступным; при повторном наложении лучше `strongest_only`.

Поля: `effect_type: curse_cooldown_flat_increase`, `cooldown_flat_increase`, `affected_abilities`, `max_final_cooldown`, `stack_rule`, `duration_seconds`, `duration_turns`, `can_be_cleansed`.

## 68. Проклятое касание

Тип: проклятье добычи ресурсов.

Что делает: при сборе ресурсов есть шанс, что небольшая часть добычи обратится в прах.

Формулы:

`ash_success = random(1, 100) <= ash_chance`

`lost_amount = floor(gathered_amount * ash_percent / 100)`

Баланс: шанс 5-15%, потеря 10-30% добытого ресурса, минимум потери 1.

Поля: `effect_type: curse_resource_ash`, `trigger: on_gather_resource`, `ash_chance_percent`, `ash_percent_of_gathered`, `min_loss_amount`, `affected_resource_tags`, `ignored_item_tags: quest, unique, rare_drop`.

## 69. Приманка для чудовищ

Тип: локационное проклятье встреч.

Что делает: повышает вероятность встречи с элитными противниками.

Формула:

`final_elite_chance = base_elite_chance * (1 + elite_chance_bonus_percent / 100)`

Баланс: +10-25% слабое, +25-50% обычное, +50-100% сильное с лимитом сверху.

Поля: `effect_type: curse_elite_encounter_modifier`, `elite_chance_bonus_percent`, `max_final_elite_chance_percent`, `affected_locations`, `ignored_encounter_tags`.

## 70. Волна нашествия

Тип: боевое проклятье призыва врагов.

Что делает: каждые несколько ходов в бою добавляет одного обычного противника.

Формула:

`if current_turn % spawn_interval_turns == 0: spawn_enemy()`

Баланс: интервал 3-5 ходов; максимум 1-3 призванных врага за бой; враг обычный, равный или ниже уровня локации.

Поля: `effect_type: curse_invasion_wave`, `trigger: every_n_turns`, `spawn_interval_turns`, `enemy_pool`, `enemy_level_rule`, `max_spawns_per_battle`, `max_active_spawned_enemies`, `ignored_battle_tags`.

## 71. Тёмный маяк

Тип: локационное проклятье опасных встреч.

Что делает: увеличивает шанс PVP и PVE боёв на локации, особенно с очень сильными противниками.

Формулы:

`final_battle_chance = base_battle_chance * (1 + battle_chance_bonus_percent / 100)`

`enemy_strength_modifier = 1 + strong_enemy_bonus_percent / 100`

Баланс: шанс боя +10-30%, тяжёлая версия +30-60%, шанс сильного противника +10-25%, обязателен максимум итогового шанса.

Поля: `effect_type: curse_dark_beacon`, `encounter_type: pve_battle / pvp_battle / both`, `battle_chance_bonus_percent`, `strong_enemy_chance_bonus_percent`, `strong_enemy_level_bonus`, `max_final_battle_chance_percent`, `works_in_locations`, `ignored_location_tags`, `ignored_encounter_tags`.

---

# 6. Зоны: локационные и мировые эффекты

## 72. Зона

Тип: локационный / мировой эффект.

Что делает: пока игрок находится в определённой локации, городе, регионе или зоне мирового события, на него накладываются положительные или отрицательные эффекты.

Текст для игрока: на этой территории действует особая зона. Она влияет на персонажа, пока вы здесь находитесь.

Базовая логика:

`if player_location has active_zone: apply_zone_effects(player)`

`if player_leaves_location: remove_or_expire_zone_effects(player)`

Варианты зон: огонь, вода, мороз, земля, ветер, духи, проклятая зона, священная зона, тьма, хаос, древняя магия, мировое событие.

Общие поля зоны:

- `effect_type: zone_effect`
- `zone_id`
- `zone_name`
- `zone_type: location / city / region / world / event`
- `zone_element`
- `affected_locations`
- `affected_city`
- `affected_region`
- `duration_mode: while_inside / timed_after_enter / timed_after_leave / world_event_duration`
- `apply_on: enter_location / every_action / every_search / every_turn / every_minute`
- `remove_on_leave`
- `linger_duration_seconds`
- `stack_rule`
- `priority`
- `show_to_player`
- `can_be_resisted`
- `resist_stat`
- `can_be_cleansed`

## 73. Зона огня

Тип: стихийная зона.

Что делает: территория жара, пламени или раскалённой магии. Может наносить периодический урон, повышать силу огненных эффектов и ослаблять ледяные эффекты.

Формула:

`fire_zone_damage = flat_damage + player_max_hp * fire_damage_percent / 100`

Баланс: 0.2-0.5% max HP слабая, 0.5-1% обычная, 1-2% опасная.

Поля: `zone_element: fire`, `periodic_damage_percent_max_hp`, `flat_damage`, `burn_chance_bonus_percent`, `fire_damage_bonus_percent`, `frost_effect_reduction_percent`, `energy_cost_bonus_percent`.

## 74. Зона воды

Тип: стихийная зона.

Что делает: вода, дождь, болота, приливы или влажная магия. Может снижать огонь, усиливать очищение, замедлять действия или влиять на добычу.

Формула:

`final_fire_damage = base_fire_damage * (1 - water_fire_reduction_percent / 100)`

Баланс: ослабление огня 10-30%, шанс погасить поджог 5-20%, бонус к водным находкам 5-15%.

Поля: `zone_element: water`, `fire_damage_reduction_percent`, `burn_extinguish_chance_percent`, `cleanse_bonus_percent`, `ranged_accuracy_penalty_percent`, `water_loot_bonus_percent`.

## 75. Зона мороза

Тип: стихийная зона.

Что делает: территория холода, льда или зимней магии. Может снижать точность, уклонение, восстановление и усиливать заморозку.

Формулы:

`final_accuracy = max(min_accuracy, base_accuracy - frost_accuracy_penalty)`

`final_dodge = max(0, base_dodge - frost_dodge_penalty)`

Баланс: штраф точности/уклонения -3-10%, опасная до -15%, шанс заморозки 3-10%.

Поля: `zone_element: frost`, `accuracy_penalty_percent`, `dodge_penalty_percent`, `freeze_chance_bonus_percent`, `regeneration_reduction_percent`, `energy_cost_bonus_percent`.

## 76. Зона земли

Тип: стихийная зона.

Что делает: территория тяжёлой земли, камня, корней или подземной силы. Может повышать защиту, снижать уклонение и замедлять бой.

Формула:

`final_physical_defense = base_physical_defense * (1 + earth_defense_bonus_percent / 100)`

Баланс: бонус защиты 3-10%, штраф уклонения -3-8%, бонус к добыче камня/руды 5-15%.

Поля: `zone_element: earth`, `physical_defense_bonus_percent`, `armor_bonus_percent`, `dodge_penalty_percent`, `escape_chance_penalty_percent`, `ore_resource_bonus_percent`.

## 77. Зона ветра

Тип: стихийная зона.

Что делает: территория бурь, сильного ветра или воздушной магии. Может повышать уклонение, снижать точность дальних атак и менять шанс событий.

Формулы:

`final_dodge = min(35, base_dodge + wind_dodge_bonus)`

`final_ranged_accuracy = max(min_accuracy, base_accuracy - wind_ranged_penalty)`

Баланс: бонус уклонения +2-6%, штраф дальним атакам -5-15%, бонус к побегу +5-15%.

Поля: `zone_element: wind`, `dodge_bonus_percent`, `ranged_accuracy_penalty_percent`, `escape_chance_bonus_percent`, `fog_disperse_chance_percent`, `action_time_reduction_percent`.

## 78. Зона духов

Тип: мистическая зона.

Что делает: территория духов, предков, призраков или древних следов. Может влиять на дух, проклятья, тени, восстановление и встречи с особыми существами.

Формула:

`final_max_spirit = base_max_spirit * (1 + spirit_zone_modifier_percent / 100)`

Баланс: изменение духа от -10% до +10%, шанс мистического события 5-15%, усиление проклятий 5-20%.

Поля: `zone_element: spirit`, `max_spirit_modifier_percent`, `spirit_skill_power_modifier_percent`, `curse_power_modifier_percent`, `spirit_encounter_chance_bonus_percent`, `vision_event_chance_percent`.

## 79. Проклятая зона

Тип: опасная зона.

Что делает: территория проклятия. Может накладывать долгие проклятья, снижать характеристики, усиливать мобов, портить добычу и мешать восстановлению.

Формулы:

`curse_apply_success = random(1, 100) <= cursed_zone_chance`

`final_stat = base_stat * (1 - cursed_zone_stat_penalty_percent / 100)`

Баланс: шанс проклятья 1-5% за опасное действие, штраф характеристик -2-10%, опасные встречи +10-30%.

Поля: `zone_element: curse`, `curse_apply_chance_percent`, `curse_pool`, `all_stats_penalty_percent`, `camp_recovery_cap_percent`, `danger_encounter_bonus_percent`, `resource_ash_chance_percent`, `enemy_power_bonus_percent`, `show_enter_warning: true`.

## 80. Священная зона

Тип: положительная зона.

Что делает: безопасная или благословенная территория. Может ускорять восстановление, ослаблять проклятья, повышать защиту и снижать шанс опасных встреч.

Формула:

`final_healing = base_healing * (1 + holy_healing_bonus_percent / 100)`

Баланс: бонус лечения 5-20%, снижение опасных встреч 5-20%, ослабление проклятий 5-30%.

Поля: `zone_element: holy`, `healing_bonus_percent`, `camp_recovery_bonus_percent`, `curse_effect_reduction_percent`, `danger_encounter_reduction_percent`, `curse_resistance_bonus_percent`.

## 81. Зона древней магии

Тип: нестабильная зона.

Что делает: территория старой магии. Может усиливать навыки, искажать эффекты, повышать шанс редких событий и одновременно накладывать риски.

Формула:

`random_zone_effect = choose_from(zone_effect_pool)`

Баланс: бонус к навыкам 5-15%, шанс случайного эффекта 3-10%, бонус к редким находкам 3-10%.

Поля: `zone_element: ancient_magic`, `mana_skill_bonus_percent`, `spirit_skill_bonus_percent`, `random_effect_chance_percent`, `effect_pool`, `rare_event_bonus_percent`, `artifact_effect_bonus_percent`, `magic_failure_chance_percent`.

---

# 7. Временная защита от зон

## 7.1. Общая механика защиты

Тип: временная защита от зональных эффектов.

Что делает: специальные зелья, артефакты или предметы могут временно снижать, блокировать или ослаблять действие некоторых зон.

Текст для игрока: вы временно защищены от части эффектов этой зоны.

Базовая логика:

`if player_has_zone_protection and zone_effect.element in protected_elements: reduce_or_block_zone_effect()`

## 7.2. Варианты защиты

Полная временная защита:

`final_zone_effect_power = 0`

Частичная защита:

`final_zone_effect_power = base_zone_effect_power * (1 - protection_percent / 100)`

Защита от конкретной стихии:

- огонь;
- вода;
- мороз;
- земля;
- ветер;
- духи;
- проклятая зона;
- тьма;
- хаос;
- древняя магия.

Защита от конкретных тегов эффекта:

- периодический урон;
- шанс проклятья;
- штраф характеристик;
- штраф точности;
- штраф уклонения;
- порча ресурсов;
- повышенная трата энергии;
- снижение лечения;
- повышенный шанс опасных встреч.

## 7.3. Баланс защиты

Зелья:

- слабое: 10-20 минут, защита 25-40%;
- обычное: 30-60 минут, защита 40-60%;
- сильное: 1-2 часа, защита 60-80%;
- редкое: короткая полная защита от одного типа зоны.

Артефакты:

- постоянная слабая защита: 10-25%;
- сильная защита должна иметь ограничение, заряд, кулдаун или штраф;
- полная постоянная защита от зоны нежелательна, кроме уникальных артефактов.

## 7.4. Поля конструктора защиты

- `effect_type: zone_protection`
- `protected_zone_elements: fire / water / frost / earth / wind / spirit / curse / holy / shadow / chaos / ancient_magic / custom`
- `protected_effect_tags: periodic_damage / curse_apply / stat_penalty / accuracy_penalty / dodge_penalty / resource_ash / energy_cost / healing_reduction / encounter_bonus`
- `protection_mode: full_block / percent_reduction / flat_reduction / chance_resist`
- `protection_percent`
- `flat_reduction`
- `resist_chance_percent`
- `duration_seconds`
- `duration_actions`
- `charges`
- `consume_charge_on_trigger`
- `active_when: potion_active / artifact_equipped / special_slot / buff`
- `stack_rule: strongest_only / additive_limited / unique_only`
- `max_total_protection_percent`
- `can_be_dispelled`
- `works_against_world_zones`
- `works_against_location_zones`

## 7.5. Поля зоны для проверки защиты

Чтобы зона понимала, можно ли от неё защититься, добавить в зону:

- `can_be_protected_against`
- `allowed_protection_elements`
- `allowed_protection_tags`
- `minimum_effect_power_after_protection_percent`
- `ignore_protection`
- `protection_effectiveness_percent`
- `required_protection_level`
- `show_protection_hint_to_player`

## 7.6. Примеры защиты

Зелье прохладной кожи: временная защита от зоны огня на 30 минут. Снижает урон от жара и шанс поджога на 50%.

Амулет тихих духов: пока экипирован, снижает силу эффектов зоны духов на 20%.

Печать чистого пути: на 1 час снижает шанс получить проклятье в проклятой зоне на 70%.

Плащ против ветра: снижает штраф точности от зоны ветра на 50%.

Артефакт глубинного дыхания: позволяет игнорировать часть отрицательных эффектов зоны воды и болот.

---

# 8. Короткий список всех эффектов для навигации

1. Отравление
2. Регенерация здоровья
3. Регенерация маны
4. Регенерация духа
5. Урон крита
6. Шанс критического удара
7. Физическая защита
8. Магическая защита
9. Точность
10. Уклонение
11. Сила
12. Мудрость
13. Выносливость
14. Ловкость
15. Восприятие
16. Интеллект
17. Дополнительный слот инвентаря
18. Поджог
19. Оглушение
20. Отражение
21. Шипы
22. Поглощение магии
23. Поглощение жизни
24. Поглощение духа
25. Аура характеристики
26. Заморозка
27. Взрыв после смерти
28. Пробой
29. Кровотечение
30. Аура регенерации
31. Живая броня
32. Аура разложения
33. Туманный покров
34. Тень прошлого
35. Печать бессмертного
36. Неуязвимость
37. Быстрые руки
38. Хранилище маны
39. Хранилище жизни
40. Хранилище духа
41. Клон
42. Скрытность
43. Следопыт
44. Хрупкость
45. Утечка маны
46. Истощение жизни
47. Ослабление духа
48. Проклятье неуклюжести
49. Путаница
50. Проклятье уязвимости
51. Гниение духа
52. Затмение разума
53. Иссушение
54. Клятва поражения
55. Печать смерти
56. Осквернённая кровь
57. Проклятье одиночества
58. Оковы судьбы
59. Тьма веков
60. Проклятая душа
61. Тень предателя
62. Пустые карманы
63. Обречённая удача
64. Паническая атака
65. Беспокойный дух
66. Клятва крови
67. Оковы времени
68. Проклятое касание
69. Приманка для чудовищ
70. Волна нашествия
71. Тёмный маяк
72. Зона
73. Зона огня
74. Зона воды
75. Зона мороза
76. Зона земли
77. Зона ветра
78. Зона духов
79. Проклятая зона
80. Священная зона
81. Зона древней магии
82. Временная защита от зон

---

# 9. Рекомендация для админ-панели конструктора

В конструкторе лучше не делать 82 отдельные системы. Лучше сделать несколько универсальных типов:

1. `stat_modifier` — сила, мудрость, выносливость, ловкость, восприятие, интеллект.
2. `resource_regeneration` — регенерация HP, маны, духа.
3. `max_resource_modifier` — увеличение и снижение max HP, маны, духа.
4. `periodic_damage` — яд, поджог, кровотечение, разложение.
5. `control_effect` — оглушение, путаница, паника.
6. `damage_response` — шипы, отражение.
7. `absorb_effect` — поглощение жизни, маны, духа.
8. `aura_effect` — ауры характеристик, регенерации, разложения.
9. `summon_effect` — клон, тень прошлого, тень предателя, волна нашествия.
10. `curse_effect` — долгие проклятья.
11. `zone_effect` — локационные и мировые зоны.
12. `zone_protection` — зелья и артефакты защиты от зон.
13. `item_lifecycle` — хрупкость, разрушение, заряды, одноразовость.

Так будет проще развивать проект и добавлять новые эффекты без переписывания кода под каждый конкретный случай.
