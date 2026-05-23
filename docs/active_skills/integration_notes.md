# Интеграция активных навыков в проект

## Файлы пакета

- `active_skills_registry.json` — основной машинный реестр навыков.
- `active_skills_catalog.md` — человекочитаемый каталог всех навыков.
- `branch_choice_seldar_order_stone.md` — отдельный сценарий выбора ветви в Селдаре.
- `branch_choice_messages.json` — готовые сообщения бота.
- `active_skills_seed.py` — пример загрузчика навыков в код проекта.
- `active_skill_balance_rules.md` — правила расчётов и ограничений.

## Главное исправление

Активные навыки **не открываются напрямую за уровень игрока**.

Уровень персонажа может:

- выдать свободные очки характеристик;
- выдать очки навыков;
- на 10 уровне открыть системный доступ к выбору ветви;
- открыть доступ к зонам, наставникам, книгам, событиям или испытаниям.

Но сам активный навык должен открываться только через требования в `skill["unlock"]["requirements"]`.

## Что важно для кода

1. До 10 уровня игроку не показывать выбор ветви.
2. После достижения 10 уровня не выбирать ветвь автоматически.
3. Выбор проходит только через сценарий: `Селдар → Верхний квартал → Ратуша → Распорядительный камень → Идентификационный амулет`.
4. До выбора ветви игрок может использовать только `resource_branch = neutral`.
5. После выбора `player.skill_branch = spirit` можно проверять навыки `spirit` и совместимые `neutral_special`.
6. После выбора `player.skill_branch = mana` можно проверять навыки `mana` и совместимые `neutral_special`.
7. Свитки случайного улучшения не должны выбирать навыки закрытой ветви.
8. Характеристические особые навыки открываются только от вложенных характеристик. Бонусы вещей, зелий, еды, напитков, баффов, проклятий и временных эффектов не засчитываются.
9. Отдельный параметр `concentration` не используется.
10. Поле `min_level` удалено из навыков. Не добавлять его обратно как условие открытия активного навыка.

## Проверка возможности выбрать ветвь

```python
def can_choose_branch_at_order_stone(player) -> bool:
    return (
        player.level >= 10
        and player.skill_branch is None
        and player.current_city == "seldar"
        and player.current_zone == "town_hall"
        and player.current_place == "order_stone"
        and player.has_identification_amulet
    )
```

Эта проверка относится только к выбору ветви. Она не открывает конкретные активные навыки напрямую.

## Проверка доступности навыка

```python
def can_learn_or_use_skill(player, skill, registry) -> bool:
    branch = skill.get("resource_branch")
    unlock = skill.get("unlock", {})

    if branch == "neutral":
        return True

    player_branch = getattr(player, "skill_branch", None)
    if not player_branch:
        return False

    if player_branch not in skill.get("allowed_branches", []):
        return False

    if unlock.get("type") == "invested_attribute_threshold":
        attribute = unlock.get("attribute")
        threshold = unlock.get("threshold", 0)
        invested = getattr(player, "invested_attributes", {}).get(attribute, 0)
        if invested < threshold:
            return False

    for requirement in unlock.get("requirements", []):
        if not check_skill_requirement(player, requirement, registry):
            return False

    if skill["resource"] == "spirit" and player.spirit < skill["base_resource_cost"]:
        return False

    if skill["resource"] == "mana" and player.mana < skill["base_resource_cost"]:
        return False

    return True
```

## Сообщение-подсказка на 10 уровне

При достижении 10 уровня бот должен сразу отправить сообщение из `branch_choice_messages.json -> level_10_branch_hint` и установить `player.branch_choice_hint_sent = true`, чтобы не дублировать подсказку.


## Синхронизация оружия

Текущие активные навыки используют только эти типы оружия проекта:

- `sword` — меч;
- `dagger` — кинжал;
- `staff` — посох;
- `axe` — топор;
- `hammer` — молот;
- `bow` — лук;
- `shield` — щит;
- `crossbow` — арбалет.

`any` используется только для универсальных действий без привязки к оружию. Старые или лишние значения `spear`, `focus`, `unarmed`, `any_melee`, `two_handed_sword`, `heavy_armor`, `medium_armor` в `weapon_requirements` больше не используются. Если ограничение связано с бронёй, оно вынесено в `equipment_requirements` или в требование `weapon_or_equipment_type`.


## Правило оружейных требований

`weapon_requirements` — это список, а не одиночное значение. У части навыков может быть несколько допустимых типов оружия. Проверка выполняется по правилу `any_of`: если текущее оружие игрока входит в список, навык можно использовать. `any` применяется только для универсальных действий, которые не зависят от оружия.


## Боеприпасы

Для навыков с `bow` и `crossbow` добавлено поле `ammo_requirements`.

Порядок применения навыка:

1. Проверить, что навык открыт по ветви, предыдущим навыкам, модификаторам, вложенным характеристикам, оружию и источникам обучения.
2. Проверить подходящее оружие по `weapon_requirements`.
3. Если текущее оружие `bow`, проверить наличие `arrow_for_bow`.
4. Если текущее оружие `crossbow`, проверить наличие `bolt_for_crossbow`.
5. Если боеприпасов нет, вывести сообщение и не тратить дух/ману.
6. Если боеприпасы есть, списать нужное количество и затем выполнить обычную логику навыка.

Если в проекте уже есть другие ID предметов для стрел и болтов, замените только `ammo_item_id`.


## Обновление: колчаны для стрел и болтов

Для лука и арбалета добавлены обязательные контейнеры боеприпасов:

- `arrow_quiver_empty` — Пустой колчан для стрел лука.
- `bolt_quiver_empty` — Пустой колчан для болтов арбалета.
- `arrow_for_bow` — Стрела для лука.
- `bolt_for_crossbow` — Болт для арбалета.

Навык с луком проверяет экипированный `arrow_quiver` и количество стрел внутри него. Навык с арбалетом проверяет экипированный `bolt_quiver` и количество болтов внутри него. Свободные боеприпасы в инвентаре не списываются напрямую активным навыком.
