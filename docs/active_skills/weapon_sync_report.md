# Отчёт синхронизации активных навыков с оружием

Проверены все 94 навыка. Недопустимые типы оружия удалены или заменены.


## Правило нескольких оружий

У части навыков может быть несколько допустимых видов оружия. Это не ошибка. В таких случаях `weapon_requirements` содержит список, а проверка работает по `any_of`: игрок может использовать навык, если экипировано хотя бы одно подходящее оружие из списка.

## Поддерживаемое оружие

- `sword` — меч: 23 навыков
- `dagger` — кинжал: 18 навыков
- `staff` — посох: 43 навыков
- `axe` — топор: 18 навыков
- `hammer` — молот: 12 навыков
- `bow` — лук: 3 навыков
- `shield` — щит: 6 навыков
- `crossbow` — арбалет: 3 навыков
- `any` — универсальные действия: 36 навыков

## Замены
- `any_melee` — раскрыт в sword, dagger, staff, axe, hammer.
- `spear` — заменён на staff, потому что копьё сейчас не входит в список оружия проекта.
- `focus` — заменён на staff, потому что магический фокус сейчас не входит в список оружия проекта.
- `unarmed` — удалён из требований: безоружный бой сейчас не входит в список оружия проекта.
- `two_handed_sword` — заменён на sword как подтип меча.
- `heavy_armor` — перенесён из оружейных требований в equipment_requirements.
- `medium_armor` — перенесён из оружейных требований в equipment_requirements.

## Меч (`sword`)
- Обычный удар (`neutral_basic_strike`) — neutral, attack/basic_melee
- Сильный удар (`spirit_power_strike`) — spirit, attack/heavy_melee
- Точный выпад (`spirit_precise_thrust`) — spirit, attack/precision_melee
- Парирование (`spirit_parry`) — spirit, defense/reaction
- Боевой рывок (`spirit_quick_dash`) — spirit, attack/mobility
- Широкий взмах (`spirit_sweeping_cut`) — spirit, attack/cleave
- Кровавый разрез (`spirit_bleeding_cut`) — spirit, attack/bleed
- Прорыв обороны (`spirit_breakthrough`) — spirit, attack/armor_pierce
- Вихрь стали (`spirit_whirlwind`) — spirit, attack/melee_aoe
- Смертельный выпад (`spirit_execution_thrust`) — spirit, attack/execute
- Поток ответных ударов (`spirit_counter_flow`) — spirit, attack/counter_combo
- Удар колосса (`spirit_colossus_blow`) — spirit, attack/ultimate_heavy
- Силовой толчок (`char_str_50_force_push`) — spirit, control/characteristic_special
- Тяжёлый раскол (`char_str_100_heavy_crack`) — spirit, attack/characteristic_special
- Грубое давление (`char_str_250_brutal_pressure`) — spirit, attack/characteristic_special
- Титанический замах (`char_str_500_titan_swing`) — spirit, attack/characteristic_special
- Давление великана (`char_str_1000_giant_pressure`) — spirit, control/characteristic_special
- Разломная сила (`char_str_2500_rift_strength`) — spirit, attack/characteristic_special
- Ответный выпад (`char_agi_100_reply_lunge`) — spirit, attack/characteristic_special
- Танец клинка (`char_agi_250_blade_dance`) — spirit, attack/characteristic_special
- Серия без дыхания (`char_agi_1000_breathless_series`) — spirit, attack/characteristic_special
- Исчезающий рывок (`char_agi_2500_vanishing_dash`) — spirit, attack/characteristic_special
- Прицельный разрез (`char_per_100_aimed_cut`) — spirit, attack/characteristic_special

