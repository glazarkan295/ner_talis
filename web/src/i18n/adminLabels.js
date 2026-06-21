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
