// Единый справочник русских названий для админ-панели (ТЗ «русские названия»).
// Технические коды остаются в данных/API, а в интерфейсе показываются русские
// подписи. Один код = одно название во всех разделах. Неизвестный код
// возвращается как есть (fallback), чтобы ничего не «пропадало».

// Жизненный цикл контента конструкторов.
export const STATUS = {
  draft: "Черновик", review: "На проверке", ready: "Готово к публикации",
  published: "Опубликовано", disabled: "Отключено", error: "Ошибка проверки",
  archived: "Архив", archive: "Архив", scheduled: "Запланировано",
  hidden: "Скрыто", deleted_soft: "Удалён (мягко)",
};

// Статусы штрафов.
export const FINE_STATUS = {
  voluntary: "Добровольная оплата", overdue: "Просрочка",
  forced_collection: "Принудительное взыскание", paid: "Оплачен",
  removed_by_admin: "Снят администратором", expired: "Просрочен",
  cancelled: "Отменён", active: "Активен", waiting_payment: "Ожидает оплаты",
  data_error: "Ошибка данных",
};

// Роли доступа админки.
export const ROLE = {
  owner: "Владелец", admin: "Администратор", support: "Поддержка",
  moderator: "Модератор", content: "Контент", economy: "Экономика",
  read_only: "Только чтение", system: "Система", player: "Игрок", npc: "NPC",
};

// Качество/редкость предметов (в данных часто уже по-русски — тогда passthrough).
export const ITEM_QUALITY = {
  common: "Обычный", uncommon: "Необычный", rare: "Редкий", epic: "Эпический",
  legendary: "Легендарный", mythic: "Мифический", divine: "Божественный",
  unique: "Уникальный",
};

// --- Конструктор предметов -------------------------------------------------
export const ITEM_TYPE = {
  normal: "Обычный", equippable: "Экипируемый", consumable: "Расходник", resource: "Ресурс",
  ingredient: "Ингредиент", recipe: "Рецепт", quest: "Квестовый", unique: "Уникальный",
  artifact: "Артефакт", one_time_artifact: "Одноразовый артефакт", special_slot: "Особый слот",
  craft: "Ремесленный", sale: "Торговый", event: "Событийный", guild: "Гильдейский",
  raid: "Рейдовый", achievement: "За достижение",
};
export const EQUIP_SLOT = {
  head: "Голова", chest: "Нагрудник", legs: "Штаны", gloves: "Перчатки", boots: "Ботинки",
  belt: "Пояс", main_hand: "Основная рука", off_hand: "Вторая рука", two_hands: "Две руки",
  staff: "Посох", spellbook: "Магическая книга", shield: "Щит", ring: "Кольцо",
  necklace: "Ожерелье", special: "Особый слот", bag: "Подсумок",
};
export const ITEM_PROPERTY = {
  strength: "Сила", stamina: "Выносливость", agility: "Ловкость", perception: "Восприятие",
  intelligence: "Интеллект", wisdom: "Мудрость", hp: "HP", mana: "Мана", spirit: "Дух",
  energy: "Энергия", phys_defense: "Физ. защита", mag_defense: "Маг. защита", accuracy: "Точность",
  evasion: "Уклонение", crit_chance: "Шанс крита", crit_damage: "Урон крита", armor: "Броня",
  hp_regen: "Реген. HP", mana_regen: "Реген. маны", exp_bonus: "Бонус опыта", coin_bonus: "Бонус монет",
  loot_bonus: "Бонус добычи", fishing_bonus: "Бонус рыбалки", alchemy_bonus: "Бонус алхимии",
};
export const ITEM_EFFECT_TYPE = {
  one_time: "Одноразовый", passive_on_equip: "Пассивный при экипировке",
  temp_on_use: "Временный при использовании", stacking: "Накопительный", combat: "Боевой",
  loot: "Добыча", fishing: "Рыбалка", alchemy: "Алхимия", craft: "Крафт",
  zone_protection: "Защита от зоны", revive: "Воскрешение", reflect: "Отражение", thorns: "Шипы",
  vampirism: "Вампиризм", burn: "Поджог", poison: "Яд", stun: "Оглушение", bleed: "Кровотечение",
  cleanse: "Очищение", regen: "Регенерация",
};