## Кинжал (`dagger`)
- Обычный удар (`neutral_basic_strike`) — neutral, attack/basic_melee
- Сильный удар (`spirit_power_strike`) — spirit, attack/heavy_melee
- Точный выпад (`spirit_precise_thrust`) — spirit, attack/precision_melee
- Парирование (`spirit_parry`) — spirit, defense/reaction
- Боевой рывок (`spirit_quick_dash`) — spirit, attack/mobility
- Кровавый разрез (`spirit_bleeding_cut`) — spirit, attack/bleed
- Метка охотника (`spirit_hunter_mark`) — spirit, support/mark
- Смертельный выпад (`spirit_execution_thrust`) — spirit, attack/execute
- Поток ответных ударов (`spirit_counter_flow`) — spirit, attack/counter_combo
- Теневая игла (`mana_shadow_needle`) — mana, attack/shadow
- Силовой толчок (`char_str_50_force_push`) — spirit, control/characteristic_special
- Грубое давление (`char_str_250_brutal_pressure`) — spirit, attack/characteristic_special
- Давление великана (`char_str_1000_giant_pressure`) — spirit, control/characteristic_special
- Ответный выпад (`char_agi_100_reply_lunge`) — spirit, attack/characteristic_special
- Танец клинка (`char_agi_250_blade_dance`) — spirit, attack/characteristic_special
- Серия без дыхания (`char_agi_1000_breathless_series`) — spirit, attack/characteristic_special
- Исчезающий рывок (`char_agi_2500_vanishing_dash`) — spirit, attack/characteristic_special
- Прицельный разрез (`char_per_100_aimed_cut`) — spirit, attack/characteristic_special

## Посох (`staff`)
- Обычный удар (`neutral_basic_strike`) — neutral, attack/basic_melee
- Сильный удар (`spirit_power_strike`) — spirit, attack/heavy_melee
- Точный выпад (`spirit_precise_thrust`) — spirit, attack/precision_melee
- Парирование (`spirit_parry`) — spirit, defense/reaction
- Боевой рывок (`spirit_quick_dash`) — spirit, attack/mobility
- Широкий взмах (`spirit_sweeping_cut`) — spirit, attack/cleave
- Подсечка (`spirit_low_sweep`) — spirit, control/control_melee
- Дробящий пролом (`spirit_crushing_break`) — spirit, attack/armor_break
- Посоховый разворот (`spirit_staff_counter`) — spirit, attack/counter_control
- Прорыв обороны (`spirit_breakthrough`) — spirit, attack/armor_pierce
- Вихрь стали (`spirit_whirlwind`) — spirit, attack/melee_aoe
- Метка охотника (`spirit_hunter_mark`) — spirit, support/mark
- Смертельный выпад (`spirit_execution_thrust`) — spirit, attack/execute
- Поток ответных ударов (`spirit_counter_flow`) — spirit, attack/counter_combo
- Огненное кольцо (`mana_fire_ring`) — mana, attack/fire_aoe
- Цепная молния (`mana_chain_lightning`) — mana, attack/lightning_chain
- Теневая игла (`mana_shadow_needle`) — mana, attack/shadow
- Земляная клетка (`mana_earth_prison`) — mana, control/root_aoe
- Восстанавливающая волна (`mana_mending_wave`) — mana, support/heal_aoe
- Печать подавления (`mana_seal_suppression`) — mana, control/strong_debuff
- Зеркальный барьер (`mana_mirror_barrier`) — mana, defense/reflect_barrier
- Всплеск маны (`mana_mana_burst`) — mana, attack/burst
- Стихийный шквал (`mana_elemental_storm`) — mana, attack/elemental_aoe
- Печать жизни (`mana_life_seal`) — mana, support/strong_heal
- Купол оберега (`mana_warding_dome`) — mana, defense/party_barrier
- Формула разлома (`mana_rift_formula`) — mana, attack/late_magic
- Силовой толчок (`char_str_50_force_push`) — spirit, control/characteristic_special
- Грубое давление (`char_str_250_brutal_pressure`) — spirit, attack/characteristic_special
- Давление великана (`char_str_1000_giant_pressure`) — spirit, control/characteristic_special
- Ответный выпад (`char_agi_100_reply_lunge`) — spirit, attack/characteristic_special
- Исчезающий рывок (`char_agi_2500_vanishing_dash`) — spirit, attack/characteristic_special
- Магическая фиксация (`char_per_100_arcane_lock`) — mana, control/characteristic_special
- Усиленная формула (`char_int_50_amplified_formula`) — mana, support/characteristic_special
- Магический разбор (`char_int_100_arcane_analysis`) — mana, control/characteristic_special
- Переплетение чар (`char_int_250_spell_weaving`) — mana, support/characteristic_special
- Разгон маны (`char_int_500_mana_acceleration`) — mana, support/characteristic_special
- Архитектура заклинания (`char_int_1000_spell_architecture`) — mana, support/characteristic_special
- Предельная формула (`char_int_2500_rift_formula_special`) — mana, attack/characteristic_special
- Очищающий жест (`char_wis_100_purifying_gesture`) — mana, support/characteristic_special
- Мудрый заслон (`char_wis_250_wise_ward`) — mana, defense/characteristic_special
- Глубокий поток (`char_wis_500_deep_flow`) — mana, support/characteristic_special
- Нить судьбы (`char_wis_1000_thread_of_fate`) — mana, support/characteristic_special
- Покой мира (`char_wis_2500_world_peace`) — mana, support/characteristic_special

