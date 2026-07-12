# 04. Effects Constructor TZ — источник

# Нер-Талис — ТЗ конструктора эффектов, состояний, свойств, проклятий, зон, травм и особых механик

**Файл для Claude Code.**  
Назначение: использовать как единое техническое задание для реализации/расширения конструктора эффектов, предметов, зелий, мобов, зон, заданий, достижений, дома игрока и уникальных мобов.

## 0. Главные правила

1. **Игроку не показывать формулы.** Игрок видит только понятное описание, итоговые значения, длительность и предупреждения. Формулы, коэффициенты, теги, caps и внутренние поля — только для админки, документации и кода.
2. **Все эффекты должны быть универсальными.** Не делать 300 отдельных hard-code систем. Делать универсальные типы: `stat_modifier`, `resource_regeneration`, `periodic_damage`, `control_effect`, `damage_response`, `absorb_effect`, `aura_effect`, `summon_effect`, `curse_effect`, `zone_effect`, `zone_protection`, `item_lifecycle`, `slot_block`, `unique_mob_counter`, `home_rest_bonus`.
3. **Дух отвечает за физику.** `spirit` — ресурс физических боевых навыков, стоек и приёмов. Не использовать Дух как отдельный магический/мистический тип урона. Для магии используется `mana`.
4. **Мана отвечает за магию.** Посохи, магические книги, заклинания, магическая защита, древняя магия — через `mana`, `magic`, `mana_skill`.
5. **Периодический и ответный урон не запускают бесконечные цепочки.** Для яда, поджога, кровотечения, аур урона, шипов, отражения, взрыва трупа и похожих эффектов по умолчанию: `can_trigger_effects=false`, `can_be_reflected=false`.
6. **Уникальность предмета — не качество.** Уникальный предмет может иметь любое качество или не иметь качества. Качества отдельно: обычный, необычный, редкий, эпический, легендарный, мифический, божественный.
7. **Посмертные PVP-проклятья.** В PVP их может наложить только погибший игрок с достижением «Проклятье? Какое проклятье?». Проклятья от мобов, предметов, ловушек, событий, неправильных действий и зон достижения не требуют.
8. **Оковы времени.** Увеличение отката навыков фиксированное: `+1`, `+2`, `+3`, а не процент.
9. **Травмы рук разделены.** Травма правой руки временно блокирует `weapon1`; травма левой руки временно блокирует `weapon2`.
10. **Уникальные мобы могут требовать контр-зелья.** Уникальная защита или атака моба временно ослабляется специальным зельем/колбой/составом с подходящим `counter_tag`.
11. **Отдых дома может выдавать бонусы.** Дом/комната/мебель/улучшения могут давать временные эффекты после отдыха: характеристики, опыт, монеты, восстановление, ремесло, добыча и т.д.

---

## 1. Базовая модель эффекта

```ts
type EffectDefinition = {
  effect_id: string;
  effect_name: string;
  player_text: string;          // текст игроку без формул
  admin_description: string;    // подробное описание для админки
  effect_type: string;
  source_type: 'item' | 'skill' | 'mob' | 'boss' | 'trap' | 'event' | 'zone' | 'curse' | 'achievement' | 'quest' | 'admin' | 'home' | 'system';
  target: 'self' | 'enemy' | 'ally' | 'party' | 'raid' | 'all_battle' | 'random_enemy' | 'random_ally' | 'location' | 'item';
  active_when: string[];        // equipped, in_inventory, in_battle, on_attack, on_receive_damage, on_death, on_rest_home, etc.
  duration_turns?: number;
  duration_seconds?: number;
  apply_chance_percent?: number;
  stack_rule: 'refresh' | 'strongest_only' | 'stack_limited' | 'unique_only' | 'additive_limited';
  max_stacks?: number;
  can_be_cleansed?: boolean;
  cleanse_tags?: string[];
  works_in_pve?: boolean;
  works_in_pvp?: boolean;
  show_to_player?: boolean;
  log_event?: boolean;
  can_trigger_effects?: boolean;
  can_be_reflected?: boolean;
  fields: Record<string, unknown>;
};
```

### 1.1. Активный эффект на игроке/мобе

```ts
type ActiveEffect = {
  active_effect_id: string;
  effect_id: string;
  owner_type: 'player' | 'mob' | 'item' | 'location' | 'world_event';
  owner_id: string;
  source_type: string;
  source_id?: string;
  started_at: string;
  ends_at?: string;
  remaining_turns?: number;
  stacks: number;
  power_multiplier: number;
  metadata: Record<string, unknown>;
};
```

---

## 2. Caps и общие формулы

```ts
const CAPS = {
  dodge_max_percent: 35,
  crit_chance_max_percent: 49,
  accuracy_min_percent: 5,
  accuracy_max_percent: 95,
  min_stat_value: 1,
  min_hp_value: 1,
};
```

### 2.1. Характеристика
`final_stat = max(min_stat, base_stat + flat_bonus + base_stat * percent_bonus / 100)`

### 2.2. Максимальный ресурс
`final_max_resource = max(min_resource, base_max_resource + flat_bonus + base_max_resource * percent_bonus / 100)`

### 2.3. Периодический урон
`tick_damage = flat_damage + target_max_hp * percent_max_hp_damage / 100`  
`total_damage = tick_damage * duration_turns`

### 2.4. Лечение
`heal_amount = heal_flat + target_max_hp * heal_percent / 100`  
`current_hp = min(max_hp, current_hp + heal_amount)`

### 2.5. Шанс наложения с сопротивлением
`final_apply_chance = base_apply_chance * (1 - target_resistance_percent / 100)`

### 2.6. Пробой защиты
`bypass_damage = raw_damage * penetration_percent / 100`  
`final_damage = bypass_damage + damage_after_defense(raw_damage - bypass_damage)`

### 2.7. Ослабление уникальной защиты моба зельем
`final_unique_defense_percent = unique_defense_percent * (1 - potion_weakening_percent / 100)`

### 2.8. Ослабление уникальной атаки моба зельем
`final_unique_attack_power = unique_attack_power * (1 - potion_attack_weaken_percent / 100)`

### 2.9. Бонус после отдыха дома
`home_rest_bonus_power = base_bonus + home_level * level_bonus + furniture_bonus + comfort_bonus`  
`effect_ends_at = current_time + duration_seconds`

---

## 3. Универсальные типы конструктора

| Тип | Назначение |
|---|---|
| `stat_modifier` | Сила, Мудрость, Выносливость, Ловкость, Восприятие, Интеллект. |
| `resource_regeneration` | Регенерация HP, маны, Духа, энергии. |
| `max_resource_modifier` | Увеличение/снижение max HP, маны, Духа, энергии. |
| `periodic_damage` | Яд, поджог, кровотечение, разложение, жар, кислотный урон. |
| `control_effect` | Оглушение, заморозка, паника, путаница, блок действия. |
| `trauma_effect` | Травмы ног, рук, правой руки, левой руки, ожоги, обморожение. |
| `slot_block` | Временная блокировка слотов экипировки, особенно `weapon1`/`weapon2`. |
| `damage_modifier` | Усиление/ослабление физического, магического, чистого урона. |
| `damage_response` | Шипы, магическое отражение, ответная атака. |
| `absorb_effect` | Поглощение жизни, маны, Духа, энергии. |
| `aura_effect` | Ауры характеристик, регенерации, разложения, поля боя. |
| `combat_stance` | Стойки Духа: сила, защита, точность, движение. |
| `summon_effect` | Клон, тень прошлого, тень предателя, волна врагов. |
| `curse_effect` | Долгие проклятья, посмертные проклятья, проклятые состояния. |
| `zone_effect` | Локационные, городские, региональные, мировые, сезонные зоны. |
| `zone_protection` | Защита от зон зельями, артефактами, бафами. |
| `craft_modifier` | Ремесло, алхимия, плавильня, качество, доп. эффект. |
| `gather_modifier` | Добыча ресурсов, руда, травы, дерево, охота, рыбалка. |
| `trade_modifier` | Скидки, бонус продажи, комиссии, штраф торговли. |
| `item_lifecycle` | Заряды, прочность, хрупкость, поломка, ремонт, одноразовость. |
| `quest_flag` | Метки заданий, доступы, скрытые события. |
| `achievement_effect` | Пассивы/открытия от достижений. |
| `unique_mob_trait` | Уникальная защита/атака моба с контр-зельем. |
| `home_rest_bonus` | Временные бонусы после отдыха дома. |

---
## 4. Сводный реестр эффектов и свойств

### Партия 1 — базовые боевые состояния и травмы

| ID | Название | Куда подходит | Базовая логика / формула |
|---:|---|---|---|

| 1 | Отравление | Бой, ловушки, мобы, навыки, зелья, зоны, травмы. | periodic/control/trauma: `if roll<=chance apply; final_param=base±penalty; duration_turns/seconds`. |

| 2 | Слабый яд | Бой, ловушки, мобы, навыки, зелья, зоны, травмы. | periodic/control/trauma: `if roll<=chance apply; final_param=base±penalty; duration_turns/seconds`. |

| 3 | Сильный яд | Бой, ловушки, мобы, навыки, зелья, зоны, травмы. | periodic/control/trauma: `if roll<=chance apply; final_param=base±penalty; duration_turns/seconds`. |

| 4 | Поджог | Бой, ловушки, мобы, навыки, зелья, зоны, травмы. | periodic/control/trauma: `if roll<=chance apply; final_param=base±penalty; duration_turns/seconds`. |

| 5 | Тлеющий ожог | Бой, ловушки, мобы, навыки, зелья, зоны, травмы. | periodic/control/trauma: `if roll<=chance apply; final_param=base±penalty; duration_turns/seconds`. |

| 6 | Глубокий ожог | Бой, ловушки, мобы, навыки, зелья, зоны, травмы. | periodic/control/trauma: `if roll<=chance apply; final_param=base±penalty; duration_turns/seconds`. |

| 7 | Кровотечение | Бой, ловушки, мобы, навыки, зелья, зоны, травмы. | periodic/control/trauma: `if roll<=chance apply; final_param=base±penalty; duration_turns/seconds`. |

| 8 | Рваная рана | Бой, ловушки, мобы, навыки, зелья, зоны, травмы. | periodic/control/trauma: `if roll<=chance apply; final_param=base±penalty; duration_turns/seconds`. |

| 9 | Оглушение | Бой, ловушки, мобы, навыки, зелья, зоны, травмы. | periodic/control/trauma: `if roll<=chance apply; final_param=base±penalty; duration_turns/seconds`. |

| 10 | Ошеломление | Бой, ловушки, мобы, навыки, зелья, зоны, травмы. | periodic/control/trauma: `if roll<=chance apply; final_param=base±penalty; duration_turns/seconds`. |

| 11 | Заморозка | Бой, ловушки, мобы, навыки, зелья, зоны, травмы. | periodic/control/trauma: `if roll<=chance apply; final_param=base±penalty; duration_turns/seconds`. |

| 12 | Обморожение | Бой, ловушки, мобы, навыки, зелья, зоны, травмы. | periodic/control/trauma: `if roll<=chance apply; final_param=base±penalty; duration_turns/seconds`. |

| 13 | Путаница | Бой, ловушки, мобы, навыки, зелья, зоны, травмы. | periodic/control/trauma: `if roll<=chance apply; final_param=base±penalty; duration_turns/seconds`. |

| 14 | Паника | Бой, ловушки, мобы, навыки, зелья, зоны, травмы. | periodic/control/trauma: `if roll<=chance apply; final_param=base±penalty; duration_turns/seconds`. |

| 15 | Травма ноги | Бой, ловушки, мобы, навыки, зелья, зоны, травмы. | periodic/control/trauma: `if roll<=chance apply; final_param=base±penalty; duration_turns/seconds`. |

| 16 | Травма руки / технический тип | Бой, ловушки, мобы, навыки, зелья, зоны, травмы. | periodic/control/trauma: `if roll<=chance apply; final_param=base±penalty; duration_turns/seconds`. |

| 17 | Трещина в броне | Бой, ловушки, мобы, навыки, зелья, зоны, травмы. | periodic/control/trauma: `if roll<=chance apply; final_param=base±penalty; duration_turns/seconds`. |

| 18 | Магический надлом | Бой, ловушки, мобы, навыки, зелья, зоны, травмы. | periodic/control/trauma: `if roll<=chance apply; final_param=base±penalty; duration_turns/seconds`. |

