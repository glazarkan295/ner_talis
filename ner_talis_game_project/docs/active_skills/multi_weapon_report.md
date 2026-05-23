# Отчёт: навыки с несколькими допустимыми видами оружия
Всего навыков: **94**.
- Навыков с несколькими видами оружия: **28**.
- Навыков с одним конкретным оружием: **30**.
- Универсальных навыков `any`: **36**.

## Правило

`weapon_requirements` всегда список. Проверка: `any_of`. Навык доступен, если экипирован хотя бы один тип оружия из списка.

## Навыки с несколькими видами оружия
- **Обычный удар** (`neutral_basic_strike`) — `sword` (меч), `dagger` (кинжал), `staff` (посох), `axe` (топор), `hammer` (молот)
- **Сильный удар** (`spirit_power_strike`) — `sword` (меч), `dagger` (кинжал), `staff` (посох), `axe` (топор), `hammer` (молот)
- **Точный выпад** (`spirit_precise_thrust`) — `sword` (меч), `staff` (посох), `dagger` (кинжал)
- **Парирование** (`spirit_parry`) — `sword` (меч), `dagger` (кинжал), `staff` (посох), `axe` (топор)
- **Боевой рывок** (`spirit_quick_dash`) — `sword` (меч), `dagger` (кинжал), `staff` (посох), `axe` (топор), `hammer` (молот)
- **Прицельный выстрел** (`spirit_aimed_shot`) — `bow` (лук), `crossbow` (арбалет)
- **Широкий взмах** (`spirit_sweeping_cut`) — `sword` (меч), `axe` (топор), `staff` (посох)
- **Подсечка** (`spirit_low_sweep`) — `staff` (посох), `axe` (топор)
- **Дробящий пролом** (`spirit_crushing_break`) — `hammer` (молот), `axe` (топор), `staff` (посох)
- **Кровавый разрез** (`spirit_bleeding_cut`) — `sword` (меч), `dagger` (кинжал), `axe` (топор)
- **Прорыв обороны** (`spirit_breakthrough`) — `sword` (меч), `hammer` (молот), `axe` (топор), `staff` (посох)
- **Вихрь стали** (`spirit_whirlwind`) — `sword` (меч), `axe` (топор), `staff` (посох)
- **Метка охотника** (`spirit_hunter_mark`) — `bow` (лук), `crossbow` (арбалет), `staff` (посох), `dagger` (кинжал)
- **Смертельный выпад** (`spirit_execution_thrust`) — `sword` (меч), `staff` (посох), `dagger` (кинжал)
- **Поток ответных ударов** (`spirit_counter_flow`) — `sword` (меч), `dagger` (кинжал), `staff` (посох)
- **Удар колосса** (`spirit_colossus_blow`) — `hammer` (молот), `axe` (топор), `sword` (меч)
- **Теневая игла** (`mana_shadow_needle`) — `staff` (посох), `dagger` (кинжал)
- **Силовой толчок** (`char_str_50_force_push`) — `sword` (меч), `dagger` (кинжал), `staff` (посох), `axe` (топор), `hammer` (молот), `shield` (щит)
- **Тяжёлый раскол** (`char_str_100_heavy_crack`) — `hammer` (молот), `axe` (топор), `sword` (меч)
- **Грубое давление** (`char_str_250_brutal_pressure`) — `sword` (меч), `dagger` (кинжал), `staff` (посох), `axe` (топор), `hammer` (молот)
- **Титанический замах** (`char_str_500_titan_swing`) — `hammer` (молот), `axe` (топор), `sword` (меч)
- **Давление великана** (`char_str_1000_giant_pressure`) — `sword` (меч), `dagger` (кинжал), `staff` (посох), `axe` (топор), `hammer` (молот), `shield` (щит)
- **Разломная сила** (`char_str_2500_rift_strength`) — `sword` (меч), `hammer` (молот), `axe` (топор)
- **Ответный выпад** (`char_agi_100_reply_lunge`) — `sword` (меч), `dagger` (кинжал), `staff` (посох)
- **Танец клинка** (`char_agi_250_blade_dance`) — `sword` (меч), `dagger` (кинжал)
- **Серия без дыхания** (`char_agi_1000_breathless_series`) — `dagger` (кинжал), `sword` (меч)
- **Исчезающий рывок** (`char_agi_2500_vanishing_dash`) — `dagger` (кинжал), `sword` (меч), `staff` (посох)
- **Прицельный разрез** (`char_per_100_aimed_cut`) — `sword` (меч), `dagger` (кинжал), `axe` (топор)

## Счётчик по оружию
- `sword` (меч): 23
- `dagger` (кинжал): 18
- `staff` (посох): 43
- `axe` (топор): 18
- `hammer` (молот): 12
- `bow` (лук): 3
- `shield` (щит): 6
- `crossbow` (арбалет): 3
- `any` (универсально): 36