## Топор (`axe`)
- Обычный удар (`neutral_basic_strike`) — neutral, attack/basic_melee
- Сильный удар (`spirit_power_strike`) — spirit, attack/heavy_melee
- Парирование (`spirit_parry`) — spirit, defense/reaction
- Боевой рывок (`spirit_quick_dash`) — spirit, attack/mobility
- Широкий взмах (`spirit_sweeping_cut`) — spirit, attack/cleave
- Подсечка (`spirit_low_sweep`) — spirit, control/control_melee
- Дробящий пролом (`spirit_crushing_break`) — spirit, attack/armor_break
- Кровавый разрез (`spirit_bleeding_cut`) — spirit, attack/bleed
- Прорыв обороны (`spirit_breakthrough`) — spirit, attack/armor_pierce
- Вихрь стали (`spirit_whirlwind`) — spirit, attack/melee_aoe
- Удар колосса (`spirit_colossus_blow`) — spirit, attack/ultimate_heavy
- Силовой толчок (`char_str_50_force_push`) — spirit, control/characteristic_special
- Тяжёлый раскол (`char_str_100_heavy_crack`) — spirit, attack/characteristic_special
- Грубое давление (`char_str_250_brutal_pressure`) — spirit, attack/characteristic_special
- Титанический замах (`char_str_500_titan_swing`) — spirit, attack/characteristic_special
- Давление великана (`char_str_1000_giant_pressure`) — spirit, control/characteristic_special
- Разломная сила (`char_str_2500_rift_strength`) — spirit, attack/characteristic_special
- Прицельный разрез (`char_per_100_aimed_cut`) — spirit, attack/characteristic_special

## Молот (`hammer`)
- Обычный удар (`neutral_basic_strike`) — neutral, attack/basic_melee
- Сильный удар (`spirit_power_strike`) — spirit, attack/heavy_melee
- Боевой рывок (`spirit_quick_dash`) — spirit, attack/mobility
- Дробящий пролом (`spirit_crushing_break`) — spirit, attack/armor_break
- Прорыв обороны (`spirit_breakthrough`) — spirit, attack/armor_pierce
- Удар колосса (`spirit_colossus_blow`) — spirit, attack/ultimate_heavy
- Силовой толчок (`char_str_50_force_push`) — spirit, control/characteristic_special
- Тяжёлый раскол (`char_str_100_heavy_crack`) — spirit, attack/characteristic_special
- Грубое давление (`char_str_250_brutal_pressure`) — spirit, attack/characteristic_special
- Титанический замах (`char_str_500_titan_swing`) — spirit, attack/characteristic_special
- Давление великана (`char_str_1000_giant_pressure`) — spirit, control/characteristic_special
- Разломная сила (`char_str_2500_rift_strength`) — spirit, attack/characteristic_special

## Лук (`bow`)
- Прицельный выстрел (`spirit_aimed_shot`) — spirit, attack/ranged
- Ливень стрел (`spirit_arrow_rain`) — spirit, attack/ranged_aoe
- Метка охотника (`spirit_hunter_mark`) — spirit, support/mark