| 19 | Усталость | Бой, ловушки, мобы, навыки, зелья, зоны, травмы. | periodic/control/trauma: `if roll<=chance apply; final_param=base±penalty; duration_turns/seconds`. |

| 20 | Истощение | Бой, ловушки, мобы, навыки, зелья, зоны, травмы. | periodic/control/trauma: `if roll<=chance apply; final_param=base±penalty; duration_turns/seconds`. |



### Партия 2 — восстановление, щиты, очищение и защитные состояния

| ID | Название | Куда подходит | Базовая логика / формула |
|---:|---|---|---|

| 21 | Регенерация здоровья | Зелья, артефакты, навыки, лагерь, достижения, защита. | heal/shield/cleanse: `restore=flat+max*percent/100`; `remove_effects_by_tags(tags,count)`; `shield absorbs incoming_damage`. |

| 22 | Медленное восстановление | Зелья, артефакты, навыки, лагерь, достижения, защита. | heal/shield/cleanse: `restore=flat+max*percent/100`; `remove_effects_by_tags(tags,count)`; `shield absorbs incoming_damage`. |

| 23 | Быстрое лечение | Зелья, артефакты, навыки, лагерь, достижения, защита. | heal/shield/cleanse: `restore=flat+max*percent/100`; `remove_effects_by_tags(tags,count)`; `shield absorbs incoming_damage`. |

| 24 | Перелечивание в щит | Зелья, артефакты, навыки, лагерь, достижения, защита. | heal/shield/cleanse: `restore=flat+max*percent/100`; `remove_effects_by_tags(tags,count)`; `shield absorbs incoming_damage`. |

| 25 | Регенерация маны | Зелья, артефакты, навыки, лагерь, достижения, защита. | heal/shield/cleanse: `restore=flat+max*percent/100`; `remove_effects_by_tags(tags,count)`; `shield absorbs incoming_damage`. |

| 26 | Регенерация Духа | Зелья, артефакты, навыки, лагерь, достижения, защита. | heal/shield/cleanse: `restore=flat+max*percent/100`; `remove_effects_by_tags(tags,count)`; `shield absorbs incoming_damage`. |

| 27 | Восстановление энергии | Зелья, артефакты, навыки, лагерь, достижения, защита. | heal/shield/cleanse: `restore=flat+max*percent/100`; `remove_effects_by_tags(tags,count)`; `shield absorbs incoming_damage`. |

| 28 | Ускоренное восстановление в лагере | Зелья, артефакты, навыки, лагерь, достижения, защита. | heal/shield/cleanse: `restore=flat+max*percent/100`; `remove_effects_by_tags(tags,count)`; `shield absorbs incoming_damage`. |

| 29 | Щит здоровья | Зелья, артефакты, навыки, лагерь, достижения, защита. | heal/shield/cleanse: `restore=flat+max*percent/100`; `remove_effects_by_tags(tags,count)`; `shield absorbs incoming_damage`. |

| 30 | Магический барьер | Зелья, артефакты, навыки, лагерь, достижения, защита. | heal/shield/cleanse: `restore=flat+max*percent/100`; `remove_effects_by_tags(tags,count)`; `shield absorbs incoming_damage`. |

| 31 | Боевой заслон Духа | Зелья, артефакты, навыки, лагерь, достижения, защита. | heal/shield/cleanse: `restore=flat+max*percent/100`; `remove_effects_by_tags(tags,count)`; `shield absorbs incoming_damage`. |

| 32 | Каменная кожа | Зелья, артефакты, навыки, лагерь, достижения, защита. | heal/shield/cleanse: `restore=flat+max*percent/100`; `remove_effects_by_tags(tags,count)`; `shield absorbs incoming_damage`. |

| 33 | Магическая завеса | Зелья, артефакты, навыки, лагерь, достижения, защита. | heal/shield/cleanse: `restore=flat+max*percent/100`; `remove_effects_by_tags(tags,count)`; `shield absorbs incoming_damage`. |

| 34 | Неуязвимость | Зелья, артефакты, навыки, лагерь, достижения, защита. | heal/shield/cleanse: `restore=flat+max*percent/100`; `remove_effects_by_tags(tags,count)`; `shield absorbs incoming_damage`. |

| 35 | Печать спасения | Зелья, артефакты, навыки, лагерь, достижения, защита. | heal/shield/cleanse: `restore=flat+max*percent/100`; `remove_effects_by_tags(tags,count)`; `shield absorbs incoming_damage`. |

| 36 | Печать бессмертного | Зелья, артефакты, навыки, лагерь, достижения, защита. | heal/shield/cleanse: `restore=flat+max*percent/100`; `remove_effects_by_tags(tags,count)`; `shield absorbs incoming_damage`. |

| 37 | Очищение | Зелья, артефакты, навыки, лагерь, достижения, защита. | heal/shield/cleanse: `restore=flat+max*percent/100`; `remove_effects_by_tags(tags,count)`; `shield absorbs incoming_damage`. |

| 38 | Мягкое очищение | Зелья, артефакты, навыки, лагерь, достижения, защита. | heal/shield/cleanse: `restore=flat+max*percent/100`; `remove_effects_by_tags(tags,count)`; `shield absorbs incoming_damage`. |

| 39 | Защита от отрицательных эффектов | Зелья, артефакты, навыки, лагерь, достижения, защита. | heal/shield/cleanse: `restore=flat+max*percent/100`; `remove_effects_by_tags(tags,count)`; `shield absorbs incoming_damage`. |

| 40 | Защита от контроля | Зелья, артефакты, навыки, лагерь, достижения, защита. | heal/shield/cleanse: `restore=flat+max*percent/100`; `remove_effects_by_tags(tags,count)`; `shield absorbs incoming_damage`. |



### Партия 3 — атакующие свойства, крит, пробой, отражение и поглощение

| ID | Название | Куда подходит | Базовая логика / формула |
|---:|---|---|---|

| 41 | Усиление физического урона | Оружие, навыки, артефакты, боевые зелья, мобы. | damage: `final=base+flat+base*percent/100`; crit cap 49%; dodge cap 35%; response effects do not trigger chains. |

| 42 | Усиление магического урона | Оружие, навыки, артефакты, боевые зелья, мобы. | damage: `final=base+flat+base*percent/100`; crit cap 49%; dodge cap 35%; response effects do not trigger chains. |

| 43 | Усиление навыков Духа | Оружие, навыки, артефакты, боевые зелья, мобы. | damage: `final=base+flat+base*percent/100`; crit cap 49%; dodge cap 35%; response effects do not trigger chains. |

| 44 | Чистый урон | Оружие, навыки, артефакты, боевые зелья, мобы. | damage: `final=base+flat+base*percent/100`; crit cap 49%; dodge cap 35%; response effects do not trigger chains. |

| 45 | Пробой физической защиты | Оружие, навыки, артефакты, боевые зелья, мобы. | damage: `final=base+flat+base*percent/100`; crit cap 49%; dodge cap 35%; response effects do not trigger chains. |

| 46 | Пробой магической защиты | Оружие, навыки, артефакты, боевые зелья, мобы. | damage: `final=base+flat+base*percent/100`; crit cap 49%; dodge cap 35%; response effects do not trigger chains. |

| 47 | Пробой брони | Оружие, навыки, артефакты, боевые зелья, мобы. | damage: `final=base+flat+base*percent/100`; crit cap 49%; dodge cap 35%; response effects do not trigger chains. |

| 48 | Сокрушение защиты | Оружие, навыки, артефакты, боевые зелья, мобы. | damage: `final=base+flat+base*percent/100`; crit cap 49%; dodge cap 35%; response effects do not trigger chains. |

| 49 | Шанс критического удара | Оружие, навыки, артефакты, боевые зелья, мобы. | damage: `final=base+flat+base*percent/100`; crit cap 49%; dodge cap 35%; response effects do not trigger chains. |

| 50 | Урон критического удара | Оружие, навыки, артефакты, боевые зелья, мобы. | damage: `final=base+flat+base*percent/100`; crit cap 49%; dodge cap 35%; response effects do not trigger chains. |

| 51 | Гарантированный крит | Оружие, навыки, артефакты, боевые зелья, мобы. | damage: `final=base+flat+base*percent/100`; crit cap 49%; dodge cap 35%; response effects do not trigger chains. |

| 52 | Добивание | Оружие, навыки, артефакты, боевые зелья, мобы. | damage: `final=base+flat+base*percent/100`; crit cap 49%; dodge cap 35%; response effects do not trigger chains. |

| 53 | Удар по ослабленной цели | Оружие, навыки, артефакты, боевые зелья, мобы. | damage: `final=base+flat+base*percent/100`; crit cap 49%; dodge cap 35%; response effects do not trigger chains. |

| 54 | Удар по проклятой цели | Оружие, навыки, артефакты, боевые зелья, мобы. | damage: `final=base+flat+base*percent/100`; crit cap 49%; dodge cap 35%; response effects do not trigger chains. |

| 55 | Вампиризм | Оружие, навыки, артефакты, боевые зелья, мобы. | damage: `final=base+flat+base*percent/100`; crit cap 49%; dodge cap 35%; response effects do not trigger chains. |

| 56 | Поглощение маны | Оружие, навыки, артефакты, боевые зелья, мобы. | damage: `final=base+flat+base*percent/100`; crit cap 49%; dodge cap 35%; response effects do not trigger chains. |

| 57 | Поглощение Духа | Оружие, навыки, артефакты, боевые зелья, мобы. | damage: `final=base+flat+base*percent/100`; crit cap 49%; dodge cap 35%; response effects do not trigger chains. |

| 58 | Кража энергии | Оружие, навыки, артефакты, боевые зелья, мобы. | damage: `final=base+flat+base*percent/100`; crit cap 49%; dodge cap 35%; response effects do not trigger chains. |

| 59 | Шипы | Оружие, навыки, артефакты, боевые зелья, мобы. | damage: `final=base+flat+base*percent/100`; crit cap 49%; dodge cap 35%; response effects do not trigger chains. |

| 60 | Магическое отражение | Оружие, навыки, артефакты, боевые зелья, мобы. | damage: `final=base+flat+base*percent/100`; crit cap 49%; dodge cap 35%; response effects do not trigger chains. |



### Партия 4 — ауры, стойки, накопительные эффекты и экипировка

| ID | Название | Куда подходит | Базовая логика / формула |
|---:|---|---|---|

| 61 | Аура силы | Ауры, стойки Духа, предметы, артефакты, накопление в бою. | aura/stance/stacks: `stacks=min(max,stacks+gain)`; `final=base*(1+stacks*bonus/100)`; active only in required slot/state. |

| 62 | Аура выносливости | Ауры, стойки Духа, предметы, артефакты, накопление в бою. | aura/stance/stacks: `stacks=min(max,stacks+gain)`; `final=base*(1+stacks*bonus/100)`; active only in required slot/state. |

| 63 | Аура ловкости | Ауры, стойки Духа, предметы, артефакты, накопление в бою. | aura/stance/stacks: `stacks=min(max,stacks+gain)`; `final=base*(1+stacks*bonus/100)`; active only in required slot/state. |

| 64 | Аура восприятия | Ауры, стойки Духа, предметы, артефакты, накопление в бою. | aura/stance/stacks: `stacks=min(max,stacks+gain)`; `final=base*(1+stacks*bonus/100)`; active only in required slot/state. |

| 65 | Аура интеллекта | Ауры, стойки Духа, предметы, артефакты, накопление в бою. | aura/stance/stacks: `stacks=min(max,stacks+gain)`; `final=base*(1+stacks*bonus/100)`; active only in required slot/state. |

| 66 | Аура мудрости | Ауры, стойки Духа, предметы, артефакты, накопление в бою. | aura/stance/stacks: `stacks=min(max,stacks+gain)`; `final=base*(1+stacks*bonus/100)`; active only in required slot/state. |

| 67 | Боевая стойка силы | Ауры, стойки Духа, предметы, артефакты, накопление в бою. | aura/stance/stacks: `stacks=min(max,stacks+gain)`; `final=base*(1+stacks*bonus/100)`; active only in required slot/state. |

| 68 | Защитная стойка | Ауры, стойки Духа, предметы, артефакты, накопление в бою. | aura/stance/stacks: `stacks=min(max,stacks+gain)`; `final=base*(1+stacks*bonus/100)`; active only in required slot/state. |

