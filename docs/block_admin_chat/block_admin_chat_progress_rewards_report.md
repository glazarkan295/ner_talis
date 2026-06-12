# Блок админ-чата: очки навыков, очки характеристик и крупицы опыта

Добавлены команды для админского начисления прогресс-ресурсов игрока.

## Правила ресурсов

- очки навыков: 1 единица = 1 свободное очко навыков;
- очки характеристик: 1 единица = 1 свободное очко характеристик;
- крупицы опыта: 1 единица = 1 опыт.

## Команды

```text
/admin_add_experience GAME_ID AMOUNT CONFIRM
/admin_add_exp GAME_ID AMOUNT CONFIRM
/admin_add_stat_points GAME_ID AMOUNT CONFIRM
/admin_add_attribute_points GAME_ID AMOUNT CONFIRM
/admin_add_skill_points GAME_ID AMOUNT CONFIRM
```

`/admin_add_experience` начисляет опыт ровно 1 к 1 без расового множителя, потому что крупица опыта уже является единицей опыта. Повышение уровня и выдача свободных очков за уровень сохраняются.

Для очков характеристик и навыков разрешены положительные и отрицательные значения, но списание не может увести значение ниже нуля.

## Ассеты

Добавлены очищенные публичные PNG:

- `/assets/admin_rewards/skill_points.png`;
- `/assets/admin_rewards/stat_points.png`;
- `/assets/admin_rewards/experience_shards.png`.

Карта ассетов: `data/admin_reward_assets.json`.