## Щит (`shield`)
- Удар щитом (`spirit_shield_bash`) — spirit, attack/control
- Бастион (`spirit_bastion_guard`) — spirit, defense/party_guard
- Силовой толчок (`char_str_50_force_push`) — spirit, control/characteristic_special
- Давление великана (`char_str_1000_giant_pressure`) — spirit, control/characteristic_special
- Непробиваемый корпус (`char_end_250_hard_body`) — spirit, defense/characteristic_special
- Неподвижная крепость (`char_end_2500_still_fortress`) — spirit, defense/characteristic_special

## Арбалет (`crossbow`)
- Прицельный выстрел (`spirit_aimed_shot`) — spirit, attack/ranged
- Пробивающий болт (`spirit_piercing_bolt`) — spirit, attack/ranged_pierce
- Метка охотника (`spirit_hunter_mark`) — spirit, support/mark

## Универсальные действия (`any`)
- Магический сгусток (`neutral_magic_clot`) — neutral, attack/basic_magic
- Простая защита (`neutral_guard`) — neutral, defense/guard
- Отскок (`neutral_dodge`) — neutral, defense/dodge
- Подсумок (`neutral_use_pouch`) — neutral, support/item_use
- Сбежать (`neutral_escape`) — neutral, support/escape
- Защитная стойка (`spirit_guard_stance`) — spirit, defense/stance
- Боевой крик (`spirit_battle_cry`) — spirit, support/buff
- Дыхание боя (`spirit_enduring_breath`) — spirit, support/resource_recovery
- Стойка несломленного (`spirit_unbroken_stance`) — spirit, defense/strong_stance
- Второе дыхание (`spirit_second_wind`) — spirit, support/self_heal_resource
- Искра маны (`mana_spark`) — mana, attack/basic_mana
- Огненная стрела (`mana_fire_arrow`) — mana, attack/fire
- Ледяной осколок (`mana_ice_shard`) — mana, attack/frost
- Малый барьер (`mana_small_barrier`) — mana, defense/barrier
- Целебная нить (`mana_healing_thread`) — mana, support/heal
- Ослабляющая метка (`mana_weakening_mark`) — mana, control/debuff
- Укол молнии (`mana_lightning_prick`) — mana, attack/lightning
- Каменная кожа (`mana_stone_skin`) — mana, defense/physical_magic_defense
- Очищение (`mana_cleanse`) — mana, support/cleanse
- Водяная дымка (`mana_water_mist`) — mana, defense/evasion_buff
- Ледяная цепь (`mana_ice_chain`) — mana, control/root
- Магический щит (`mana_arcane_shield`) — mana, defense/barrier
- Растворение яда (`mana_poison_dissolve`) — mana, support/cleanse_heal
- Сосредоточение разума (`mana_mind_focus`) — mana, support/self_buff
- Короткий заслон (`char_end_50_short_wall`) — spirit, defense/characteristic_special
- Живая стойка (`char_end_100_living_stance`) — spirit, defense/characteristic_special
- Сердце бастиона (`char_end_500_bastion_heart`) — spirit, support/characteristic_special
- Несломленная оболочка (`char_end_1000_unbroken_shell`) — spirit, defense/characteristic_special
- Скользящий шаг (`char_agi_50_sliding_step`) — spirit, defense/characteristic_special
- Призрачный уклон (`char_agi_500_ghost_dodge`) — spirit, defense/characteristic_special
- Метка слабости (`char_per_50_weak_mark`) — neutral_special, support/characteristic_special
- Охотничий захват (`char_per_250_hunter_grip`) — neutral_special, control/characteristic_special
- Абсолютная наводка (`char_per_500_absolute_guidance`) — neutral_special, support/characteristic_special
- Разбор движения (`char_per_1000_motion_reading`) — neutral_special, defense/characteristic_special
- Глаз разлома (`char_per_2500_rift_eye`) — neutral_special, support/characteristic_special
- Тихое восстановление (`char_wis_50_quiet_restore`) — mana, support/characteristic_special