| 69 | Стойка точного удара | Ауры, стойки Духа, предметы, артефакты, накопление в бою. | aura/stance/stacks: `stacks=min(max,stacks+gain)`; `final=base*(1+stacks*bonus/100)`; active only in required slot/state. |

| 70 | Стойка быстрого движения | Ауры, стойки Духа, предметы, артефакты, накопление в бою. | aura/stance/stacks: `stacks=min(max,stacks+gain)`; `final=base*(1+stacks*bonus/100)`; active only in required slot/state. |

| 71 | Накопление ярости | Ауры, стойки Духа, предметы, артефакты, накопление в бою. | aura/stance/stacks: `stacks=min(max,stacks+gain)`; `final=base*(1+stacks*bonus/100)`; active only in required slot/state. |

| 72 | Накопление стойкости | Ауры, стойки Духа, предметы, артефакты, накопление в бою. | aura/stance/stacks: `stacks=min(max,stacks+gain)`; `final=base*(1+stacks*bonus/100)`; active only in required slot/state. |

| 73 | Накопление мастерства | Ауры, стойки Духа, предметы, артефакты, накопление в бою. | aura/stance/stacks: `stacks=min(max,stacks+gain)`; `final=base*(1+stacks*bonus/100)`; active only in required slot/state. |

| 74 | Накопление концентрации | Ауры, стойки Духа, предметы, артефакты, накопление в бою. | aura/stance/stacks: `stacks=min(max,stacks+gain)`; `final=base*(1+stacks*bonus/100)`; active only in required slot/state. |

| 75 | Разогрев артефакта | Ауры, стойки Духа, предметы, артефакты, накопление в бою. | aura/stance/stacks: `stacks=min(max,stacks+gain)`; `final=base*(1+stacks*bonus/100)`; active only in required slot/state. |

| 76 | Перегрев артефакта | Ауры, стойки Духа, предметы, артефакты, накопление в бою. | aura/stance/stacks: `stacks=min(max,stacks+gain)`; `final=base*(1+stacks*bonus/100)`; active only in required slot/state. |

| 77 | Эффект экипировки | Ауры, стойки Духа, предметы, артефакты, накопление в бою. | aura/stance/stacks: `stacks=min(max,stacks+gain)`; `final=base*(1+stacks*bonus/100)`; active only in required slot/state. |

| 78 | Эффект особого слота | Ауры, стойки Духа, предметы, артефакты, накопление в бою. | aura/stance/stacks: `stacks=min(max,stacks+gain)`; `final=base*(1+stacks*bonus/100)`; active only in required slot/state. |

| 79 | Эффект предмета в инвентаре | Ауры, стойки Духа, предметы, артефакты, накопление в бою. | aura/stance/stacks: `stacks=min(max,stacks+gain)`; `final=base*(1+stacks*bonus/100)`; active only in required slot/state. |

| 80 | Эффект при снятии предмета | Ауры, стойки Духа, предметы, артефакты, накопление в бою. | aura/stance/stacks: `stacks=min(max,stacks+gain)`; `final=base*(1+stacks*bonus/100)`; active only in required slot/state. |



### Партия 5 — заряды, одноразовые, перезаряжаемые, хрупкие, проклятые и уникальные предметы

| ID | Название | Куда подходит | Базовая логика / формула |
|---:|---|---|---|

| 81 | Заряды предмета | Предметы, артефакты, квестовые награды, сезонные вещи. | item lifecycle: `charges-=cost`; `if durability<=0 broken`; `if bound block trade/drop`; `if season_active effect_active`. |

| 82 | Восстановление зарядов по времени | Предметы, артефакты, квестовые награды, сезонные вещи. | item lifecycle: `charges-=cost`; `if durability<=0 broken`; `if bound block trade/drop`; `if season_active effect_active`. |

| 83 | Заряд за действие | Предметы, артефакты, квестовые награды, сезонные вещи. | item lifecycle: `charges-=cost`; `if durability<=0 broken`; `if bound block trade/drop`; `if season_active effect_active`. |

| 84 | Заряд за убийство | Предметы, артефакты, квестовые награды, сезонные вещи. | item lifecycle: `charges-=cost`; `if durability<=0 broken`; `if bound block trade/drop`; `if season_active effect_active`. |

| 85 | Одноразовый эффект | Предметы, артефакты, квестовые награды, сезонные вещи. | item lifecycle: `charges-=cost`; `if durability<=0 broken`; `if bound block trade/drop`; `if season_active effect_active`. |

| 86 | Одноразовое спасение от смерти | Предметы, артефакты, квестовые награды, сезонные вещи. | item lifecycle: `charges-=cost`; `if durability<=0 broken`; `if bound block trade/drop`; `if season_active effect_active`. |

| 87 | Хрупкость предмета | Предметы, артефакты, квестовые награды, сезонные вещи. | item lifecycle: `charges-=cost`; `if durability<=0 broken`; `if bound block trade/drop`; `if season_active effect_active`. |

| 88 | Износ предмета | Предметы, артефакты, квестовые награды, сезонные вещи. | item lifecycle: `charges-=cost`; `if durability<=0 broken`; `if bound block trade/drop`; `if season_active effect_active`. |

| 89 | Сломанный предмет | Предметы, артефакты, квестовые награды, сезонные вещи. | item lifecycle: `charges-=cost`; `if durability<=0 broken`; `if bound block trade/drop`; `if season_active effect_active`. |

| 90 | Починка предмета | Предметы, артефакты, квестовые награды, сезонные вещи. | item lifecycle: `charges-=cost`; `if durability<=0 broken`; `if bound block trade/drop`; `if season_active effect_active`. |

| 91 | Проклятый предмет | Предметы, артефакты, квестовые награды, сезонные вещи. | item lifecycle: `charges-=cost`; `if durability<=0 broken`; `if bound block trade/drop`; `if season_active effect_active`. |

| 92 | Запрет снятия проклятого предмета | Предметы, артефакты, квестовые награды, сезонные вещи. | item lifecycle: `charges-=cost`; `if durability<=0 broken`; `if bound block trade/drop`; `if season_active effect_active`. |

| 93 | Проклятая привязка | Предметы, артефакты, квестовые награды, сезонные вещи. | item lifecycle: `charges-=cost`; `if durability<=0 broken`; `if bound block trade/drop`; `if season_active effect_active`. |

| 94 | Уникальный предмет | Предметы, артефакты, квестовые награды, сезонные вещи. | item lifecycle: `charges-=cost`; `if durability<=0 broken`; `if bound block trade/drop`; `if season_active effect_active`. |

| 95 | Именной предмет | Предметы, артефакты, квестовые награды, сезонные вещи. | item lifecycle: `charges-=cost`; `if durability<=0 broken`; `if bound block trade/drop`; `if season_active effect_active`. |

| 96 | Персональная привязка | Предметы, артефакты, квестовые награды, сезонные вещи. | item lifecycle: `charges-=cost`; `if durability<=0 broken`; `if bound block trade/drop`; `if season_active effect_active`. |

| 97 | Перезаряжаемый активный эффект | Предметы, артефакты, квестовые награды, сезонные вещи. | item lifecycle: `charges-=cost`; `if durability<=0 broken`; `if bound block trade/drop`; `if season_active effect_active`. |

| 98 | Перезарядка после боя | Предметы, артефакты, квестовые награды, сезонные вещи. | item lifecycle: `charges-=cost`; `if durability<=0 broken`; `if bound block trade/drop`; `if season_active effect_active`. |

| 99 | Сезонный предмет | Предметы, артефакты, квестовые награды, сезонные вещи. | item lifecycle: `charges-=cost`; `if durability<=0 broken`; `if bound block trade/drop`; `if season_active effect_active`. |

| 100 | Спящий эффект предмета | Предметы, артефакты, квестовые награды, сезонные вещи. | item lifecycle: `charges-=cost`; `if durability<=0 broken`; `if bound block trade/drop`; `if season_active effect_active`. |



### Партия 6 — долгие проклятья, посмертные проклятья и последствия

| ID | Название | Куда подходит | Базовая логика / формула |
|---:|---|---|---|

| 101 | Долгое проклятье | Проклятья от PVP, мобов, зон, предметов, ловушек, событий. | curse: `if roll<=chance apply(duration)`; PVP death requires achievement; `cooldown=base+flat_increase` for time shackles. |

| 102 | Посмертное PVP-проклятье | Проклятья от PVP, мобов, зон, предметов, ловушек, событий. | curse: `if roll<=chance apply(duration)`; PVP death requires achievement; `cooldown=base+flat_increase` for time shackles. |

| 103 | Проклятье неуклюжести | Проклятья от PVP, мобов, зон, предметов, ловушек, событий. | curse: `if roll<=chance apply(duration)`; PVP death requires achievement; `cooldown=base+flat_increase` for time shackles. |

| 104 | Пустые карманы | Проклятья от PVP, мобов, зон, предметов, ловушек, событий. | curse: `if roll<=chance apply(duration)`; PVP death requires achievement; `cooldown=base+flat_increase` for time shackles. |

| 105 | Проклятье уязвимости | Проклятья от PVP, мобов, зон, предметов, ловушек, событий. | curse: `if roll<=chance apply(duration)`; PVP death requires achievement; `cooldown=base+flat_increase` for time shackles. |

| 106 | Иссушение жизни | Проклятья от PVP, мобов, зон, предметов, ловушек, событий. | curse: `if roll<=chance apply(duration)`; PVP death requires achievement; `cooldown=base+flat_increase` for time shackles. |

| 107 | Затмение разума | Проклятья от PVP, мобов, зон, предметов, ловушек, событий. | curse: `if roll<=chance apply(duration)`; PVP death requires achievement; `cooldown=base+flat_increase` for time shackles. |

| 108 | Истощение Духа | Проклятья от PVP, мобов, зон, предметов, ловушек, событий. | curse: `if roll<=chance apply(duration)`; PVP death requires achievement; `cooldown=base+flat_increase` for time shackles. |

| 109 | Оковы времени | Проклятья от PVP, мобов, зон, предметов, ловушек, событий. | curse: `if roll<=chance apply(duration)`; PVP death requires achievement; `cooldown=base+flat_increase` for time shackles. |

| 110 | Оковы судьбы | Проклятья от PVP, мобов, зон, предметов, ловушек, событий. | curse: `if roll<=chance apply(duration)`; PVP death requires achievement; `cooldown=base+flat_increase` for time shackles. |

| 111 | Клятва крови | Проклятья от PVP, мобов, зон, предметов, ловушек, событий. | curse: `if roll<=chance apply(duration)`; PVP death requires achievement; `cooldown=base+flat_increase` for time shackles. |

| 112 | Осквернённая кровь | Проклятья от PVP, мобов, зон, предметов, ловушек, событий. | curse: `if roll<=chance apply(duration)`; PVP death requires achievement; `cooldown=base+flat_increase` for time shackles. |

| 113 | Проклятье одиночества | Проклятья от PVP, мобов, зон, предметов, ловушек, событий. | curse: `if roll<=chance apply(duration)`; PVP death requires achievement; `cooldown=base+flat_increase` for time shackles. |

| 114 | Тьма веков | Проклятья от PVP, мобов, зон, предметов, ловушек, событий. | curse: `if roll<=chance apply(duration)`; PVP death requires achievement; `cooldown=base+flat_increase` for time shackles. |

| 115 | Проклятая душа | Проклятья от PVP, мобов, зон, предметов, ловушек, событий. | curse: `if roll<=chance apply(duration)`; PVP death requires achievement; `cooldown=base+flat_increase` for time shackles. |

| 116 | Печать смерти | Проклятья от PVP, мобов, зон, предметов, ловушек, событий. | curse: `if roll<=chance apply(duration)`; PVP death requires achievement; `cooldown=base+flat_increase` for time shackles. |

| 117 | Клятва поражения | Проклятья от PVP, мобов, зон, предметов, ловушек, событий. | curse: `if roll<=chance apply(duration)`; PVP death requires achievement; `cooldown=base+flat_increase` for time shackles. |

| 118 | Тень предателя | Проклятья от PVP, мобов, зон, предметов, ловушек, событий. | curse: `if roll<=chance apply(duration)`; PVP death requires achievement; `cooldown=base+flat_increase` for time shackles. |

