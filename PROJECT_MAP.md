# PROJECT_MAP — карта проекта Ner-Talis (для быстрой навигации)

> Назначение: читать ЭТОТ файл первым, находить нужный модуль/данные и работать
> точечно, не сканируя весь репозиторий. **При добавлении нового модуля/фичи —
> обновлять этот файл** (раздел services / data / «Где что лежит»).
> Подробный человекочитаемый обзор: `ner_talis_game_project/docs/PROJECT_STRUCTURE.md`.

Игра: Telegram + VK боты + сайт-профиль/админка (FastAPI) + React-SPA.
Контент data-driven (JSON в `data/`). Бэкенд — Python (`ner_talis_game_project/`).

## Точки входа
- `ner_talis_game_project/main.py` — запуск ботов (run_bots: Telegram/VK), восстановление таймеров (recover_runtime_timers), запуск планировщика эффектов (_start_player_effect_scheduler_once).
- `ner_talis_game_project/web_app.py` — FastAPI-приложение сайта (профиль + админка).
- `ner_talis_game_project/site_api.py` — API профиля игрока (frontend_profile, эндпоинты инвентаря/навыков/характеристик/использования предметов/edit-field).
- `ner_talis_game_project/admin_panel_api.py` — API админ-панели (роуты /api/admin/...).
- `ner_talis_game_project/project_paths.py` — resolve_project_path / project_path (доступ к data/ и ресурсам).

## services/ (ядро логики)
- `city_service.py` — городская навигация Селдара; **process_world_action** (единый роутер действий мира: город/рынок/крафт/внешние локации/бой/штрафы/рыбалка); central_square_buttons, кварталы; хук advance_player_time; триггер city_quarter_walk.
- `external_location_service.py` — внешние локации (Холмистые луга, Обыкновенный лес, Малое плато, крепость): поиск, события (resolve_active_event), таймеры (complete_active_timer), лагерь/готовка, крепость (handle_fortress_action), claim_active_event.
- `pve_battle_service.py` — PVE-бой: handle_battle_action, ходы, урон/крит/попадание, враги (build_enemy), лут/опыт; make_player_battle_state.
- `pve_battle_models.py` — dataclass'ы боя (PlayerBattleState/EnemyBattleState с crit_chance/crit_damage), формулы calculate_hit_chance/calculate_final_damage/apply_defense.
- `derived_stats_service.py` — производные статы из атрибутов+экипировки+эффектов (calculate_player_derived_stats), модификаторы (equipment/external/passive), crit/accuracy/dodge/hp.
- `active_skill_service.py` — активные/пассивные навыки: реестр (load_active_skill_registry → data/active_skills_registry.json, v11), урон навыка, стоимость (resource_cost_with_modifiers), кулдауны, passive_stat_modifiers, weapon_requirements.
- `crafting_service.py` — мастерские (плавильня/кузница/кожевенная/ювелирная/алхимия), рецепты (data/crafting_recipes.json), WORKSHOPS, секции; ювелирка (Бижутерия→кольца(железные/серебряные)/ожерелья/рецепты), вставка камней; алхимия (неудача → suspicious_potion).
- `market_service.py` — рынки (NPC/портовый): покупка/продажа, цены, ротация портового рынка + **атомарный claim стока** (claim_port_stock); format_price.
- `fishing_service.py` — рыбалка (таймер 60с, энергия −1), трата использования удочки (gathering_tools).
- `gathering_tools.py` — прочность инструментов (удочка/топор/кирка): 10 использований/инструмент, стак 10, spend_tool_use/tool_uses_left.
- `fine_service.py` — облавы/городские штрафы, перемещение в крепость, оплата; fine_entries_for_profile (попап штрафов).
- `small_plateau_service.py` — Малое плато: поиск (resolve_small_plateau_search, data/small_plateau_*.json), Древнее Проклятье (roll_ancient_curse_trigger, cleanse), ожог амулета, достижения (Ищущий/«Какое проклятье?»), filter_seeker_only.
- `player_time_service.py` — догон время-эффектов (часовой ожог амулета, суточные дни проклятья); advance_player_time (на действие), advance_all_players_time + start_persistent_player_effect_worker (фоновый планировщик).
- `battle_stimulant_service.py` — боевой стимулятор: фазы (активная/откат), зависимость, stat_percent_modifiers, статус-карточка.
- `inventory_service.py` — инвентарь: add_inventory_item, переполнение/слоты, карманы, квалити/уровень/цена генерируемых предметов.
- `item_registry.py` — реестр предметов: load_all_item_definitions, get_item_definition_by_id/by_name, build_inventory_item (агрегирует data/items_*.json).
- `currency.py` — медь как база; format_money (краткий баланс) / format_price (торговля: «13 маг. зол. 6 зол. 400 мед. монет»). Курс: сер.=1e3, зол.=1e6, маг.зол.=1e9, древн.=5e11.
- `progression_service.py` — опыт/уровни (grant_exact_experience).
- `race_bonus_service.py` — расовые бонусы (hp_multiplier, сопротивления, регенерация).
- `registration_service.py` — создание игрока (create_player), validate_name/normalize_name, load_races, гендеры; согласие перед регистрацией (consent_message, CONSENT_BUTTON, _doc_link → env LINK_PRIVACY_POLICY / LINK_TERMS_OF_SERVICE).
- `promo_service.py` — промокоды: _normalize_code (срез слэша+upper), add/delete (удаляет ВСЕ совпавшие ключи), redeem (атомарный claim_promo_use).
- `admin_panel_service.py` — логика админ-панели: каталог (HIDDEN_CATALOG_ITEM_IDS, SYNTHETIC_REWARD_IDS — монеты/очки), доставка наград (cap по меди), промо, сессии (consume_or_read_admin_session — атомарный claim токена), просмотр игроков.
- `admin_command_service.py` / `admin_access.py` / `admin_audit.py` — админ-команды в боте, доступ, аудит.
- `admin_player_service.py` — поиск/сводка/удаление игроков, бэкап.
- `web_profile.py` — генерация ссылок на сайт-профиль (create_profile_site_link), base URL.
- `chat_log_service.py` — лог чата игрока + pending_bot_messages (pop_pending_bot_messages — доставка фоновых сообщений ботом).
- `runtime_timer_scheduler.py` — доставка таймеров (поиск/отдых/крафт) после рестарта; start_persistent_timer_worker, claim.