// --- Конструктор эффектов --------------------------------------------------
export const EFFECT_TYPE = {
  stat_modifier: "Модификатор характеристики", resource_regeneration: "Регенерация ресурса",
  max_resource_modifier: "Модификатор макс. ресурса", periodic_damage: "Периодический урон",
  control_effect: "Контроль", damage_response: "Ответ на урон", absorb_effect: "Поглощение",
  aura_effect: "Аура", summon_effect: "Призыв", curse_effect: "Проклятье", zone_effect: "Эффект зоны",
  zone_protection: "Защита от зоны", item_lifecycle: "Жизненный цикл предмета",
  crit_damage_modifier: "Модификатор урона крита", crit_chance_modifier: "Модификатор шанса крита",
  accuracy_modifier: "Модификатор точности", dodge_modifier: "Модификатор уклонения",
  physical_defense_modifier: "Модификатор физ. защиты", magic_defense_modifier: "Модификатор маг. защиты",
  inventory_slot_bonus: "Бонус слотов инвентаря", bonus_action_modifier: "Модификатор доп. действия",
  encounter_chance_modifier: "Модификатор шанса встречи",
};
export const EFFECT_SOURCE = {
  item: "Предмет", skill: "Навык", mob: "Моб", trap: "Ловушка", event: "Событие",
  zone: "Зона", curse: "Проклятье", admin: "Администратор",
};
export const EFFECT_TARGET = {
  self: "На себя", wearer: "Носитель", enemy: "Враг", ally: "Союзник", party: "Группа",
  raid: "Рейд", all_battle: "Все в бою", random: "Случайная цель",
};
export const EFFECT_ACTIVE_WHEN = {
  equipped: "Когда надет", in_inventory: "В инвентаре", in_battle: "В бою",
  on_enter_location: "При входе в локацию", on_death: "При смерти", on_attack: "При атаке",
  on_receive_damage: "При получении урона", on_deal_damage: "При нанесении урона", always: "Всегда",
};
export const EFFECT_STACK_RULE = {
  refresh: "Обновлять длительность", strongest_only: "Только сильнейший",
  stack_limited: "Стак с лимитом", unique_only: "Только уникальный",
};
export const STAT = {
  strength: "Сила", wisdom: "Мудрость", endurance: "Выносливость", agility: "Ловкость",
  perception: "Восприятие", intelligence: "Интеллект",
};
export const RESOURCE = { hp: "HP", mana: "Мана", spirit: "Дух" };
export const CONTROL_KIND = {
  stun: "Оглушение", confusion: "Замешательство", panic: "Паника", freeze: "Заморозка", root: "Обездвиживание",
};
export const ZONE_ELEMENT = {
  fire: "Огонь", water: "Вода", frost: "Мороз", earth: "Земля", wind: "Ветер", spirit: "Духи",
  curse: "Проклятье", holy: "Свет", shadow: "Тьма", chaos: "Хаос", ancient_magic: "Древняя магия",
};