| 119 | Волна нашествия | Проклятья от PVP, мобов, зон, предметов, ловушек, событий. | curse: `if roll<=chance apply(duration)`; PVP death requires achievement; `cooldown=base+flat_increase` for time shackles. |

| 120 | Тёмный маяк | Проклятья от PVP, мобов, зон, предметов, ловушек, событий. | curse: `if roll<=chance apply(duration)`; PVP death requires achievement; `cooldown=base+flat_increase` for time shackles. |



### Партия 7 — зоны, локационные эффекты и защита от зон

| ID | Название | Куда подходит | Базовая логика / формула |
|---:|---|---|---|

| 121 | Зона | Локации, города, регионы, события, подземелья. | zone: `if player in affected_area apply`; protection: `power=base*(1-protection/100)`; linger after leaving optional. |

| 122 | Зона огня | Локации, города, регионы, события, подземелья. | zone: `if player in affected_area apply`; protection: `power=base*(1-protection/100)`; linger after leaving optional. |

| 123 | Зона воды | Локации, города, регионы, события, подземелья. | zone: `if player in affected_area apply`; protection: `power=base*(1-protection/100)`; linger after leaving optional. |

| 124 | Зона мороза | Локации, города, регионы, события, подземелья. | zone: `if player in affected_area apply`; protection: `power=base*(1-protection/100)`; linger after leaving optional. |

| 125 | Зона земли | Локации, города, регионы, события, подземелья. | zone: `if player in affected_area apply`; protection: `power=base*(1-protection/100)`; linger after leaving optional. |

| 126 | Зона ветра | Локации, города, регионы, события, подземелья. | zone: `if player in affected_area apply`; protection: `power=base*(1-protection/100)`; linger after leaving optional. |

| 127 | Зона боевого Духа | Локации, города, регионы, события, подземелья. | zone: `if player in affected_area apply`; protection: `power=base*(1-protection/100)`; linger after leaving optional. |

| 128 | Проклятая зона | Локации, города, регионы, события, подземелья. | zone: `if player in affected_area apply`; protection: `power=base*(1-protection/100)`; linger after leaving optional. |

| 129 | Священная зона | Локации, города, регионы, события, подземелья. | zone: `if player in affected_area apply`; protection: `power=base*(1-protection/100)`; linger after leaving optional. |

| 130 | Зона древней магии | Локации, города, регионы, события, подземелья. | zone: `if player in affected_area apply`; protection: `power=base*(1-protection/100)`; linger after leaving optional. |

| 131 | Зона тьмы | Локации, города, регионы, события, подземелья. | zone: `if player in affected_area apply`; protection: `power=base*(1-protection/100)`; linger after leaving optional. |

| 132 | Зона хаоса | Локации, города, регионы, события, подземелья. | zone: `if player in affected_area apply`; protection: `power=base*(1-protection/100)`; linger after leaving optional. |

| 133 | Зона жизни | Локации, города, регионы, события, подземелья. | zone: `if player in affected_area apply`; protection: `power=base*(1-protection/100)`; linger after leaving optional. |

| 134 | Зона мёртвой земли | Локации, города, регионы, события, подземелья. | zone: `if player in affected_area apply`; protection: `power=base*(1-protection/100)`; linger after leaving optional. |

| 135 | Зона богатой добычи | Локации, города, регионы, события, подземелья. | zone: `if player in affected_area apply`; protection: `power=base*(1-protection/100)`; linger after leaving optional. |

| 136 | Истощённая зона | Локации, города, регионы, события, подземелья. | zone: `if player in affected_area apply`; protection: `power=base*(1-protection/100)`; linger after leaving optional. |

| 137 | Мировая зона события | Локации, города, регионы, события, подземелья. | zone: `if player in affected_area apply`; protection: `power=base*(1-protection/100)`; linger after leaving optional. |

| 138 | Сезонная зона | Локации, города, регионы, события, подземелья. | zone: `if player in affected_area apply`; protection: `power=base*(1-protection/100)`; linger after leaving optional. |

| 139 | Защита от зоны | Локации, города, регионы, события, подземелья. | zone: `if player in affected_area apply`; protection: `power=base*(1-protection/100)`; linger after leaving optional. |

| 140 | Защитный след после выхода из зоны | Локации, города, регионы, события, подземелья. | zone: `if player in affected_area apply`; protection: `power=base*(1-protection/100)`; linger after leaving optional. |



### Партия 8 — ремесло, алхимия, добыча, рыбалка и торговля

| ID | Название | Куда подходит | Базовая логика / формула |
|---:|---|---|---|

| 141 | Бонус к ремеслу | Ремесло, алхимия, профессии, ресурсы, торговля. | craft/gather/trade: `chance=base+bonus`; `amount=base+extra`; `price=base*(1±percent/100)`; cap rare drops. |

| 142 | Шанс не потратить ингредиенты | Ремесло, алхимия, профессии, ресурсы, торговля. | craft/gather/trade: `chance=base+bonus`; `amount=base+extra`; `price=base*(1±percent/100)`; cap rare drops. |

| 143 | Бонус к выходу ремесла | Ремесло, алхимия, профессии, ресурсы, торговля. | craft/gather/trade: `chance=base+bonus`; `amount=base+extra`; `price=base*(1±percent/100)`; cap rare drops. |

| 144 | Шанс дополнительного эффекта на предмет | Ремесло, алхимия, профессии, ресурсы, торговля. | craft/gather/trade: `chance=base+bonus`; `amount=base+extra`; `price=base*(1±percent/100)`; cap rare drops. |

| 145 | Улучшение качества при создании | Ремесло, алхимия, профессии, ресурсы, торговля. | craft/gather/trade: `chance=base+bonus`; `amount=base+extra`; `price=base*(1±percent/100)`; cap rare drops. |

| 146 | Снижение времени крафта | Ремесло, алхимия, профессии, ресурсы, торговля. | craft/gather/trade: `chance=base+bonus`; `amount=base+extra`; `price=base*(1±percent/100)`; cap rare drops. |

| 147 | Ускорение плавильни | Ремесло, алхимия, профессии, ресурсы, торговля. | craft/gather/trade: `chance=base+bonus`; `amount=base+extra`; `price=base*(1±percent/100)`; cap rare drops. |

| 148 | Бонус к алхимии | Ремесло, алхимия, профессии, ресурсы, торговля. | craft/gather/trade: `chance=base+bonus`; `amount=base+extra`; `price=base*(1±percent/100)`; cap rare drops. |

| 149 | Алхимический побочный результат | Ремесло, алхимия, профессии, ресурсы, торговля. | craft/gather/trade: `chance=base+bonus`; `amount=base+extra`; `price=base*(1±percent/100)`; cap rare drops. |

| 150 | Усиление зелья при создании | Ремесло, алхимия, профессии, ресурсы, торговля. | craft/gather/trade: `chance=base+bonus`; `amount=base+extra`; `price=base*(1±percent/100)`; cap rare drops. |

| 151 | Бонус к добыче ресурсов | Ремесло, алхимия, профессии, ресурсы, торговля. | craft/gather/trade: `chance=base+bonus`; `amount=base+extra`; `price=base*(1±percent/100)`; cap rare drops. |

| 152 | Бонус к добыче руды | Ремесло, алхимия, профессии, ресурсы, торговля. | craft/gather/trade: `chance=base+bonus`; `amount=base+extra`; `price=base*(1±percent/100)`; cap rare drops. |

| 153 | Шанс найти драгоценный камень при добыче | Ремесло, алхимия, профессии, ресурсы, торговля. | craft/gather/trade: `chance=base+bonus`; `amount=base+extra`; `price=base*(1±percent/100)`; cap rare drops. |

| 154 | Бонус к рубке дерева | Ремесло, алхимия, профессии, ресурсы, торговля. | craft/gather/trade: `chance=base+bonus`; `amount=base+extra`; `price=base*(1±percent/100)`; cap rare drops. |

| 155 | Бонус к травам | Ремесло, алхимия, профессии, ресурсы, торговля. | craft/gather/trade: `chance=base+bonus`; `amount=base+extra`; `price=base*(1±percent/100)`; cap rare drops. |

| 156 | Бонус к охотничьей добыче | Ремесло, алхимия, профессии, ресурсы, торговля. | craft/gather/trade: `chance=base+bonus`; `amount=base+extra`; `price=base*(1±percent/100)`; cap rare drops. |

| 157 | Бонус к рыбалке | Ремесло, алхимия, профессии, ресурсы, торговля. | craft/gather/trade: `chance=base+bonus`; `amount=base+extra`; `price=base*(1±percent/100)`; cap rare drops. |

| 158 | Бонус к редким находкам | Ремесло, алхимия, профессии, ресурсы, торговля. | craft/gather/trade: `chance=base+bonus`; `amount=base+extra`; `price=base*(1±percent/100)`; cap rare drops. |

| 159 | Скидка при покупке | Ремесло, алхимия, профессии, ресурсы, торговля. | craft/gather/trade: `chance=base+bonus`; `amount=base+extra`; `price=base*(1±percent/100)`; cap rare drops. |

| 160 | Бонус к продаже | Ремесло, алхимия, профессии, ресурсы, торговля. | craft/gather/trade: `chance=base+bonus`; `amount=base+extra`; `price=base*(1±percent/100)`; cap rare drops. |



### Партия 9 — задания, достижения, репутация, штрафы и социальные эффекты

| ID | Название | Куда подходит | Базовая логика / формула |
|---:|---|---|---|

| 161 | Бонус за активное задание | Квесты, достижения, репутация, штрафы, VK/TG модерация. | flags/reputation/fines: `if condition unlock/apply`; `fine=base+level*mult`; warning stages apply timed debuffs. |

| 162 | Метка задания | Квесты, достижения, репутация, штрафы, VK/TG модерация. | flags/reputation/fines: `if condition unlock/apply`; `fine=base+level*mult`; warning stages apply timed debuffs. |

| 163 | Временный доступ по заданию | Квесты, достижения, репутация, штрафы, VK/TG модерация. | flags/reputation/fines: `if condition unlock/apply`; `fine=base+level*mult`; warning stages apply timed debuffs. |

| 164 | Наградной множитель задания | Квесты, достижения, репутация, штрафы, VK/TG модерация. | flags/reputation/fines: `if condition unlock/apply`; `fine=base+level*mult`; warning stages apply timed debuffs. |

| 165 | Штраф за провал задания | Квесты, достижения, репутация, штрафы, VK/TG модерация. | flags/reputation/fines: `if condition unlock/apply`; `fine=base+level*mult`; warning stages apply timed debuffs. |

| 166 | Достижение как источник эффекта | Квесты, достижения, репутация, штрафы, VK/TG модерация. | flags/reputation/fines: `if condition unlock/apply`; `fine=base+level*mult`; warning stages apply timed debuffs. |

| 167 | Ступенчатое достижение | Квесты, достижения, репутация, штрафы, VK/TG модерация. | flags/reputation/fines: `if condition unlock/apply`; `fine=base+level*mult`; warning stages apply timed debuffs. |

| 168 | Сезонное достижение | Квесты, достижения, репутация, штрафы, VK/TG модерация. | flags/reputation/fines: `if condition unlock/apply`; `fine=base+level*mult`; warning stages apply timed debuffs. |

| 169 | Репутация города | Квесты, достижения, репутация, штрафы, VK/TG модерация. | flags/reputation/fines: `if condition unlock/apply`; `fine=base+level*mult`; warning stages apply timed debuffs. |

| 170 | Репутация фракции | Квесты, достижения, репутация, штрафы, VK/TG модерация. | flags/reputation/fines: `if condition unlock/apply`; `fine=base+level*mult`; warning stages apply timed debuffs. |

| 171 | Враждебность фракции | Квесты, достижения, репутация, штрафы, VK/TG модерация. | flags/reputation/fines: `if condition unlock/apply`; `fine=base+level*mult`; warning stages apply timed debuffs. |

| 172 | Фракционная метка | Квесты, достижения, репутация, штрафы, VK/TG модерация. | flags/reputation/fines: `if condition unlock/apply`; `fine=base+level*mult`; warning stages apply timed debuffs. |

| 173 | Штраф города | Квесты, достижения, репутация, штрафы, VK/TG модерация. | flags/reputation/fines: `if condition unlock/apply`; `fine=base+level*mult`; warning stages apply timed debuffs. |