## Изменённые навыки
- Обычный удар (`neutral_basic_strike`): `['any_melee', 'unarmed']` → `['sword', 'dagger', 'staff', 'axe', 'hammer']`
- Магический сгусток (`neutral_magic_clot`): `['any', 'staff', 'focus']` → `['any']`
- Простая защита (`neutral_guard`): `['any', 'shield']` → `['any']`
- Сильный удар (`spirit_power_strike`): `['any_melee']` → `['sword', 'dagger', 'staff', 'axe', 'hammer']`
- Точный выпад (`spirit_precise_thrust`): `['sword', 'spear', 'dagger']` → `['sword', 'staff', 'dagger']`
- Защитная стойка (`spirit_guard_stance`): `['any', 'shield']` → `['any']`
- Парирование (`spirit_parry`): `['sword', 'dagger', 'spear', 'axe']` → `['sword', 'dagger', 'staff', 'axe']`
- Боевой рывок (`spirit_quick_dash`): `['any_melee']` → `['sword', 'dagger', 'staff', 'axe', 'hammer']`
- Широкий взмах (`spirit_sweeping_cut`): `['sword', 'axe', 'staff', 'spear']` → `['sword', 'axe', 'staff']`
- Подсечка (`spirit_low_sweep`): `['staff', 'spear', 'axe', 'unarmed']` → `['staff', 'axe']`
- Дробящий пролом (`spirit_crushing_break`): `['hammer', 'axe', 'spear']` → `['hammer', 'axe', 'staff']`
- Прорыв обороны (`spirit_breakthrough`): `['sword', 'hammer', 'axe', 'spear']` → `['sword', 'hammer', 'axe', 'staff']`
- Стойка несломленного (`spirit_unbroken_stance`): `['any', 'shield']` → `['any']`
- Метка охотника (`spirit_hunter_mark`): `['bow', 'crossbow', 'spear', 'dagger']` → `['bow', 'crossbow', 'staff', 'dagger']`
- Смертельный выпад (`spirit_execution_thrust`): `['sword', 'spear', 'dagger']` → `['sword', 'staff', 'dagger']`
- Удар колосса (`spirit_colossus_blow`): `['hammer', 'axe', 'two_handed_sword']` → `['hammer', 'axe', 'sword']`
- Бастион (`spirit_bastion_guard`): `['shield', 'heavy_armor']` → `['shield']`, снаряжение: `['heavy_armor']`
- Искра маны (`mana_spark`): `['staff', 'focus', 'any']` → `['any']`
- Огненная стрела (`mana_fire_arrow`): `['staff', 'focus', 'any']` → `['any']`
- Ледяной осколок (`mana_ice_shard`): `['staff', 'focus', 'any']` → `['any']`
- Малый барьер (`mana_small_barrier`): `['staff', 'focus', 'any']` → `['any']`
- Целебная нить (`mana_healing_thread`): `['staff', 'focus', 'any']` → `['any']`
- Ослабляющая метка (`mana_weakening_mark`): `['staff', 'focus', 'any']` → `['any']`
- Укол молнии (`mana_lightning_prick`): `['staff', 'focus', 'any']` → `['any']`
- Каменная кожа (`mana_stone_skin`): `['staff', 'focus', 'any']` → `['any']`
- Очищение (`mana_cleanse`): `['staff', 'focus', 'any']` → `['any']`
- Водяная дымка (`mana_water_mist`): `['staff', 'focus', 'any']` → `['any']`
- Огненное кольцо (`mana_fire_ring`): `['staff', 'focus']` → `['staff']`
- Ледяная цепь (`mana_ice_chain`): `['staff', 'focus', 'any']` → `['any']`
- Магический щит (`mana_arcane_shield`): `['staff', 'focus', 'any']` → `['any']`
- Цепная молния (`mana_chain_lightning`): `['staff', 'focus']` → `['staff']`
- Растворение яда (`mana_poison_dissolve`): `['staff', 'focus', 'any']` → `['any']`
- Сосредоточение разума (`mana_mind_focus`): `['staff', 'focus', 'any']` → `['any']`
- Теневая игла (`mana_shadow_needle`): `['staff', 'focus', 'dagger']` → `['staff', 'dagger']`
- Земляная клетка (`mana_earth_prison`): `['staff', 'focus']` → `['staff']`
- Восстанавливающая волна (`mana_mending_wave`): `['staff', 'focus']` → `['staff']`
- Печать подавления (`mana_seal_suppression`): `['staff', 'focus']` → `['staff']`
- Зеркальный барьер (`mana_mirror_barrier`): `['staff', 'focus']` → `['staff']`
- Всплеск маны (`mana_mana_burst`): `['staff', 'focus']` → `['staff']`
- Стихийный шквал (`mana_elemental_storm`): `['staff', 'focus']` → `['staff']`
- Печать жизни (`mana_life_seal`): `['staff', 'focus']` → `['staff']`
- Купол оберега (`mana_warding_dome`): `['staff', 'focus']` → `['staff']`
- Формула разлома (`mana_rift_formula`): `['staff', 'focus']` → `['staff']`
- Силовой толчок (`char_str_50_force_push`): `['any_melee', 'shield', 'unarmed']` → `['sword', 'dagger', 'staff', 'axe', 'hammer', 'shield']`
- Тяжёлый раскол (`char_str_100_heavy_crack`): `['hammer', 'axe', 'two_handed_sword']` → `['hammer', 'axe', 'sword']`
- Грубое давление (`char_str_250_brutal_pressure`): `['any_melee']` → `['sword', 'dagger', 'staff', 'axe', 'hammer']`
- Титанический замах (`char_str_500_titan_swing`): `['hammer', 'axe', 'two_handed_sword']` → `['hammer', 'axe', 'sword']`
- Давление великана (`char_str_1000_giant_pressure`): `['any_melee', 'shield']` → `['sword', 'dagger', 'staff', 'axe', 'hammer', 'shield']`
- Разломная сила (`char_str_2500_rift_strength`): `['two_handed_sword', 'hammer', 'axe']` → `['sword', 'hammer', 'axe']`
- Короткий заслон (`char_end_50_short_wall`): `['any', 'shield']` → `['any']`
- Непробиваемый корпус (`char_end_250_hard_body`): `['medium_armor', 'heavy_armor', 'shield']` → `['shield']`, снаряжение: `['medium_armor', 'heavy_armor']`
- Неподвижная крепость (`char_end_2500_still_fortress`): `['shield', 'heavy_armor']` → `['shield']`, снаряжение: `['heavy_armor']`
- Ответный выпад (`char_agi_100_reply_lunge`): `['sword', 'dagger', 'spear']` → `['sword', 'dagger', 'staff']`
- Серия без дыхания (`char_agi_1000_breathless_series`): `['dagger', 'sword', 'unarmed']` → `['dagger', 'sword']`
- Исчезающий рывок (`char_agi_2500_vanishing_dash`): `['dagger', 'sword', 'spear']` → `['dagger', 'sword', 'staff']`
- Магическая фиксация (`char_per_100_arcane_lock`): `['staff', 'focus']` → `['staff']`
- Усиленная формула (`char_int_50_amplified_formula`): `['staff', 'focus']` → `['staff']`
- Магический разбор (`char_int_100_arcane_analysis`): `['staff', 'focus']` → `['staff']`
- Переплетение чар (`char_int_250_spell_weaving`): `['staff', 'focus']` → `['staff']`
- Разгон маны (`char_int_500_mana_acceleration`): `['staff', 'focus']` → `['staff']`
- Архитектура заклинания (`char_int_1000_spell_architecture`): `['staff', 'focus']` → `['staff']`
- Предельная формула (`char_int_2500_rift_formula_special`): `['staff', 'focus']` → `['staff']`
- Тихое восстановление (`char_wis_50_quiet_restore`): `['any', 'staff', 'focus']` → `['any']`
- Очищающий жест (`char_wis_100_purifying_gesture`): `['staff', 'focus']` → `['staff']`
- Мудрый заслон (`char_wis_250_wise_ward`): `['staff', 'focus']` → `['staff']`
- Глубокий поток (`char_wis_500_deep_flow`): `['staff', 'focus']` → `['staff']`
- Нить судьбы (`char_wis_1000_thread_of_fate`): `['staff', 'focus']` → `['staff']`
- Покой мира (`char_wis_2500_world_peace`): `['staff', 'focus']` → `['staff']`