// --- Конструктор достижений ------------------------------------------------
export const ACH_TYPE = {
  normal: "Обычное", hidden: "Скрытое", story: "Сюжетное", combat: "Боевое", craft: "Ремесло",
  exploration: "Исследование", economy: "Экономика", fishing: "Рыбалка", alchemy: "Алхимия",
  forge: "Кузница", social: "Социальное", guild: "Гильдейское", raid: "Рейдовое", world: "Мировое",
  festive: "Праздничное", seasonal: "Сезонное", unique: "Уникальное", one_time: "Одноразовое",
  repeatable: "Повторяемое", multi_stage: "Многоступенчатое",
};
export const ACH_VISIBILITY = {
  open: "Открытое", hidden_until_earned: "Скрыто до получения", fully_hidden: "Полностью скрыто",
  story: "Сюжетное", seasonal: "Сезонное", guild: "Гильдейское", admin: "Админское",
};
export const ACH_CONDITION_LOGIC = {
  any: "Любое из", all: "Все", ordered: "По порядку", n_of: "N из",
};
export const ACH_CONDITION_TYPE = {
  reach_level: "Достичь уровня", kill_mob: "Убить моба", kill_boss: "Убить босса",
  kill_world_boss: "Убить мирового босса", damage_world_boss: "Урон мировому боссу",
  join_raid: "Вступить в рейд", finish_raid: "Завершить рейд", find_item: "Найти предмет",
  craft_item: "Создать предмет", sell_item: "Продать предмет", buy_item: "Купить предмет",
  catch_fish: "Поймать рыбу", open_clam: "Вскрыть моллюска", find_pearl: "Найти жемчуг",
  visit_location: "Посетить локацию", discover_location: "Открыть локацию", finish_event: "Завершить событие",
  use_promo: "Использовать промокод", get_fine: "Получить штраф", pay_fine: "Оплатить штраф",
  survive_raid_event: "Выжить в облаве", get_warning: "Получить предупреждение",
  no_warnings_days: "Дни без предупреждений", join_guild: "Вступить в гильдию",
  create_guild: "Создать гильдию", contribute_guild: "Вклад в гильдию",
  finish_guild_quest: "Гильдейское задание", join_world_event: "Участие в мировом событии",
  contribute_global_progress: "Вклад в мировой прогресс", get_unique_item: "Получить уникальный предмет",
  use_artifact: "Использовать артефакт", revive_by_artifact: "Воскрешение артефактом",
};
export const ACH_PROGRESS_TYPE = {
  numeric: "Числовой", percent: "Проценты", list: "Список", stages: "Ступени",
  contribution: "Вклад", guild: "Гильдейский", world: "Мировой",
};
export const ACH_REWARD_TYPE = {
  experience: "Опыт", coins: "Монеты", item: "Предмет", unique_item: "Уникальный предмет",
  exp_grains: "Крупицы опыта", stat_points: "Очки характеристик", skill_points: "Очки навыков",
  temp_buff: "Временный баф", passive_bonus: "Пассивный бонус", title: "Титул", emblem: "Эмблема",
  profile_icon: "Иконка профиля", unlock_location: "Открыть локацию", unlock_npc: "Открыть NPC",
  unlock_recipe: "Открыть рецепт", unlock_event: "Открыть событие", guild_points: "Гильдейские очки",
  event_currency: "Событийная валюта",
};
export const ACH_REPEAT_PERIOD = {
  day: "День", week: "Неделя", month: "Месяц", season: "Сезон", festive: "Праздник",
};

// --- Конструктор штрафов ---------------------------------------------------
export const FINE_TYPE = {
  city: "Городской штраф", raid: "Штраф после облавы", chat_rules: "За нарушение правил чата",
  mechanic_abuse: "За злоупотребление механиками", criminal: "За криминальное действие",
  obligation: "За невыполнение обязательства", overdue: "За просрочку", assault: "За нападение",
  illegal_trade: "За запрещённую торговлю", forbidden_service: "За запрещённый сервис",
  manual: "Ручной штраф от администратора", system: "Системный штраф", story: "Сюжетный штраф",
};
export const FINE_SOURCE = {
  black_market_raid: "Облава на Чёрном рынке", informer_raid: "Облава у информатора Крота",
  casino_raid: "Облава в подпольном казино", guard_decision: "Решение стражи",
  manager_decision: "Решение Управляющего", admin_decision: "Решение администратора",
  auto_moderation: "Автоматическая модерация", player_moderator: "Игрок-модератор",
  player_report: "Жалоба игрока", chat_violation: "Нарушение в общем чате",
  trade_violation: "Нарушение в торговле", location_event: "Событие локации",
  story_event: "Сюжетное событие", quest_fail: "Провал задания",
  contract_violation: "Нарушение условий договора", system_check: "Системная проверка",
};
export const FINE_ISSUER_ROLE = {
  system: "Система", admin: "Администратор", senior_admin: "Старший администратор",
  moderator: "Модератор", player_moderator: "Игрок-модератор", guard: "Страж порядка",
  manager: "Управляющий", npc: "NPC", event: "Событие", location_script: "Скрипт локации",
};
export const CURRENCY = {
  copper: "Медные монеты", silver: "Серебряные монеты", gold: "Золотые монеты",
  magic_gold: "Магическое золото", ancient: "Древние монеты",
};
export const FINE_RESTRICTION = {
  block_city: "Запрет входа в город", block_starting: "Запрет стартовых локаций",
  block_market: "Запрет рынка", block_black_market: "Запрет Чёрного рынка",
  block_casino: "Запрет казино", block_transfer: "Запрет передачи предметов",
  block_chat: "Запрет общего чата", block_raids: "Запрет рейдов", block_quests: "Запрет заданий",
  force_fortress: "Перенос в Крепость в ущелье", raise_guard_check: "Повышенный шанс проверки стражей",
  raise_raid_chance: "Повышенный шанс облавы", debuff: "Дебаф на персонажа", debtor_mark: "Метка должника",
};