| 174 | Рост штрафа со временем | Квесты, достижения, репутация, штрафы, VK/TG модерация. | flags/reputation/fines: `if condition unlock/apply`; `fine=base+level*mult`; warning stages apply timed debuffs. |

| 175 | Предупреждение модерации | Квесты, достижения, репутация, штрафы, VK/TG модерация. | flags/reputation/fines: `if condition unlock/apply`; `fine=base+level*mult`; warning stages apply timed debuffs. |

| 176 | Дебаф за предупреждение | Квесты, достижения, репутация, штрафы, VK/TG модерация. | flags/reputation/fines: `if condition unlock/apply`; `fine=base+level*mult`; warning stages apply timed debuffs. |

| 177 | Молчание в общем чате | Квесты, достижения, репутация, штрафы, VK/TG модерация. | flags/reputation/fines: `if condition unlock/apply`; `fine=base+level*mult`; warning stages apply timed debuffs. |

| 178 | Сообщение от стража порядка | Квесты, достижения, репутация, штрафы, VK/TG модерация. | flags/reputation/fines: `if condition unlock/apply`; `fine=base+level*mult`; warning stages apply timed debuffs. |

| 179 | Бонус за активность сообщества | Квесты, достижения, репутация, штрафы, VK/TG модерация. | flags/reputation/fines: `if condition unlock/apply`; `fine=base+level*mult`; warning stages apply timed debuffs. |

| 180 | Антинакрутка социальной награды | Квесты, достижения, репутация, штрафы, VK/TG модерация. | flags/reputation/fines: `if condition unlock/apply`; `fine=base+level*mult`; warning stages apply timed debuffs. |



### Партия 10 — мобы, боссы, элитные враги, призывы и фазы боя

| ID | Название | Куда подходит | Базовая логика / формула |
|---:|---|---|---|

| 181 | Усиленный моб | Мобы, элитные враги, боссы, мировые боссы, арены. | mob/boss: `phase by hp%`; `spawn every N turns`; `counter only direct damage`; boss control effectiveness reduced. |

| 182 | Элитный моб | Мобы, элитные враги, боссы, мировые боссы, арены. | mob/boss: `phase by hp%`; `spawn every N turns`; `counter only direct damage`; boss control effectiveness reduced. |

| 183 | Редкий вариант моба | Мобы, элитные враги, боссы, мировые боссы, арены. | mob/boss: `phase by hp%`; `spawn every N turns`; `counter only direct damage`; boss control effectiveness reduced. |

| 184 | Яростный враг | Мобы, элитные враги, боссы, мировые боссы, арены. | mob/boss: `phase by hp%`; `spawn every N turns`; `counter only direct damage`; boss control effectiveness reduced. |

| 185 | Панцирь босса | Мобы, элитные враги, боссы, мировые боссы, арены. | mob/boss: `phase by hp%`; `spawn every N turns`; `counter only direct damage`; boss control effectiveness reduced. |

| 186 | Уязвимая фаза босса | Мобы, элитные враги, боссы, мировые боссы, арены. | mob/boss: `phase by hp%`; `spawn every N turns`; `counter only direct damage`; boss control effectiveness reduced. |

| 187 | Фаза босса | Мобы, элитные враги, боссы, мировые боссы, арены. | mob/boss: `phase by hp%`; `spawn every N turns`; `counter only direct damage`; boss control effectiveness reduced. |

| 188 | Призыв помощников | Мобы, элитные враги, боссы, мировые боссы, арены. | mob/boss: `phase by hp%`; `spawn every N turns`; `counter only direct damage`; boss control effectiveness reduced. |

| 189 | Защитник босса | Мобы, элитные враги, боссы, мировые боссы, арены. | mob/boss: `phase by hp%`; `spawn every N turns`; `counter only direct damage`; boss control effectiveness reduced. |

| 190 | Связь с прислужниками | Мобы, элитные враги, боссы, мировые боссы, арены. | mob/boss: `phase by hp%`; `spawn every N turns`; `counter only direct damage`; boss control effectiveness reduced. |

| 191 | Кровавая метка | Мобы, элитные враги, боссы, мировые боссы, арены. | mob/boss: `phase by hp%`; `spawn every N turns`; `counter only direct damage`; boss control effectiveness reduced. |

| 192 | Метка охотника | Мобы, элитные враги, боссы, мировые боссы, арены. | mob/boss: `phase by hp%`; `spawn every N turns`; `counter only direct damage`; boss control effectiveness reduced. |

| 193 | Раскол строя | Мобы, элитные враги, боссы, мировые боссы, арены. | mob/boss: `phase by hp%`; `spawn every N turns`; `counter only direct damage`; boss control effectiveness reduced. |

| 194 | Подавление лечения | Мобы, элитные враги, боссы, мировые боссы, арены. | mob/boss: `phase by hp%`; `spawn every N turns`; `counter only direct damage`; boss control effectiveness reduced. |

| 195 | Боевой крик врага | Мобы, элитные враги, боссы, мировые боссы, арены. | mob/boss: `phase by hp%`; `spawn every N turns`; `counter only direct damage`; boss control effectiveness reduced. |

| 196 | Устрашающий рёв | Мобы, элитные враги, боссы, мировые боссы, арены. | mob/boss: `phase by hp%`; `spawn every N turns`; `counter only direct damage`; boss control effectiveness reduced. |

| 197 | Ответная атака | Мобы, элитные враги, боссы, мировые боссы, арены. | mob/boss: `phase by hp%`; `spawn every N turns`; `counter only direct damage`; boss control effectiveness reduced. |

| 198 | Кара за критический удар | Мобы, элитные враги, боссы, мировые боссы, арены. | mob/boss: `phase by hp%`; `spawn every N turns`; `counter only direct damage`; boss control effectiveness reduced. |

| 199 | Запрет повторного контроля босса | Мобы, элитные враги, боссы, мировые боссы, арены. | mob/boss: `phase by hp%`; `spawn every N turns`; `counter only direct damage`; boss control effectiveness reduced. |

| 200 | Боевая арена босса | Мобы, элитные враги, боссы, мировые боссы, арены. | mob/boss: `phase by hp%`; `spawn every N turns`; `counter only direct damage`; boss control effectiveness reduced. |



### Партия 11 — расходники, зелья, еда, стимуляторы и побочные эффекты

| ID | Название | Куда подходит | Базовая логика / формула |
|---:|---|---|---|

| 201 | Мгновенное зелье лечения | Зелья, еда, стимуляторы, расходники, чёрный рынок. | consumable: `use item => apply effect`; repeated use may reduce effectiveness; addiction accumulates; zone potion protects by tags. |

| 202 | Зелье регенерации | Зелья, еда, стимуляторы, расходники, чёрный рынок. | consumable: `use item => apply effect`; repeated use may reduce effectiveness; addiction accumulates; zone potion protects by tags. |

| 203 | Зелье очищения | Зелья, еда, стимуляторы, расходники, чёрный рынок. | consumable: `use item => apply effect`; repeated use may reduce effectiveness; addiction accumulates; zone potion protects by tags. |

| 204 | Зелье восстановления маны | Зелья, еда, стимуляторы, расходники, чёрный рынок. | consumable: `use item => apply effect`; repeated use may reduce effectiveness; addiction accumulates; zone potion protects by tags. |

| 205 | Зелье восстановления Духа | Зелья, еда, стимуляторы, расходники, чёрный рынок. | consumable: `use item => apply effect`; repeated use may reduce effectiveness; addiction accumulates; zone potion protects by tags. |

| 206 | Зелье энергии | Зелья, еда, стимуляторы, расходники, чёрный рынок. | consumable: `use item => apply effect`; repeated use may reduce effectiveness; addiction accumulates; zone potion protects by tags. |

| 207 | Еда | Зелья, еда, стимуляторы, расходники, чёрный рынок. | consumable: `use item => apply effect`; repeated use may reduce effectiveness; addiction accumulates; zone potion protects by tags. |

| 208 | Сытность | Зелья, еда, стимуляторы, расходники, чёрный рынок. | consumable: `use item => apply effect`; repeated use may reduce effectiveness; addiction accumulates; zone potion protects by tags. |

| 209 | Напиток бодрости | Зелья, еда, стимуляторы, расходники, чёрный рынок. | consumable: `use item => apply effect`; repeated use may reduce effectiveness; addiction accumulates; zone potion protects by tags. |

| 210 | Боевой стимулятор | Зелья, еда, стимуляторы, расходники, чёрный рынок. | consumable: `use item => apply effect`; repeated use may reduce effectiveness; addiction accumulates; zone potion protects by tags. |

| 211 | Зависимость | Зелья, еда, стимуляторы, расходники, чёрный рынок. | consumable: `use item => apply effect`; repeated use may reduce effectiveness; addiction accumulates; zone potion protects by tags. |

| 212 | Подозрительное зелье | Зелья, еда, стимуляторы, расходники, чёрный рынок. | consumable: `use item => apply effect`; repeated use may reduce effectiveness; addiction accumulates; zone potion protects by tags. |

| 213 | Нестабильное зелье | Зелья, еда, стимуляторы, расходники, чёрный рынок. | consumable: `use item => apply effect`; repeated use may reduce effectiveness; addiction accumulates; zone potion protects by tags. |

| 214 | Передозировка зельями | Зелья, еда, стимуляторы, расходники, чёрный рынок. | consumable: `use item => apply effect`; repeated use may reduce effectiveness; addiction accumulates; zone potion protects by tags. |

| 215 | Привыкание к зелью | Зелья, еда, стимуляторы, расходники, чёрный рынок. | consumable: `use item => apply effect`; repeated use may reduce effectiveness; addiction accumulates; zone potion protects by tags. |

| 216 | Зелье защиты от зоны | Зелья, еда, стимуляторы, расходники, чёрный рынок. | consumable: `use item => apply effect`; repeated use may reduce effectiveness; addiction accumulates; zone potion protects by tags. |

| 217 | Зелье временного иммунитета | Зелья, еда, стимуляторы, расходники, чёрный рынок. | consumable: `use item => apply effect`; repeated use may reduce effectiveness; addiction accumulates; zone potion protects by tags. |

| 218 | Свиток усиления | Зелья, еда, стимуляторы, расходники, чёрный рынок. | consumable: `use item => apply effect`; repeated use may reduce effectiveness; addiction accumulates; zone potion protects by tags. |

| 219 | Боевой порошок | Зелья, еда, стимуляторы, расходники, чёрный рынок. | consumable: `use item => apply effect`; repeated use may reduce effectiveness; addiction accumulates; zone potion protects by tags. |

| 220 | Дымовая завеса | Зелья, еда, стимуляторы, расходники, чёрный рынок. | consumable: `use item => apply effect`; repeated use may reduce effectiveness; addiction accumulates; zone potion protects by tags. |



### Партия 12 — метательные предметы, боеприпасы, подсумок, колчаны и ловушки

| ID | Название | Куда подходит | Базовая логика / формула |
|---:|---|---|---|

| 221 | Метательный предмет | Метательные предметы, луки, арбалеты, подсумок, ловушки. | ammo/pouch/trap: `consume ammo`; `bonus_action_cost`; `trap triggers on condition`; `bonus_actions=min(base+bonus,max)`. |

| 222 | Метательный нож | Метательные предметы, луки, арбалеты, подсумок, ловушки. | ammo/pouch/trap: `consume ammo`; `bonus_action_cost`; `trap triggers on condition`; `bonus_actions=min(base+bonus,max)`. |

| 223 | Метательный топорик | Метательные предметы, луки, арбалеты, подсумок, ловушки. | ammo/pouch/trap: `consume ammo`; `bonus_action_cost`; `trap triggers on condition`; `bonus_actions=min(base+bonus,max)`. |

| 224 | Алхимическая колба | Метательные предметы, луки, арбалеты, подсумок, ловушки. | ammo/pouch/trap: `consume ammo`; `bonus_action_cost`; `trap triggers on condition`; `bonus_actions=min(base+bonus,max)`. |

| 225 | Кислотная колба | Метательные предметы, луки, арбалеты, подсумок, ловушки. | ammo/pouch/trap: `consume ammo`; `bonus_action_cost`; `trap triggers on condition`; `bonus_actions=min(base+bonus,max)`. |

