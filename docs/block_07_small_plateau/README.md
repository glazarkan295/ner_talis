# Нер-Талис — пакет интеграции локации «Малое плато»

Пакет подготовлен как overlay для интеграции в основной проект. Он не заменяет полный архив проекта, а добавляет новую локацию, предметы, тексты, таблицу событий, механику проклятья и пороги поисков.

## Состав

- `data/small_plateau_location.json` — описание локации, кнопки, лагерь, арка, стандартные правила поиска.
- `data/small_plateau_search_events.json` — 27 событий поиска по руинам.
- `data/items_small_plateau.json` — предметы `old_brooch` и `old_medallion`.
- `data/small_plateau_mechanics.json` — Древнее Проклятье, ожоги амулета, достижения и пороги поиска.
- `data/small_plateau_texts.json` — отдельные тексты проклятья и арки.
- `services/small_plateau_service.py` — изолированная логика для подключения к runtime проекта.
- `tests/test_small_plateau_service.py` — базовые тесты логики.
- `web/public/assets/items/junk/old_brooch.jpg` — ассет старой броши.
- `web/public/assets/items/junk/old_medallion.jpg` — ассет старого медальона.
- `source/small_plateau_user_source.txt` — исходный текст пользователя.

## Как подключать в проект

1. Скопировать `data/*.json` в папку `data/` проекта.
2. Скопировать `services/small_plateau_service.py` в `services/` проекта.
3. Скопировать ассеты из `web/public/assets/items/junk/` в такую же папку проекта.
4. Подключить `small_plateau_location.json` к списку внешних локаций.
5. В роутере внешних локаций добавить кнопки:
   - `small_plateau_start_search`
   - `small_plateau_camp`
   - `small_plateau_arch_menu`
   - `small_plateau_inspect_arch`
   - `small_plateau_main`
6. После завершения стандартного таймера поиска вызывать:
   ```python
   from services.small_plateau_service import resolve_small_plateau_search
   result = resolve_small_plateau_search(player_state)
   ```
7. Если `result["requires_choice"] == True`, показать игроку выбор из события `cursed_silver_coins`:
   - «Взять монеты» → `handle_cursed_coin_choice(player_state, True)`
   - «Уйти» → `handle_cursed_coin_choice(player_state, False)`
8. При действиях игрока в городе, крепости, поиске на локациях и отдыхе в лагере вызывать:
   ```python
   roll_ancient_curse_trigger(player_state, action_type)
   ```
9. Из hourly scheduler проекта вызывать:
   ```python
   tick_amulet_burn_hourly(player_state)
   ```
10. Для учёта достижения «Проклятье? Какое проклятье?» раз в игровой день вызывать:
   ```python
   register_ancient_curse_active_day(player_state, activity_minutes_today)
   ```

## Важное про шансы событий

В исходном описании почти у всех событий указан шанс 40%, а у одного события 30%. Для одной таблицы случайного поиска сумма таких шансов превышает 100%, поэтому в интеграционном JSON они сохранены в поле `source_chance_label`, а фактический выбор выполнен через `weight`.

## Незакрытые моменты

- Ассеты броши и медальона приложены как `.jpg`. На изображениях виден шахматный фон, поэтому перед финальной публикацией можно отдельно очистить фон и заменить ссылки на `.png`.
- Если в основном проекте уже есть отдельный формат описания локаций/предметов/эффектов, JSON из пакета нужно привести к этому формату при финальной интеграции.