// --- Конструктор навыков ---------------------------------------------------
export const SKILL_TYPE = { active: "Активный", passive: "Пассивный" };
export const SKILL_BRANCH = { neutral: "Нейтральная", spirit: "Ветвь Духа", mana: "Ветвь Маны" };
export const SKILL_PATH = {
  none: "Без пути", sword: "Меч", dagger: "Кинжал", axe: "Топор", hammer: "Молот",
  bow: "Лук", shield: "Щит", crossbow: "Арбалет", fire: "Огонь", water: "Вода",
  earth: "Земля", air: "Воздух", support: "Поддержка", death: "Смерть", life: "Жизнь",
};
export const SKILL_RESOURCE_TYPE = { none: "Без ресурса", spirit: "Дух", mana: "Мана" };
export const SKILL_DAMAGE_TYPE = {
  none: "Без урона", physical: "Физический", magic: "Магический", mixed: "Смешанный",
};
export const SKILL_TARGET_MODE = {
  self: "На себя", single_enemy: "Один враг", all_enemies: "Все враги", ally: "Союзник",
  all_allies: "Все союзники", passive: "Пассивно",
};
export const SKILL_WEAPON_REQUIREMENT = {
  any: "Любое оружие", sword: "Меч", dagger: "Кинжал", axe: "Топор", hammer: "Молот",
  bow: "Лук", shield: "Щит", crossbow: "Арбалет", staff: "Посох", magic_book: "Магическая книга",
};

// --- Конструктор раскладки профиля -----------------------------------------
export const PROFILE_LAYOUT_KIND = {
  profile_tab: "Вкладка", profile_block: "Блок", profile_theme: "Оформление",
};
export const PROFILE_BLOCK_TYPE = {
  main_info: "Основные данные", resources: "HP/мана/дух/энергия", stats: "Характеристики",
  equipment: "Экипировка", inventory: "Инвентарь", effects: "Эффекты", fines: "Штрафы",
  warnings: "Предупреждения", activity: "Активность", currency: "Валюта", skills: "Навыки",
  passive_skills: "Пассивные навыки", services: "Сервисы", transfer: "Передача предметов",
  pavilion: "Торговый павильон", danger_zone: "Опасная зона",
};
export const PROFILE_VISIBILITY = {
  always: "Всегда", has_data: "Если есть данные", conditional: "По условию", hidden: "Скрыт",
};
export const PROFILE_BLOCK_WIDTH = { full: "Полная", half: "Половина", third: "Треть" };
export const PROFILE_TAB_PRESET = {
  character: "Персонаж", inventory: "Инвентарь", skills: "Навыки", services: "Сервисы",
  info: "Информация", effects: "Эффекты", activity: "Активность", pavilion: "Торговый Павильон",
  achievements: "Достижения", raids: "Рейды",
};

// --- Конструктор города и крепости -----------------------------------------
export const CITY_KIND = {
  city_node: "Узел", city_button: "Кнопка", city_shop_item: "Товар",
  city_service: "Сервис", criminal_zone: "Криминальная зона",
};
export const CITY_NODE_TYPE = {
  city: "Город", fortress: "Крепость", quarter: "Квартал", district: "Район",
  square: "Площадь", street: "Улица", alley: "Переулок", building: "Здание",
  townhall: "Ратуша", market: "Рынок", workshop: "Мастерская", tavern: "Таверна",
  pier: "Причал", outpost: "Застава", stand: "Стенд", board: "Доска объявлений",
  criminal_zone: "Криминальная зона", residential: "Жилой район", service: "Сервис",
  transition: "Переход",
};
export const CITY_BUTTON_ACTION = {
  goto_node: "Перейти в узел", open_market: "Открыть рынок", open_npc: "Открыть NPC",
  open_quests: "Открыть задания", open_craft: "Открыть ремесло", open_alchemy: "Открыть алхимию",
  start_fishing: "Начать рыбалку", open_fines: "Открыть штрафы", open_board: "Открыть доску",
  start_event: "Запустить событие", go_back: "Назад", show_message: "Показать сообщение",
};
export const CITY_SHOP_KIND = {
  city_market: "Городской рынок", port_market: "Портовый рынок", trade_quarter: "Торговый квартал",
  black_market: "Чёрный рынок", resource_buyer: "Скупщик ресурсов", npc_trader: "NPC-торговец",
  temp_trader: "Временный торговец", event_trader: "Событийный торговец", fortress_supplier: "Крепостной снабженец",
};
export const CITY_SERVICE_KIND = {
  smelter: "Плавильня", forge: "Кузница", leatherworks: "Кожевенная мастерская",
  alchemy: "Алхимическая мастерская", jewelry: "Ювелирная мастерская", enchanting: "Чародейская мастерская",
};
export const CITY_STOCK_TYPE = {
  always: "Доступен всегда", conditional: "По условию", event_only: "Во время события",
};