## storage/
- `storage_factory.py` — create_storage() по ENV (STORAGE_BACKEND: postgres/sqlite/json).
- `base.py` — интерфейс хранилища.
- `json_storage.py` / `sqlite_storage.py` / `postgres_storage.py` — бэкенды (игроки, промо, админ-сессии).
- `event_claims.py` / `timer_claims.py` — атомарные claim'ы событий/таймеров (анти-дубль наград).
- `starter_pack_runtime.py`, `hard_delete_runtime.py` — стартовый набор, жёсткое удаление.

## handlers/ (боты)
- `city.py` — Telegram-обработчик мира (send_city_response → process_world_action; flush pending_bot_messages; **сохраняет игрока после действия** — учитывать при claim-копиях!).
- `registration.py` / `vk_registration.py` — регистрация (Telegram/VK); _gender_choice_from_text (Муж./Жен.); согласие первым шагом (TG: CONSENT_GATE → accept_consent; VK: STATE_CONSENT, первый контакт/кнопка «Начать» → согласие, фикс VK first-launch).
- `telegram_admin.py` / `vk_admin.py` / `vk_admin_runtime.py` — админ-команды в чатах.
- `site_profile.py` — выдача ссылок профиля.

## web/src (React SPA, Vite)
- `App.jsx` — роутинг: профиль игрока / админ-просмотр профиля / админ-панель; прокидывает onEditProfileField и др.
- `api/profileApi.js` — вызовы API профиля (useItem/sellItem/editProfileField/...).
- `api/adminApi.js` — вызовы API админки (loadCatalog/deletePromo/...).
- `components/player-profile/PlayerProfile.jsx` — профиль: вкладки Персонаж/Инвентарь/Навыки/Информация; модалки (ItemModal, FinesModal, ProfileEditModal, nt-center-modal); CollapsiblePanel; сводка (Имя/Раса/Пол + карандаши).
- `components/player-profile/PlayerProfile.css` — стили профиля (модалки, попапы, мобильное центрирование ≤560px).
- `components/admin-panel/AdminPanel.jsx` — каталог/доставка/промокоды/игроки.
- Сборка: `cd web && npm run build` → `web/dist/` (gitignored).