| 226 | Боеприпас | Метательные предметы, луки, арбалеты, подсумок, ловушки. | ammo/pouch/trap: `consume ammo`; `bonus_action_cost`; `trap triggers on condition`; `bonus_actions=min(base+bonus,max)`. |

| 227 | Стрела | Метательные предметы, луки, арбалеты, подсумок, ловушки. | ammo/pouch/trap: `consume ammo`; `bonus_action_cost`; `trap triggers on condition`; `bonus_actions=min(base+bonus,max)`. |

| 228 | Болт | Метательные предметы, луки, арбалеты, подсумок, ловушки. | ammo/pouch/trap: `consume ammo`; `bonus_action_cost`; `trap triggers on condition`; `bonus_actions=min(base+bonus,max)`. |

| 229 | Ядовитый боеприпас | Метательные предметы, луки, арбалеты, подсумок, ловушки. | ammo/pouch/trap: `consume ammo`; `bonus_action_cost`; `trap triggers on condition`; `bonus_actions=min(base+bonus,max)`. |

| 230 | Огненный боеприпас | Метательные предметы, луки, арбалеты, подсумок, ловушки. | ammo/pouch/trap: `consume ammo`; `bonus_action_cost`; `trap triggers on condition`; `bonus_actions=min(base+bonus,max)`. |

| 231 | Подсумок | Метательные предметы, луки, арбалеты, подсумок, ловушки. | ammo/pouch/trap: `consume ammo`; `bonus_action_cost`; `trap triggers on condition`; `bonus_actions=min(base+bonus,max)`. |

| 232 | Слот подсумка | Метательные предметы, луки, арбалеты, подсумок, ловушки. | ammo/pouch/trap: `consume ammo`; `bonus_action_cost`; `trap triggers on condition`; `bonus_actions=min(base+bonus,max)`. |

| 233 | Ограничение предметов в подсумке | Метательные предметы, луки, арбалеты, подсумок, ловушки. | ammo/pouch/trap: `consume ammo`; `bonus_action_cost`; `trap triggers on condition`; `bonus_actions=min(base+bonus,max)`. |

| 234 | Колчан | Метательные предметы, луки, арбалеты, подсумок, ловушки. | ammo/pouch/trap: `consume ammo`; `bonus_action_cost`; `trap triggers on condition`; `bonus_actions=min(base+bonus,max)`. |

| 235 | Автоподача боеприпасов | Метательные предметы, луки, арбалеты, подсумок, ловушки. | ammo/pouch/trap: `consume ammo`; `bonus_action_cost`; `trap triggers on condition`; `bonus_actions=min(base+bonus,max)`. |

| 236 | Ловушка игрока | Метательные предметы, луки, арбалеты, подсумок, ловушки. | ammo/pouch/trap: `consume ammo`; `bonus_action_cost`; `trap triggers on condition`; `bonus_actions=min(base+bonus,max)`. |

| 237 | Капкан | Метательные предметы, луки, арбалеты, подсумок, ловушки. | ammo/pouch/trap: `consume ammo`; `bonus_action_cost`; `trap triggers on condition`; `bonus_actions=min(base+bonus,max)`. |

| 238 | Ловушка с лезвиями | Метательные предметы, луки, арбалеты, подсумок, ловушки. | ammo/pouch/trap: `consume ammo`; `bonus_action_cost`; `trap triggers on condition`; `bonus_actions=min(base+bonus,max)`. |

| 239 | Блокировка использования расходников | Метательные предметы, луки, арбалеты, подсумок, ловушки. | ammo/pouch/trap: `consume ammo`; `bonus_action_cost`; `trap triggers on condition`; `bonus_actions=min(base+bonus,max)`. |

| 240 | Ограничение дополнительных действий | Метательные предметы, луки, арбалеты, подсумок, ловушки. | ammo/pouch/trap: `consume ammo`; `bonus_action_cost`; `trap triggers on condition`; `bonus_actions=min(base+bonus,max)`. |



### Партия 13 — скрытые события, условия открытия, пороги и скрытые награды

| ID | Название | Куда подходит | Базовая логика / формула |
|---:|---|---|---|

| 241 | Скрытое событие | Скрытые события, локации, амулеты, Древние, проклятья. | unlock/counter: `if all(required) and not any(blocking) unlock`; counters trigger stages; special cleanse only by required method. |

| 242 | Единое условие открытия | Скрытые события, локации, амулеты, Древние, проклятья. | unlock/counter: `if all(required) and not any(blocking) unlock`; counters trigger stages; special cleanse only by required method. |

| 243 | Счётчик поисков локации | Скрытые события, локации, амулеты, Древние, проклятья. | unlock/counter: `if all(required) and not any(blocking) unlock`; counters trigger stages; special cleanse only by required method. |

| 244 | Пороговый эффект | Скрытые события, локации, амулеты, Древние, проклятья. | unlock/counter: `if all(required) and not any(blocking) unlock`; counters trigger stages; special cleanse only by required method. |

| 245 | Реакция амулета | Скрытые события, локации, амулеты, Древние, проклятья. | unlock/counter: `if all(required) and not any(blocking) unlock`; counters trigger stages; special cleanse only by required method. |

| 246 | Ожог от амулета | Скрытые события, локации, амулеты, Древние, проклятья. | unlock/counter: `if all(required) and not any(blocking) unlock`; counters trigger stages; special cleanse only by required method. |

| 247 | Тяжёлый ожог от амулета | Скрытые события, локации, амулеты, Древние, проклятья. | unlock/counter: `if all(required) and not any(blocking) unlock`; counters trigger stages; special cleanse only by required method. |

| 248 | Достижение за долгий поиск | Скрытые события, локации, амулеты, Древние, проклятья. | unlock/counter: `if all(required) and not any(blocking) unlock`; counters trigger stages; special cleanse only by required method. |

| 249 | Открытие скрытых действий | Скрытые события, локации, амулеты, Древние, проклятья. | unlock/counter: `if all(required) and not any(blocking) unlock`; counters trigger stages; special cleanse only by required method. |

| 250 | Открытие скрытых наград | Скрытые события, локации, амулеты, Древние, проклятья. | unlock/counter: `if all(required) and not any(blocking) unlock`; counters trigger stages; special cleanse only by required method. |

| 251 | Скрытая подсказка | Скрытые события, локации, амулеты, Древние, проклятья. | unlock/counter: `if all(required) and not any(blocking) unlock`; counters trigger stages; special cleanse only by required method. |

| 252 | Скрытая цепочка события | Скрытые события, локации, амулеты, Древние, проклятья. | unlock/counter: `if all(required) and not any(blocking) unlock`; counters trigger stages; special cleanse only by required method. |

| 253 | Скрытый предмет-ключ | Скрытые события, локации, амулеты, Древние, проклятья. | unlock/counter: `if all(required) and not any(blocking) unlock`; counters trigger stages; special cleanse only by required method. |

| 254 | Скрытое место | Скрытые события, локации, амулеты, Древние, проклятья. | unlock/counter: `if all(required) and not any(blocking) unlock`; counters trigger stages; special cleanse only by required method. |

| 255 | Древняя метка | Скрытые события, локации, амулеты, Древние, проклятья. | unlock/counter: `if all(required) and not any(blocking) unlock`; counters trigger stages; special cleanse only by required method. |

| 256 | Неснимаемое проклятье | Скрытые события, локации, амулеты, Древние, проклятья. | unlock/counter: `if all(required) and not any(blocking) unlock`; counters trigger stages; special cleanse only by required method. |

| 257 | Древнее проклятье переноса | Скрытые события, локации, амулеты, Древние, проклятья. | unlock/counter: `if all(required) and not any(blocking) unlock`; counters trigger stages; special cleanse only by required method. |

| 258 | Снятие проклятья через жертву | Скрытые события, локации, амулеты, Древние, проклятья. | unlock/counter: `if all(required) and not any(blocking) unlock`; counters trigger stages; special cleanse only by required method. |

| 259 | Достижение за жизнь с проклятьем | Скрытые события, локации, амулеты, Древние, проклятья. | unlock/counter: `if all(required) and not any(blocking) unlock`; counters trigger stages; special cleanse only by required method. |

| 260 | Ослабление проклятий от достижения | Скрытые события, локации, амулеты, Древние, проклятья. | unlock/counter: `if all(required) and not any(blocking) unlock`; counters trigger stages; special cleanse only by required method. |



### Партия 14 — дом, библиотека, записи, книги, картины и открытия лора

| ID | Название | Куда подходит | Базовая логика / формула |
|---:|---|---|---|

| 261 | Дом игрока | Дом, библиотека, лор, коллекции, рецепты, домашние бонусы. | home/library: `if found lore add_to_library`; `if placed in home apply home bonus`; rest uses home modifiers. |

| 262 | Уровень дома | Дом, библиотека, лор, коллекции, рецепты, домашние бонусы. | home/library: `if found lore add_to_library`; `if placed in home apply home bonus`; rest uses home modifiers. |

| 263 | Домашнее хранилище | Дом, библиотека, лор, коллекции, рецепты, домашние бонусы. | home/library: `if found lore add_to_library`; `if placed in home apply home bonus`; rest uses home modifiers. |

| 264 | Библиотека игрока | Дом, библиотека, лор, коллекции, рецепты, домашние бонусы. | home/library: `if found lore add_to_library`; `if placed in home apply home bonus`; rest uses home modifiers. |

| 265 | Запись в библиотеку | Дом, библиотека, лор, коллекции, рецепты, домашние бонусы. | home/library: `if found lore add_to_library`; `if placed in home apply home bonus`; rest uses home modifiers. |

| 266 | Фрагмент древней записи | Дом, библиотека, лор, коллекции, рецепты, домашние бонусы. | home/library: `if found lore add_to_library`; `if placed in home apply home bonus`; rest uses home modifiers. |

| 267 | Собранная книга | Дом, библиотека, лор, коллекции, рецепты, домашние бонусы. | home/library: `if found lore add_to_library`; `if placed in home apply home bonus`; rest uses home modifiers. |

| 268 | Картина | Дом, библиотека, лор, коллекции, рецепты, домашние бонусы. | home/library: `if found lore add_to_library`; `if placed in home apply home bonus`; rest uses home modifiers. |

| 269 | Стенд коллекции | Дом, библиотека, лор, коллекции, рецепты, домашние бонусы. | home/library: `if found lore add_to_library`; `if placed in home apply home bonus`; rest uses home modifiers. |

| 270 | Коллекционный прогресс | Дом, библиотека, лор, коллекции, рецепты, домашние бонусы. | home/library: `if found lore add_to_library`; `if placed in home apply home bonus`; rest uses home modifiers. |

| 271 | Полная коллекция | Дом, библиотека, лор, коллекции, рецепты, домашние бонусы. | home/library: `if found lore add_to_library`; `if placed in home apply home bonus`; rest uses home modifiers. |

| 272 | Лор как условие открытия | Дом, библиотека, лор, коллекции, рецепты, домашние бонусы. | home/library: `if found lore add_to_library`; `if placed in home apply home bonus`; rest uses home modifiers. |

| 273 | Знание рецепта | Дом, библиотека, лор, коллекции, рецепты, домашние бонусы. | home/library: `if found lore add_to_library`; `if placed in home apply home bonus`; rest uses home modifiers. |

| 274 | Изучение книги | Дом, библиотека, лор, коллекции, рецепты, домашние бонусы. | home/library: `if found lore add_to_library`; `if placed in home apply home bonus`; rest uses home modifiers. |

| 275 | Древнее знание | Дом, библиотека, лор, коллекции, рецепты, домашние бонусы. | home/library: `if found lore add_to_library`; `if placed in home apply home bonus`; rest uses home modifiers. |

| 276 | Подсказка из библиотеки | Дом, библиотека, лор, коллекции, рецепты, домашние бонусы. | home/library: `if found lore add_to_library`; `if placed in home apply home bonus`; rest uses home modifiers. |

| 277 | Бонус отдыха дома | Дом, библиотека, лор, коллекции, рецепты, домашние бонусы. | home/library: `if found lore add_to_library`; `if placed in home apply home bonus`; rest uses home modifiers. |

| 278 | Домашняя защита от проклятий | Дом, библиотека, лор, коллекции, рецепты, домашние бонусы. | home/library: `if found lore add_to_library`; `if placed in home apply home bonus`; rest uses home modifiers. |