// --- Мировые события -------------------------------------------------------
export const WORLD_EVENT_TYPE = {
  festive: "Праздничное", seasonal: "Сезонное", permanent: "Постоянное", threat: "Угроза",
  world_boss: "Мировой босс", global_raid: "Глобальный рейд", mob_invasion: "Нашествие мобов",
  fair: "Ярмарка", city: "Городское", guild: "Гильдейское", story: "Сюжетное",
  economic: "Экономическое", boosted_drop: "Повышенный дроп", boosted_exp: "Повышенный опыт",
  new_location: "Новая локация",
};
export const EVENT_REPEAT_TYPE = {
  none: "Не повторять", weekly: "Каждую неделю", monthly: "Каждый месяц", yearly: "Каждый год",
};
export const EVENT_REWARD_TYPE = {
  experience: "Опыт", coins: "Монеты", item: "Предмет", resource: "Ресурс", effect: "Эффект",
  achievement: "Достижение", special_loot: "Особая добыча", temp_buff: "Временный бонус",
  temp_debuff: "Временный дебаф", event_shop: "Доступ к магазину события", special_location: "Доступ к локации",
};
export const SPECIAL_LOOT_SOURCE = {
  all_mobs: "Из всех мобов", selected_mobs: "Из выбранных мобов", all_events: "Из всех событий",
  selected_events: "Из выбранных событий", locations: "В выбранных локациях", search: "При поиске",
  battle: "При победе в бою", chest: "Из сундука", quest: "При завершении задания",
};

// --- Действия аудита (частые; код доступен в подсказке/тех-блоке) -----------
export const ACTION_LABEL = {
  "rewards.grant": "Выдача награды", "players.message": "Сообщение игроку",
  "players.unstuck": "Разблокировка (unstuck)", "fines.forgive": "Снятие штрафов",
  "fines.repair": "Проверка/починка штрафов", "players.reset": "Сброс игрока",
  "player.delete": "Удаление игрока", "players.delete": "Удаление игрока",
  "roles.change": "Смена роли", "promo.delete": "Удаление промокода",
  "promo.create": "Создание промокода", "broadcast.send": "Рассылка",
  "asset.image_change": "Смена изображения",
  "world.create_draft": "Мир: создан черновик", "world.edit_draft": "Мир: правка черновика",
  "world.set_status": "Мир: смена статуса", "world.validate": "Мир: проверка",
  "world.publish": "Мир: публикация", "world.disable": "Мир: отключение",
  "world.archive": "Мир: архив", "world.test_run": "Мир: тестовый проход",
  "world.import_existing": "Мир: импорт существующего",
  "item.publish": "Предмет: публикация", "item.disable": "Предмет: отключение",
  "item.archive": "Предмет: архив", "item.delete_soft": "Предмет: мягкое удаление",
  "item.delete_hard": "Предмет: полное удаление", "item.restore": "Предмет: восстановление",
  "effect.publish": "Эффект: публикация", "effect.disable": "Эффект: отключение",
  "effect.archive": "Эффект: архив", "effect.delete": "Эффект: удаление",
  "achievement.publish": "Достижение: публикация", "achievement.disable": "Достижение: отключение",
  "achievement.archive": "Достижение: архив", "achievement.grant_manual": "Достижение: ручная выдача",
  "achievement.revoke_manual": "Достижение: ручной откат",
  "guild.disable": "Гильдия: отключение", "world_event.start": "Событие: запуск",
  "world_event.stop": "Событие: остановка", "world_event.reward": "Событие: награды",
  "world_event.archive": "Событие: архив",
  "news.publish": "Новость: публикация", "guides.publish": "Гайд: публикация",
  "faq.publish": "FAQ: публикация", "site.settings_edit": "Сайт: настройки",
  "system.maintenance_on": "Режим обслуживания", "system.feature_flag": "Фичефлаг",
};