## data/ (контент, JSON) — по доменам
- Навыки: active_skills_registry.json (v11), active_skills_counts.json.
- Бой/враги/лут: pve_battle_schema.json, items_block4_combat_runtime.json, items_starting_mob_loot.json, ammunition_system.json, quiver_system.json, items_ammunition_quivers.json.
- Крафт: crafting_recipes.json, items_crafting.json, items_collected_crafting.json, items_catalog_expansion.json, items_iron_armor.json, items_simple_leather_armor.json.
- Локации: hilly_meadows.json, ordinary_forest.json, small_plateau_location.json/_mechanics/_search_events/_texts, fortress_in_gorge.json, location_fishing_sources.json, items_block7_locations_fishing.json (удочка), items_<location>.json.
- Город/рынок: seldar_city.json, seldar_market.json (Рынок — цены покупки), items_seldar_market.json (определения; топор/кирка/удочка).
- Игрок/прочее: races.json, item_sell_prices.json, branch_choice_messages.json, alchemy_system_runtime.json.
- Визуальные ассеты: item_visual_assets_*.json (привязка иконок).
- Рантайм-состояние (часть gitignored): players.json/sqlite3, promo_codes.json, port_market_state.json.
- Иконки: `web/public/assets/items/...`, модели/фоны: `web/public/assets/profile/...`.

## Тесты и запуск
- Тесты: `./.venv/Scripts/python.exe -m pytest -p no:cacheprovider -q ner_talis_game_project/tests` — **запускать из КОРНЯ репо** (часть тестов проверяет `web/public/...` относительно корня).
- venv: `.venv/Scripts/python.exe`. Сборка SPA: `cd web && npm run build`.
- Стиль E501/F401 — историческая норма проекта, игнорируется.

## Где что лежит (быстрый индекс фич)
- Цены/валюта/номиналы → `services/currency.py`.
- Крит/урон/попадание/враги в PVE → `pve_battle_service.py` + `pve_battle_models.py`.
- Эффекты на статы (стимулятор/кристаллы/зелья/проклятье) → `derived_stats_service.py` (+ источники в battle_stimulant_service / small_plateau_service / site_api suspicious_potion).
- Древнее Проклятье / амулет / Малое плато / Ищущий → `small_plateau_service.py` + data/small_plateau_*.json.
- Время-эффекты и фоновый планировщик → `player_time_service.py` (+ запуск в main.run_bots).
- Рыбалка и прочность инструментов → `fishing_service.py` + `gathering_tools.py` (удочка/топор/кирка).
- Рынок/портовый сток/цены → `market_service.py`; данные — seldar_market.json / items_seldar_market.json.
- Ювелирка/крафт-секции → `crafting_service.py` + crafting_recipes.json.
- Штрафы/облавы → `fine_service.py`.
- Промокоды → `promo_service.py` + admin_panel_service (создание из админки).
- Админ-панель (каталог/доставка/монеты/сессии) → `admin_panel_service.py` + admin_panel_api.py + web AdminPanel.jsx.
- Профиль-сайт (данные/эндпоинты/редактирование сводки) → `site_api.py` + web PlayerProfile.jsx.
- Регистрация/гендер/раса/валидация имени → `registration_service.py` + handlers/registration.py + vk_registration.py.
- Хранилище/claim'ы/атомарность → `storage/` (event_claims, timer_claims, *_storage.py).
- Доставка фоновых сообщений игроку → pending_bot_messages (chat_log_service.pop_pending_bot_messages, flush в handlers/city.py + vk).

## Важные инварианты (легко сломать)
- Боты ПОСЛЕ действия пересохраняют ИСХОДНЫЙ объект игрока (handlers/city.py:~113, vk). Поэтому claim-перезагрузки (события/рыбалка) надо синхронизировать В исходный объект (`player.clear(); player.update(claimed)`), иначе изменения затрутся.
- Тесты запускать из корня репозитория (иначе ложные падения проверок иконок `web/public/...`).
- Деньги хранятся в меди (64-бит) — награды монетами ограничены по медному эквиваленту (admin_panel_service.MAX_REWARD_MONEY_COPPER).