| 279 | Памятный предмет | Дом, библиотека, лор, коллекции, рецепты, домашние бонусы. | home/library: `if found lore add_to_library`; `if placed in home apply home bonus`; rest uses home modifiers. |

| 280 | Архив открытых знаний | Дом, библиотека, лор, коллекции, рецепты, домашние бонусы. | home/library: `if found lore add_to_library`; `if placed in home apply home bonus`; rest uses home modifiers. |



### Партия 15 — профиль, передача, посылки, рефералы и сервисы

| ID | Название | Куда подходит | Базовая логика / формула |
|---:|---|---|---|

| 281 | Реферальная метка игрока | Профиль, сервисы, рефералы, передача, промокоды, торговля. | services: `transfer_cost=10*level*0.3+bonus_or_penalty`; direct bot notifications; log all actions. |

| 282 | Временная реферальная ссылка | Профиль, сервисы, рефералы, передача, промокоды, торговля. | services: `transfer_cost=10*level*0.3+bonus_or_penalty`; direct bot notifications; log all actions. |

| 283 | Награда за переход по реферальной ссылке | Профиль, сервисы, рефералы, передача, промокоды, торговля. | services: `transfer_cost=10*level*0.3+bonus_or_penalty`; direct bot notifications; log all actions. |

| 284 | Награда за регистрацию реферала | Профиль, сервисы, рефералы, передача, промокоды, торговля. | services: `transfer_cost=10*level*0.3+bonus_or_penalty`; direct bot notifications; log all actions. |

| 285 | Реферальные рубежи | Профиль, сервисы, рефералы, передача, промокоды, торговля. | services: `transfer_cost=10*level*0.3+bonus_or_penalty`; direct bot notifications; log all actions. |

| 286 | Награда за уровень реферала | Профиль, сервисы, рефералы, передача, промокоды, торговля. | services: `transfer_cost=10*level*0.3+bonus_or_penalty`; direct bot notifications; log all actions. |

| 287 | Бонус наставника | Профиль, сервисы, рефералы, передача, промокоды, торговля. | services: `transfer_cost=10*level*0.3+bonus_or_penalty`; direct bot notifications; log all actions. |

| 288 | Передача предметов игроку | Профиль, сервисы, рефералы, передача, промокоды, торговля. | services: `transfer_cost=10*level*0.3+bonus_or_penalty`; direct bot notifications; log all actions. |

| 289 | Доставка посылки | Профиль, сервисы, рефералы, передача, промокоды, торговля. | services: `transfer_cost=10*level*0.3+bonus_or_penalty`; direct bot notifications; log all actions. |

| 290 | Сообщение к посылке | Профиль, сервисы, рефералы, передача, промокоды, торговля. | services: `transfer_cost=10*level*0.3+bonus_or_penalty`; direct bot notifications; log all actions. |

| 291 | Подарок от высших сил | Профиль, сервисы, рефералы, передача, промокоды, торговля. | services: `transfer_cost=10*level*0.3+bonus_or_penalty`; direct bot notifications; log all actions. |

| 292 | Промокод | Профиль, сервисы, рефералы, передача, промокоды, торговля. | services: `transfer_cost=10*level*0.3+bonus_or_penalty`; direct bot notifications; log all actions. |

| 293 | Лимит использования промокода | Профиль, сервисы, рефералы, передача, промокоды, торговля. | services: `transfer_cost=10*level*0.3+bonus_or_penalty`; direct bot notifications; log all actions. |

| 294 | Торговый павильон игрока | Профиль, сервисы, рефералы, передача, промокоды, торговля. | services: `transfer_cost=10*level*0.3+bonus_or_penalty`; direct bot notifications; log all actions. |

| 295 | Комиссия торгового павильона | Профиль, сервисы, рефералы, передача, промокоды, торговля. | services: `transfer_cost=10*level*0.3+bonus_or_penalty`; direct bot notifications; log all actions. |

| 296 | Защита от передачи запрещённых предметов | Профиль, сервисы, рефералы, передача, промокоды, торговля. | services: `transfer_cost=10*level*0.3+bonus_or_penalty`; direct bot notifications; log all actions. |

| 297 | Бонус безопасной сделки | Профиль, сервисы, рефералы, передача, промокоды, торговля. | services: `transfer_cost=10*level*0.3+bonus_or_penalty`; direct bot notifications; log all actions. |

| 298 | Блокировка сервиса профиля | Профиль, сервисы, рефералы, передача, промокоды, торговля. | services: `transfer_cost=10*level*0.3+bonus_or_penalty`; direct bot notifications; log all actions. |

| 299 | Уведомление игрока от бота | Профиль, сервисы, рефералы, передача, промокоды, торговля. | services: `transfer_cost=10*level*0.3+bonus_or_penalty`; direct bot notifications; log all actions. |

| 300 | Журнал сервисных действий | Профиль, сервисы, рефералы, передача, промокоды, торговля. | services: `transfer_cost=10*level*0.3+bonus_or_penalty`; direct bot notifications; log all actions. |



### Дополнение A — уникальные защиты и атаки мобов с контр-зельями

| ID | Название | Куда подходит | Базовая логика / формула |
|---:|---|---|---|

| 301 | Уникальная защита моба | Уникальные мобы, боссы, элитные враги, контр-зелья. | unique mob: `if potion.counter_tag in mob.tags apply weaken`; wrong type has low effectiveness; duration_turns limits weakening. |

| 302 | Уникальная атака моба | Уникальные мобы, боссы, элитные враги, контр-зелья. | unique mob: `if potion.counter_tag in mob.tags apply weaken`; wrong type has low effectiveness; duration_turns limits weakening. |

| 303 | Зелье ослабления защиты | Уникальные мобы, боссы, элитные враги, контр-зелья. | unique mob: `if potion.counter_tag in mob.tags apply weaken`; wrong type has low effectiveness; duration_turns limits weakening. |

| 304 | Зелье ослабления атаки | Уникальные мобы, боссы, элитные враги, контр-зелья. | unique mob: `if potion.counter_tag in mob.tags apply weaken`; wrong type has low effectiveness; duration_turns limits weakening. |

| 305 | Огненный панцирь | Уникальные мобы, боссы, элитные враги, контр-зелья. | unique mob: `if potion.counter_tag in mob.tags apply weaken`; wrong type has low effectiveness; duration_turns limits weakening. |

| 306 | Каменная шкура | Уникальные мобы, боссы, элитные враги, контр-зелья. | unique mob: `if potion.counter_tag in mob.tags apply weaken`; wrong type has low effectiveness; duration_turns limits weakening. |

| 307 | Ледяная броня | Уникальные мобы, боссы, элитные враги, контр-зелья. | unique mob: `if potion.counter_tag in mob.tags apply weaken`; wrong type has low effectiveness; duration_turns limits weakening. |

| 308 | Ядовитая кожа | Уникальные мобы, боссы, элитные враги, контр-зелья. | unique mob: `if potion.counter_tag in mob.tags apply weaken`; wrong type has low effectiveness; duration_turns limits weakening. |

| 309 | Кислотная кровь | Уникальные мобы, боссы, элитные враги, контр-зелья. | unique mob: `if potion.counter_tag in mob.tags apply weaken`; wrong type has low effectiveness; duration_turns limits weakening. |

| 310 | Панцирь отражения | Уникальные мобы, боссы, элитные враги, контр-зелья. | unique mob: `if potion.counter_tag in mob.tags apply weaken`; wrong type has low effectiveness; duration_turns limits weakening. |

| 311 | Панцирь против оружия | Уникальные мобы, боссы, элитные враги, контр-зелья. | unique mob: `if potion.counter_tag in mob.tags apply weaken`; wrong type has low effectiveness; duration_turns limits weakening. |

| 312 | Щит древней магии | Уникальные мобы, боссы, элитные враги, контр-зелья. | unique mob: `if potion.counter_tag in mob.tags apply weaken`; wrong type has low effectiveness; duration_turns limits weakening. |

| 313 | Непробиваемая стойка | Уникальные мобы, боссы, элитные враги, контр-зелья. | unique mob: `if potion.counter_tag in mob.tags apply weaken`; wrong type has low effectiveness; duration_turns limits weakening. |

| 314 | Кровавая атака | Уникальные мобы, боссы, элитные враги, контр-зелья. | unique mob: `if potion.counter_tag in mob.tags apply weaken`; wrong type has low effectiveness; duration_turns limits weakening. |

| 315 | Морозный выпад | Уникальные мобы, боссы, элитные враги, контр-зелья. | unique mob: `if potion.counter_tag in mob.tags apply weaken`; wrong type has low effectiveness; duration_turns limits weakening. |

| 316 | Ядовитый плевок | Уникальные мобы, боссы, элитные враги, контр-зелья. | unique mob: `if potion.counter_tag in mob.tags apply weaken`; wrong type has low effectiveness; duration_turns limits weakening. |

| 317 | Сокрушающий удар | Уникальные мобы, боссы, элитные враги, контр-зелья. | unique mob: `if potion.counter_tag in mob.tags apply weaken`; wrong type has low effectiveness; duration_turns limits weakening. |

| 318 | Вихревая атака | Уникальные мобы, боссы, элитные враги, контр-зелья. | unique mob: `if potion.counter_tag in mob.tags apply weaken`; wrong type has low effectiveness; duration_turns limits weakening. |

| 319 | Проклятый укус | Уникальные мобы, боссы, элитные враги, контр-зелья. | unique mob: `if potion.counter_tag in mob.tags apply weaken`; wrong type has low effectiveness; duration_turns limits weakening. |

| 320 | Неподходящее зелье | Уникальные мобы, боссы, элитные враги, контр-зелья. | unique mob: `if potion.counter_tag in mob.tags apply weaken`; wrong type has low effectiveness; duration_turns limits weakening. |



### Дополнение B — эффекты после отдыха дома

| ID | Название | Куда подходит | Базовая логика / формула |
|---:|---|---|---|

| 321 | Свежие силы | Дом, мебель, комнаты, улучшения, отдых, временные бонусы. | home rest: `if rest_at_home and requirements met apply timed buff`; `bonus=min(max, base+home_level*step+furniture_bonus)`. |

| 322 | Домашний покой | Дом, мебель, комнаты, улучшения, отдых, временные бонусы. | home rest: `if rest_at_home and requirements met apply timed buff`; `bonus=min(max, base+home_level*step+furniture_bonus)`. |

| 323 | Сон в удобной кровати | Дом, мебель, комнаты, улучшения, отдых, временные бонусы. | home rest: `if rest_at_home and requirements met apply timed buff`; `bonus=min(max, base+home_level*step+furniture_bonus)`. |

| 324 | Бодрое утро | Дом, мебель, комнаты, улучшения, отдых, временные бонусы. | home rest: `if rest_at_home and requirements met apply timed buff`; `bonus=min(max, base+home_level*step+furniture_bonus)`. |

| 325 | Разминка после отдыха | Дом, мебель, комнаты, улучшения, отдых, временные бонусы. | home rest: `if rest_at_home and requirements met apply timed buff`; `bonus=min(max, base+home_level*step+furniture_bonus)`. |

| 326 | Тихое чтение | Дом, мебель, комнаты, улучшения, отдых, временные бонусы. | home rest: `if rest_at_home and requirements met apply timed buff`; `bonus=min(max, base+home_level*step+furniture_bonus)`. |

| 327 | Домашняя медитация Маны | Дом, мебель, комнаты, улучшения, отдых, временные бонусы. | home rest: `if rest_at_home and requirements met apply timed buff`; `bonus=min(max, base+home_level*step+furniture_bonus)`. |

| 328 | Тренировка Духа дома | Дом, мебель, комнаты, улучшения, отдых, временные бонусы. | home rest: `if rest_at_home and requirements met apply timed buff`; `bonus=min(max, base+home_level*step+furniture_bonus)`. |

| 329 | Уютный завтрак | Дом, мебель, комнаты, улучшения, отдых, временные бонусы. | home rest: `if rest_at_home and requirements met apply timed buff`; `bonus=min(max, base+home_level*step+furniture_bonus)`. |

| 330 | Сон перед походом | Дом, мебель, комнаты, улучшения, отдых, временные бонусы. | home rest: `if rest_at_home and requirements met apply timed buff`; `bonus=min(max, base+home_level*step+furniture_bonus)`. |