// --- Конструктор сайта -----------------------------------------------------
export const SITE_KIND = {
  news: "Новость", guide: "Гайд", faq: "FAQ", banner: "Баннер", announcement: "Объявление",
  page: "Страница", page_block: "Блок страницы", menu_item: "Пункт меню", post: "Пост",
  rating: "Рейтинг", lore: "Лор", where_is: "Что где находится", site_theme: "Оформление",
};
export const SITE_BLOCK_TYPE = {
  heading: "Заголовок", text: "Текст", image: "Изображение", gallery: "Галерея",
  banner: "Баннер", card: "Карточка", list: "Список", table: "Таблица", button: "Кнопка",
  link: "Ссылка", quote: "Цитата", warning: "Предупреждение", news: "Блок новости",
  guide: "Блок гайда", faq: "Блок FAQ", lore: "Блок лора", rating: "Блок рейтинга",
  where_is: "Что где находится", items: "Предметы", mobs: "Мобы", locations: "Локации",
  city: "Город", fortress: "Крепость",
};
export const SITE_PAGE_VISIBILITY = {
  public: "Публичная", authorized: "Для авторизованных", hidden: "Скрыта",
};
export const SITE_BLOCK_WIDTH = { full: "Полная", half: "Половина", third: "Треть", quarter: "Четверть" };
export const SITE_BLOCK_ALIGN = { left: "Слева", center: "По центру", right: "Справа" };
export const SITE_RATING_TYPE = {
  level: "По уровню", exp: "По опыту", wins: "По победам", pvp: "По PVP", loot: "По добыче",
  craft: "По ремеслу", events: "По событиям", raids: "По рейдам", wealth: "По богатству",
  weekly: "Недельный", monthly: "Месячный", seasonal: "Сезонный",
};
export const SITE_RATING_PERIOD = {
  all_time: "За всё время", weekly: "Неделя", monthly: "Месяц", seasonal: "Сезон",
};
export const SITE_LORE_TYPE = {
  history: "История мира", ancient_record: "Древняя запись", diary: "Дневник", book: "Книга",
  note: "Заметка", legend: "Легенда", race: "Описание расы", city: "Описание города",
  ancient_place: "Древнее место", seldar: "История Селдара", fortress: "История Крепости",
  ner_vir: "История Нер-Вира", ancients: "История Древних",
};
export const GUIDE_DIFFICULTY = {
  novice: "Новичок", normal: "Обычный", advanced: "Продвинутый", admin: "Админский", service: "Служебный",
};
export const BANNER_TYPE = {
  info: "Информация", warning: "Предупреждение", maintenance: "Тех. работы", event: "Событие",
  festive: "Праздник", promo: "Промо", danger: "Опасность", update: "Обновление",
};

// --- Справочники конструктора мира/локаций/мобов (ключи = metaKey из /kinds) ---
export const OPTION_LABELS = {
  locationTypes: {
    city: "Городская", starting: "Стартовая", wild: "Дикая", dungeon: "Подземелье",
    fortress: "Крепость", raid: "Рейдовая", world_boss: "Мировой босс",
    port: "Порт", market: "Рынок", camp: "Лагерь", story: "Сюжетная", event: "Событийная",
  },
  buttonActions: {
    goto_location: "Перейти в локацию", show_message: "Показать сообщение",
    start_search: "Начать поиск", start_battle: "Начать бой", open_shop: "Открыть магазин",
    open_npc: "Открыть NPC", open_quests: "Открыть задания", open_raids: "Открыть рейды",
    give_item: "Выдать предмет", take_item: "Списать предмет", check_condition: "Проверить условие",
    start_event: "Запустить событие", open_fishing: "Открыть рыбалку", open_camp: "Открыть лагерь",
    go_back: "Назад",
  },
  accessConditions: {
    always: "Всегда доступно", from_level: "С уровня", need_item: "Нужен предмет",
    need_quest: "Нужен квест", need_reputation: "Нужна репутация", blocked_fine: "Нельзя при штрафе",
    blocked_mute_ban: "Нельзя при муте/бане", blocked_battle: "Нельзя в бою",
    blocked_timer: "Нельзя при таймере", blocked_event: "Нельзя при активном событии",
  },
  eventTypes: {
    found_resource: "Найден ресурс", found_item: "Найден предмет", met_mob: "Встречен моб",
    trap: "Ловушка", chest: "Сундук", npc: "NPC", story: "Сюжетное", curse: "Проклятье",
    raid: "Рейд", energy_loss: "Потеря энергии", buff: "Баф", debuff: "Дебаф",
    hidden_transition: "Скрытый переход", rare_find: "Редкая находка",
  },
  eventResultTypes: {
    give_item: "Выдать предмет", give_currency: "Выдать валюту", give_exp: "Выдать опыт",
    take_item: "Списать предмет", take_currency: "Списать валюту", take_energy: "Списать энергию",
    start_battle: "Начать бой", move_player: "Переместить игрока", apply_buff: "Наложить баф",
    apply_debuff: "Наложить дебаф", show_text: "Показать текст", open_buttons: "Открыть кнопки",
    start_timer: "Запустить таймер", give_fine: "Выдать штраф", start_raid: "Запустить рейд",
  },
  npcFunctions: {
    shop: "Магазин", dialog: "Диалог", give_quest: "Выдать задание", accept_quest: "Принять задание",
    repair: "Ремонт", pay_fines: "Оплата штрафов", raids: "Рейды", board: "Доска заданий",
    craft: "Ремесло", teleport: "Телепорт", trade: "Торговля", training: "Обучение",
    informant: "Информатор",
  },
  questGoalTypes: {
    bring_item: "Принести предмет", kill_mob: "Убить моба", find_resource: "Найти ресурс",
    visit_location: "Посетить локацию", talk_npc: "Поговорить с NPC",
    deliver_item: "Доставить предмет", activate_object: "Активировать объект",
  },
  raidTypes: {
    world_boss: "Мировой босс", dungeon: "Подземелье", expedition: "Экспедиция", event_raid: "Событийный рейд",
  },
  npcKinds: {
    regular: "Обычный", quest_giver: "Квестодатель", questioner: "С вопросами",
    trader: "Торговец", special: "Особый",
  },
  eventOutcomeTypes: {
    battle: "Бой", trap: "Ловушка", resource: "Ресурс", item: "Предмет", nothing: "Ничего",
    battle_or_nothing: "Бой или ничего", resource_or_battle: "Ресурс или бой",
    trap_or_resource: "Ловушка или ресурс", special: "Особое событие", dialog: "Диалог с NPC",
    question: "Вопрос с ответами", open_access: "Открытие доступа", effect: "Эффект",
    curse: "Проклятие", state: "Состояние", lose_resource: "Потеря ресурса", fine: "Штраф",
    teleport: "Перенос в локацию", hidden_button: "Скрытая кнопка", chain: "Цепочка событий",
  },
  mobTypes: {
    beast: "Зверь", undead: "Нежить", bandit: "Разбойник", monster: "Чудовище", magic: "Магическое создание",
    human: "Человек", boss: "Босс", world_boss: "Мировой босс", event: "Событийный", raid: "Рейдовый",
    dwarf: "Дворф", elf: "Эльф", lizardfolk: "Ящеролюд", spirit: "Дух", demon: "Демон",
    cursed: "Проклятое существо", mechanism: "Механизм", golem: "Голем", elemental: "Стихийное существо",
    elite_boss: "Элитный босс", holiday: "Праздничный", guild: "Гильдейский",
  },
  zoneTypes: {
    fire: "Огонь", water: "Вода", frost: "Мороз", earth: "Земля", wind: "Ветер", spirit: "Духи",
    cursed: "Проклятая зона", poison: "Ядовитая зона", dark: "Тёмная зона", light: "Светлая зона",
    magic_anomaly: "Магическая аномалия", raid_zone: "Зона облавы", high_loot: "Зона повышенного дропа",
    high_danger: "Зона повышенной опасности",
  },
  resourceCategories: {
    herb: "Трава", berry: "Ягоды", alchemy: "Алхимический ингредиент", wood: "Дерево", stone: "Камень",
    ore: "Руда", leather: "Кожа", bone: "Кость", fish: "Рыба", shellfish: "Моллюск", pearl: "Жемчуг",
    trophy: "Трофей", event: "Событийный ресурс", guild: "Гильдейский ресурс", rare: "Редкая находка",
  },
  lootSources: {
    search: "Поиск", gather: "Добыча", fishing: "Рыбалка", chest: "Сундук", event: "Событие",
    hidden_event: "Скрытое событие", battle: "Бой", mob_drop: "Дроп моба", npc: "NPC", quest: "Квест",
    raid: "Рейд", world_event: "Мировое событие", guild_event: "Гильдейское событие",
  },
  weeklyLimitTypes: {
    resource: "Ресурс", item: "Предмет", trophy: "Трофей", mob: "Моб", mob_group: "Группа мобов",
    rare_mob: "Редкий моб", boss: "Босс", event: "Событие", hidden_event: "Скрытое событие",
    mob_drop: "Дроп моба", event_currency: "Событийная валюта", event_item: "Событийный предмет",
    guild_resource: "Гильдейский ресурс", world_progress: "Мировой прогресс",
  },
  rotationPeriodicity: {
    weekly: "Еженедельно", biweekly: "Каждые 2 недели", monthly: "Ежемесячно",
    event: "По событию", manual: "Вручную",
  },
  rotationSelectionModes: {
    random: "Случайно", weighted_random: "Случайно по весам", fixed_calendar: "Фиксированный календарь",
    seasonal: "Сезонно", manual: "Вручную", by_world_event: "По мировому событию",
    by_holiday: "По празднику", by_economy: "По экономике",
  },
  redistributionModes: {
    even: "Равномерно", by_weight: "По весам", same_group: "В той же группе",
    normal_only: "Только обычные", same_category: "В той же категории", none: "Не перераспределять",
  },
  eventGroups: {
    common: "Обычные", resource: "Ресурсные", loot: "Добыча", mob: "Боевые", trap: "Ловушки",
    rare: "Редкие", hidden: "Скрытые", story: "Сюжетные", holiday: "Праздничные", world: "Мировые",
    guild: "Гильдейские", empty: "Пустая локация",
  },
  depletionTriggers: {
    zero: "Когда остаток 0", below_10pct: "Ниже 10%", below_count: "Ниже количества",
    manual: "Вручную", world_event: "При мировом событии", zone_state: "При состоянии зоны",
  },
  mobVariantTypes: {
    normal: "Обычный", enhanced: "Усиленный", elite: "Элитный", rare: "Редкий", dangerous: "Опасный",
    mini_boss: "Мини-босс", boss: "Босс", raid: "Рейдовый", world_boss: "Мировой босс",
    event: "Событийный", holiday: "Праздничный", cursed: "Проклятый", zonal: "Зональный",
  },
  mobAttackTypes: {
    physical: "Физическая", magical: "Магическая", mixed: "Смешанная", poison: "Яд", bleed: "Кровотечение",
    fire: "Огонь", frost: "Мороз", water: "Вода", earth: "Земля", wind: "Ветер", spirit: "Дух",
    curse: "Проклятье", pure: "Чистый урон",
  },
  mobSkillTypes: {
    basic_attack: "Обычная атака", heavy_attack: "Усиленная атака", magic_attack: "Магическая атака",
    aoe_attack: "Массовая атака", poison: "Яд", bleed: "Кровотечение", stun: "Оглушение", burn: "Поджог",
    curse: "Проклятье", weaken: "Ослабление", reduce_accuracy: "Снижение точности",
    reduce_evasion: "Снижение уклонения", reduce_defense: "Снижение защиты", self_heal: "Лечение себя",
    regen: "Регенерация", summon: "Призыв союзника", self_buff: "Усиление себя",
    defensive_stance: "Защитная стойка", counter: "Контратака", vampirism: "Вампиризм", flee: "Побег",
    boss_phase: "Фаза босса",
  },
  mobSkillConditions: {
    always: "Всегда", hp_below: "Если HP ниже %", player_uses_magic: "Если игрок использует магию",
    player_uses_physical: "Если игрок бьёт физически", after_n_turns: "После N ходов",
    mob_enhanced: "Если моб усиленный", mob_elite: "Если моб элитный", zone_active: "Если активна зона",
    world_event_active: "Если активно мировое событие", raid_battle: "Если бой рейдовый",
    has_allies: "Если есть союзники", player_has_effect: "Если у игрока есть эффект",
  },
  mobBehaviorTypes: {
    aggressive: "Агрессивный", cautious: "Осторожный", defensive: "Защитный", fast: "Быстрый",
    magical: "Магический", poisonous: "Ядовитый", summoner: "Призывающий", support: "Поддержка",
    boss_phases: "Босс с фазами", random: "Случайное",
  },
  mobResistTypes: {
    physical: "Физический урон", magical: "Магический урон", fire: "Огонь", water: "Вода", frost: "Мороз",
    earth: "Земля", wind: "Ветер", spirit: "Дух", poison: "Яд", bleed: "Кровотечение", stun: "Оглушение",
    curse: "Проклятье", periodic: "Периодический урон", crit: "Критический урон",
  },
};

// Перевод одного значения по таблице.
export function tr(map, code) {
  if (code == null || code === "") return code;
  return (map && map[code]) || code;
}

// Перевод опции выпадающего списка конструктора по metaKey из /kinds.
export function trOption(metaKey, code) {
  const map = OPTION_LABELS[metaKey];
  return (map && map[code]) || code;
}