| 331 | Рабочий настрой ремесленника | Дом, мебель, комнаты, улучшения, отдых, временные бонусы. | home rest: `if rest_at_home and requirements met apply timed buff`; `bonus=min(max, base+home_level*step+furniture_bonus)`. |

| 332 | Вдохновение алхимика | Дом, мебель, комнаты, улучшения, отдых, временные бонусы. | home rest: `if rest_at_home and requirements met apply timed buff`; `bonus=min(max, base+home_level*step+furniture_bonus)`. |

| 333 | Настрой торговца | Дом, мебель, комнаты, улучшения, отдых, временные бонусы. | home rest: `if rest_at_home and requirements met apply timed buff`; `bonus=min(max, base+home_level*step+furniture_bonus)`. |

| 334 | Память о доме | Дом, мебель, комнаты, улучшения, отдых, временные бонусы. | home rest: `if rest_at_home and requirements met apply timed buff`; `bonus=min(max, base+home_level*step+furniture_bonus)`. |

| 335 | Защита родного очага | Дом, мебель, комнаты, улучшения, отдых, временные бонусы. | home rest: `if rest_at_home and requirements met apply timed buff`; `bonus=min(max, base+home_level*step+furniture_bonus)`. |

| 336 | Сытый отдых | Дом, мебель, комнаты, улучшения, отдых, временные бонусы. | home rest: `if rest_at_home and requirements met apply timed buff`; `bonus=min(max, base+home_level*step+furniture_bonus)`. |

| 337 | Собранные мысли | Дом, мебель, комнаты, улучшения, отдых, временные бонусы. | home rest: `if rest_at_home and requirements met apply timed buff`; `bonus=min(max, base+home_level*step+furniture_bonus)`. |

| 338 | Порядок в снаряжении | Дом, мебель, комнаты, улучшения, отдых, временные бонусы. | home rest: `if rest_at_home and requirements met apply timed buff`; `bonus=min(max, base+home_level*step+furniture_bonus)`. |

| 339 | Отдых после травмы | Дом, мебель, комнаты, улучшения, отдых, временные бонусы. | home rest: `if rest_at_home and requirements met apply timed buff`; `bonus=min(max, base+home_level*step+furniture_bonus)`. |

| 340 | Домашний благословенный день | Дом, мебель, комнаты, улучшения, отдых, временные бонусы. | home rest: `if rest_at_home and requirements met apply timed buff`; `bonus=min(max, base+home_level*step+furniture_bonus)`. |


---

## 5. Детализация критически важных правок

### 5.1. Травма правой руки

**Назначение:** капканы, удар по вооружённой руке, критический удар, атака моба, ловушка с лезвием, проклятие оружия, неудачное ремесло.  
**Эффект:** снижает точность/урон и временно блокирует слот `weapon1`.

```ts
if right_arm_injury_active:
  final_accuracy = max(min_accuracy, base_accuracy - right_arm_accuracy_penalty)
  final_physical_damage = base_physical_damage * (1 - right_arm_damage_penalty_percent / 100)
  block_slot('weapon1')
```

Предмет в слоте не исчезает и не ломается. Он остаётся надетым, но временно недоступен для атак, навыков и смены.

### 5.2. Травма левой руки

**Назначение:** удар по дополнительной руке, травма щитом, атака зверя, ловушка, критический удар.  
**Эффект:** снижает эффективность offhand и временно блокирует слот `weapon2`.

```ts
if left_arm_injury_active:
  final_offhand_effectiveness = base_offhand_effectiveness * (1 - left_arm_effectiveness_penalty_percent / 100)
  block_slot('weapon2')
```

Если во втором слоте был щит, книга, колчан, второе оружие или другой предмет, он остаётся надетым, но временно не работает.

### 5.3. Временная блокировка оружейного слота

```ts
type TemporarySlotBlock = {
  effect_type: 'temporary_slot_block';
  blocked_slot: 'weapon1' | 'weapon2';
  block_equip: true;
  block_unequip: true;
  block_use: true;
  block_skills_requiring_slot: true;
  duration_turns?: number;
  duration_seconds?: number;
  cleanse_tags: ['trauma', 'control', 'curse'];
};
```

---

## 6. Система уникальных мобов с контр-зельями

### 6.1. Модель уникального свойства моба

```ts
type UniqueMobTrait = {
  trait_id: string;
  trait_name: string;
  trait_kind: 'unique_defense' | 'unique_attack' | 'unique_counterattack' | 'phase_trait';
  tags: string[]; // fire_shell, stone_skin, ice_armor, poison_skin, mirror_shell, blood_attack, frost_attack...
  player_hint: string; // подсказка в бою, без формул
  base_power_percent: number;
  duration_mode: 'always' | 'phase' | 'turn_limited';
  can_be_weakened: boolean;
  required_counter_tags: string[];
  wrong_type_effectiveness_percent: number;
  boss_effectiveness_percent: number;
};
```

### 6.2. Модель контр-зелья

```ts
type CounterPotion = {
  item_id: string;
  item_name: string;
  potion_kind: 'defense_weaken' | 'attack_weaken' | 'mixed_weaken';
  counter_tags: string[];
  weakening_percent: number;
  duration_turns: number;
  duration_seconds?: number;
  wrong_type_effectiveness_percent: number;
  boss_effectiveness_percent: number;
  consume_on_use: true;
};
```

### 6.3. Алгоритм применения контр-зелья

```ts
function applyCounterPotion(potion, mob) {
  const matched = potion.counter_tags.some(tag => mob.unique_tags.includes(tag));
  let effectiveness = potion.weakening_percent;

  if (!matched) effectiveness *= potion.wrong_type_effectiveness_percent / 100;
  if (mob.rank === 'boss' || mob.rank === 'unique') effectiveness *= potion.boss_effectiveness_percent / 100;

  applyTimedWeakening(mob, effectiveness, potion.duration_turns);
  consumeItem(potion.item_id);
}
```

### 6.4. Теги уникальных защит

| Тег | Смысл | Подходящее зелье |
|---|---|---|
| `fire_shell` | Огненный панцирь, ответный поджог | Зелье охлаждения панциря |
| `stone_skin` | Каменная шкура, защита от физики | Кислотная колба размягчения |
| `ice_armor` | Ледяная броня, штраф точности | Согревающее зелье трещин |
| `poison_skin` | Ядовитая кожа, ответный яд | Зелье нейтрализации яда |
| `acid_blood` | Кислотная кровь, ответный урон/износ | Щелочной состав нейтрализации |
| `mirror_shell` | Магическое отражение | Зелье помутнения зеркала |
| `weapon_resistance` | Сопротивление обычному оружию | Разъедающая смазка |
| `ancient_magic_shield` | Щит древней магии | Зелье рассеивания древней магии |
| `stance_defense` | Непробиваемая стойка | Зелье сбивания стойки |

### 6.5. Теги уникальных атак

| Тег | Смысл | Подходящее зелье |
|---|---|---|
| `blood_attack` | Кровавая атака + кровотечение | Зелье сгущения крови |
| `frost_attack` | Морозный выпад + заморозка | Зелье тёплого дыхания |
| `poison_spit` | Ядовитый плевок | Зелье нейтрализации токсинов |
| `crushing_attack` | Сокрушающий удар + оглушение | Зелье ослабления мышц |
| `wind_attack` | Вихревая атака, несколько ударов | Зелье утяжеления воздуха |
| `curse_bite` | Проклятый укус | Зелье чистой крови |

---

## 7. Эффекты после отдыха дома

### 7.1. Правило выдачи

Эффект отдыха дома выдаётся после завершённого отдыха в доме, комнате или улучшенном месте отдыха. Сила зависит от уровня дома, мебели, качества комнаты и специальных предметов.

```ts
type HomeRestBonus = {
  effect_id: string;
  required_home_level?: number;
  required_room?: 'bedroom' | 'library' | 'workshop' | 'alchemy_room' | 'training_room' | 'kitchen' | 'shrine';
  required_furniture_tags?: string[];
  duration_seconds: number;
  max_daily_triggers?: number;
  stack_rule: 'refresh' | 'strongest_only' | 'unique_only';
  bonus_fields: Record<string, number>;
};
```

### 7.2. Примеры домашних бонусов

| ID | Название | Эффект | Формула |
|---:|---|---|---|
| 321 | Свежие силы | +к max энергии после отдыха | `final_max_energy = base_max_energy * (1 + bonus_percent/100)` |
| 322 | Домашний покой | +к восстановлению HP/маны/Духа | `restore = base_restore * (1 + home_restore_bonus/100)` |
| 323 | Сон в удобной кровати | +к выносливости временно | `final_endurance = base_endurance + flat + base_endurance*percent/100` |
| 324 | Бодрое утро | меньше расход энергии на поиск | `final_energy_cost = base_energy_cost * (1 - reduction/100)` |
| 325 | Разминка после отдыха | +к силе/ловкости для физических боёв | `final_strength/agility += bonus` |
| 326 | Тихое чтение | +к мудрости/интеллекту | `final_wisdom/intelligence += bonus` |
| 327 | Домашняя медитация Маны | +к max mana или regen mana | `final_max_mana = base * (1 + bonus/100)` |
| 328 | Тренировка Духа дома | +к max spirit или сниженный расход Духа | `final_spirit_cost = base_cost * (1 - reduction/100)` |
| 329 | Уютный завтрак | +к монетам с PVE/заданий на время | `final_coins = base_coins * (1 + coin_bonus/100)` |
| 330 | Сон перед походом | +к шансу мирных событий | `event_chance = base * (1 + bonus/100)` |
| 331 | Рабочий настрой ремесленника | +к успеху крафта | `craft_success = base + bonus_percent` |
| 332 | Вдохновение алхимика | +к силе/успеху зелий | `potion_power = base * (1 + bonus/100)` |
| 333 | Настрой торговца | скидка/бонус продажи | `price = base * (1 ± bonus/100)` |
| 334 | Память о доме | +к опыту на время | `exp_gain = base_exp * (1 + exp_bonus/100)` |
| 335 | Защита родного очага | сопротивление проклятьям | `curse_chance = base * (1 - resist/100)` |
| 336 | Сытый отдых | меньше штрафов усталости | `exhaustion_power = base * (1 - reduction/100)` |
| 337 | Собранные мысли | +точность/крит после отдыха | `accuracy=clamp(base+bonus,min,max)` |
| 338 | Порядок в снаряжении | быстрее смена/ремонт/меньше износ | `durability_loss = base_loss * (1 - reduction/100)` |
| 339 | Отдых после травмы | ускоряет снятие травм | `trauma_duration_tick = base_tick * (1 + recovery_bonus/100)` |
| 340 | Домашний благословенный день | малый комплексный баф | `apply selected stat/resource/event bonuses with caps` |

### 7.3. Ограничения домашних бонусов

- Домашние бонусы не должны стакаться бесконечно: `stack_rule=refresh` или `strongest_only`.
- Желательно ограничить выдачу 1–3 раза в день по типу бонуса.
- Боевые бонусы от дома должны быть умеренными: обычно 1–5%, сильные — через редкую мебель/улучшения/заряды.
- Бонус к опыту/монетам лучше делать временным и с дневным лимитом.
- Домашний отдых не снимает сюжетные/неснимаемые проклятья без специальных условий.

---

## 8. Минимальный список задач для Claude Code

1. Создать/расширить модель `EffectDefinition` и `ActiveEffect`.
2. Добавить универсальные типы эффектов из раздела 3.
3. Реализовать caps: уклонение 35%, крит 49%, точность 5–95%, характеристики минимум 1.
4. Реализовать запрет цепочек для periodic/response damage.
5. Реализовать `slot_block` для `weapon1`/`weapon2` и травмы правой/левой руки.
6. Реализовать `spirit` как физический ресурс, `mana` как магический ресурс.
7. Реализовать долгие проклятья и правило достижения для PVP-посмертных проклятий.
8. Реализовать зоны и защиту от зон.
9. Реализовать item lifecycle: заряды, прочность, хрупкость, привязки, уникальность.
10. Реализовать unique mob traits + counter potions.
11. Реализовать home rest bonuses.
12. Добавить админские поля на русском языке и предпросмотр текста игроку без формул.
13. Добавить логирование всех важных срабатываний: эффект, источник, цель, время, результат.
14. Добавить валидацию: caps, запрещённые теги, wrong potion effectiveness, boss effectiveness, max stacks.
15. Подготовить seed/миграцию реестра эффектов из этого ТЗ.
