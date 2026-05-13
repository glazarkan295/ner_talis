import React, { useMemo, useState } from "react";
import { profileMockData } from "./profileMockData.js";

const TABS = [
  { id: "character", label: "Персонаж", icon: "♙" },
  { id: "inventory", label: "Инвентарь", icon: "▣" },
  { id: "skills", label: "Навыки", icon: "✦" },
  { id: "info", label: "Информация", icon: "☷" },
];

const INVENTORY_CATEGORIES = [
  "Всё",
  "Снаряжение",
  "Оружие",
  "Бижутерия",
  "Алхимия",
  "Ресурсы",
  "Прочее",
  "Особое",
];

const RACE_INFO = {
  human: {
    name: "Человек",
    description: "Сбалансированная раса без сильных слабостей, быстро обучается и умеет извлекать выгоду из покупок.",
    stats: "Сила 3 · Ловкость 3 · Выносливость 4 · Интеллект 3 · Мудрость 3 · Восприятие 4",
    bonuses: [
      "Возврат золота: после покупки у NPC есть 5% шанс вернуть 3% потраченного золота.",
      "Обучаемость: получаемый опыт выше на 2%.",
      "Универсальность: все основные характеристики выше на 1%.",
    ],
  },
  elf: {
    name: "Эльф",
    description: "Ловкая и разумная раса, хорошо чувствует магию, природу и алхимию.",
    stats: "Сила 2 · Ловкость 4 · Выносливость 2 · Интеллект 5 · Мудрость 4 · Восприятие 3",
    bonuses: [
      "Магия: магический урон выше на 3%.",
      "Алхимия: шанс создать зелье повышенного качества выше на 4%.",
      "Знание трав: шанс получить дополнительный алхимический ингредиент выше на 3%.",
    ],
  },
  dwarf: {
    name: "Дворф",
    description: "Крепкая и выносливая раса мастеров, сильна в кузнечном деле и работе с металлом.",
    stats: "Сила 5 · Ловкость 2 · Выносливость 5 · Интеллект 3 · Мудрость 3 · Восприятие 2",
    bonuses: [
      "Кузнечное дело: шанс создать оружие или броню повышенного качества выше на 4%.",
      "Работа с металлом: расход руды и металла при создании снаряжения ниже на 3%.",
      "Крепкое телосложение: максимальная выносливость выше на 3%.",
    ],
  },
  undead: {
    name: "Нежить",
    description: "Мрачная и живучая раса, устойчивая к боли, ядам, проклятиям и другим эффектам.",
    stats: "Сила 3 · Ловкость 2 · Выносливость 6 · Интеллект 3 · Мудрость 4 · Восприятие 2",
    bonuses: [
      "Выживаемость: максимальное здоровье выше на 4%.",
      "Сопротивление эффектам: шанс получить яд, кровотечение, оглушение и проклятие ниже на 5%.",
      "Мёртвая плоть: периодический урон ниже на 3%.",
    ],
  },
  lizardfolk: {
    name: "Ящеролюд",
    description: "Сильная дикая раса с крепкой чешуёй, боевой регенерацией и чутьём на добычу.",
    stats: "Сила 4 · Ловкость 4 · Выносливость 4 · Интеллект 1 · Мудрость 2 · Восприятие 5",
    bonuses: [
      "Регенерация в бою: восстанавливает 0.5% здоровья раз в ход.",
      "Крепкая чешуя: физический урон ниже на 2%.",
      "Чутьё на добычу: шанс найти добычу, следы или ресурсы выше на 4%.",
    ],
  },
};

const RACE_NAME_TO_KEY = {
  человек: "human",
  эльф: "elf",
  дворф: "dwarf",
  нежить: "undead",
  ящеролюд: "lizardfolk",
};

function qualityClass(quality = "обычный") {
  return `quality-${String(quality).toLowerCase().replace(/\s+/g, "-")}`;
}

function getRaceInfo(player) {
  const key = player?.raceKey || RACE_NAME_TO_KEY[String(player?.raceName || "").toLowerCase()] || "human";
  return RACE_INFO[key] || { ...RACE_INFO.human, name: player?.raceName || "Раса" };
}

function Panel({ title, children, right, className = "" }) {
  return (
    <section className={`nt-panel ${className}`.trim()}>
      <header className="nt-panel-head">
        <h2>{title}</h2>
        {right ? <div className="nt-panel-right">{right}</div> : null}
      </header>
      {children}
    </section>
  );
}

function Row({ label, value, children, className = "" }) {
  return (
    <div className={`nt-row ${className}`.trim()}>
      <span>{label}</span>
      <strong>{value}</strong>
      {children}
    </div>
  );
}

function CardRow({ label, value }) {
  return (
    <div className="nt-card-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function RaceInfoButton({ onClick }) {
  return (
    <button className="nt-race-info-button" type="button" onClick={onClick} title="Бонусы расы" aria-label="Показать бонусы расы">
      !
    </button>
  );
}

function RaceInfoModal({ profile, onClose }) {
  if (!profile) return null;
  const race = getRaceInfo(profile.player);

  return (
    <div className="nt-modal-layer" onMouseDown={onClose}>
      <article className="nt-modal nt-race-modal" onMouseDown={(event) => event.stopPropagation()}>
        <button className="nt-modal-close" onClick={onClose}>×</button>
        <div className="nt-modal-kicker">Бонусы расы</div>
        <h3>{race.name}</h3>
        <p>{race.description}</p>
        <div className="nt-modal-block">
          <h4>Стартовые характеристики</h4>
          <p className="nt-race-stats">{race.stats}</p>
        </div>
        <div className="nt-modal-block">
          <h4>Бонусы</h4>
          <ul>{race.bonuses.map((bonus) => <li key={bonus}>{bonus}</li>)}</ul>
        </div>
        <footer className="nt-modal-actions">
          <button className="nt-secondary" onClick={onClose}>Закрыть</button>
        </footer>
      </article>
    </div>
  );
}

function Modal({ item, slotKey, onClose, onEquipItem, onUnequipItem, onUseItem }) {
  if (!item) return null;
  const actions = item.actions || [];

  return (
    <div className="nt-modal-layer" onMouseDown={onClose}>
      <article className={`nt-modal ${qualityClass(item.quality)}`} onMouseDown={(event) => event.stopPropagation()}>
        <button className="nt-modal-close" onClick={onClose}>×</button>
        <div className="nt-modal-kicker">{item.category || "Предмет"}</div>
        <h3>{item.name}</h3>
        <div className="nt-modal-grid">
          <span>Тип</span><strong>{item.type || "—"}</strong>
          <span>Качество</span><strong>{item.quality || "обычный"}</strong>
          <span>Уровень</span><strong>{item.level || 1}</strong>
          <span>Слот</span><strong>{slotKey || item.targetSlotKey || item.slotKey || "—"}</strong>
        </div>
        <p>{item.description || "Описание предмета пока не добавлено."}</p>
        {item.stats?.length ? (
          <div className="nt-modal-block">
            <h4>Свойства</h4>
            <ul>{item.stats.map((line) => <li key={line}>{line}</li>)}</ul>
          </div>
        ) : null}
        {item.enchantments?.length ? (
          <div className="nt-modal-block">
            <h4>Зачарования</h4>
            <ul>{item.enchantments.map((line) => <li key={line}>{line}</li>)}</ul>
          </div>
        ) : null}
        {item.compare?.length ? (
          <div className="nt-modal-block">
            <h4>Сравнение</h4>
            <ul>{item.compare.map((line) => <li key={line}>{line}</li>)}</ul>
          </div>
        ) : null}
        <footer className="nt-modal-actions">
          {actions.includes("Надеть") ? <button onClick={() => onEquipItem?.(item)}>Надеть</button> : null}
          {actions.includes("Снять") ? <button onClick={() => onUnequipItem?.(slotKey || item.slotKey, item)}>Снять</button> : null}
          {actions.includes("Использовать") ? <button onClick={() => onUseItem?.(item)}>Использовать</button> : null}
          <button className="nt-secondary" onClick={onClose}>Закрыть</button>
        </footer>
      </article>
    </div>
  );
}

function CharacterTab({ profile, onOpenItem, onSpendAttributePoints }) {
  const [inputs, setInputs] = useState({});
  const [showRaceInfo, setShowRaceInfo] = useState(false);
  const freePoints = profile.player.freeAttributePoints || 0;
  const expMax = Math.max(1, profile.player.experienceToNext || 1);
  const expPercent = Math.min(100, Math.round(((profile.player.experienceCurrent || 0) / expMax) * 100));

  function spend(attributeKey) {
    const amount = Math.max(0, Math.floor(Number(inputs[attributeKey] || 0)));
    if (!amount) return;
    onSpendAttributePoints?.(attributeKey, amount);
    setInputs((current) => ({ ...current, [attributeKey]: "" }));
  }

  return (
    <div className="nt-stack nt-character-stack">
      <Panel title="Экипировка">
        <div className="nt-equipment-grid">
          {profile.equipmentSlots.map((slot) => {
            const item = profile.equipment?.[slot.key];
            return (
              <button
                key={slot.key}
                className={`nt-equip-slot ${item ? qualityClass(item.quality) : "empty"}`}
                onClick={() => item && onOpenItem(item, slot.key)}
                title={item?.name || slot.label}
              >
                <span className="nt-equip-icon">{slot.icon}</span>
                <span className="nt-equip-label">{slot.label}</span>
                <strong>{item?.name || "Пусто"}</strong>
              </button>
            );
          })}
        </div>
      </Panel>

      <Panel title="Сводка" right={<span className="nt-badge">{profile.player.branch}</span>}>
        <div className="nt-lines">
          <Row label="Ник" value={profile.player.nickname} />
          <Row
            label={<span className="nt-label-with-action">Раса <RaceInfoButton onClick={() => setShowRaceInfo(true)} /></span>}
            value={profile.player.raceName}
          />
          <Row label="Уровень" value={profile.player.level} />
          <Row label="Баланс" value={profile.player.balanceText} />
          <Row label="Свободные характеристики" value={freePoints} />
          <Row label="Свободные очки навыков" value={profile.player.freeSkillPoints} />
        </div>
        <div className="nt-progress-label">Опыт: {profile.player.experienceCurrent} / {profile.player.experienceToNext}</div>
        <div className="nt-progress"><i style={{ width: `${expPercent}%` }} /></div>
      </Panel>

      <Panel title="Характеристики" right={<span className="nt-badge">{freePoints}</span>}>
        <div className="nt-attributes nt-lines">
          {profile.attributes.map((attribute) => (
            <div key={attribute.key} className="nt-attribute nt-row">
              <span>{attribute.label}</span>
              <strong>{attribute.value}</strong>
              {freePoints ? (
                <div className="nt-attribute-controls">
                  <input
                    type="number"
                    min="1"
                    max={freePoints}
                    value={inputs[attribute.key] || ""}
                    onChange={(event) => setInputs((current) => ({ ...current, [attribute.key]: event.target.value }))}
                    aria-label={`Очки в ${attribute.label}`}
                  />
                  <button onClick={() => spend(attribute.key)}>+</button>
                </div>
              ) : null}
            </div>
          ))}
        </div>
      </Panel>

      <Panel title="Параметры">
        <div className="nt-params nt-lines">
          {profile.parameters.map((parameter) => (
            <Row key={parameter.label} label={parameter.label} value={parameter.value} />
          ))}
        </div>
      </Panel>

      {profile.effects?.length ? (
        <Panel title="Эффекты">
          <div className="nt-card-list nt-column-list">
            {profile.effects.map((effect) => (
              <div key={effect.name || effect} className="nt-mini-card">
                <CardRow label={effect.name || effect} value="Активно" />
                <p>{effect.description || "Активный эффект"}</p>
              </div>
            ))}
          </div>
        </Panel>
      ) : null}

      <Panel title="Активные сеты">
        {profile.activeSets?.length ? (
          <div className="nt-card-list nt-column-list">
            {profile.activeSets.map((set) => (
              <div key={set.name} className="nt-mini-card">
                <CardRow label={set.name} value="Сет" />
                <p>{set.bonus}</p>
              </div>
            ))}
          </div>
        ) : <p className="nt-empty-text">Активных сетов нет.</p>}
      </Panel>

      {showRaceInfo ? <RaceInfoModal profile={profile} onClose={() => setShowRaceInfo(false)} /> : null}
    </div>
  );
}

function InventoryTab({ profile, onOpenItem }) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("Всё");
  const categories = useMemo(() => {
    const customCategories = profile.inventory
      .map((item) => item.category || "Прочее")
      .filter((item) => !INVENTORY_CATEGORIES.includes(item));
    return [...INVENTORY_CATEGORIES, ...new Set(customCategories)];
  }, [profile.inventory]);

  const items = profile.inventory.filter((item) => {
    const itemCategory = item.category || "Прочее";
    const matchesCategory = category === "Всё" || itemCategory === category;
    const matchesQuery = item.name.toLowerCase().includes(query.toLowerCase());
    return matchesCategory && matchesQuery;
  });

  return (
    <div className="nt-stack">
      <Panel title="Инвентарь">
        <div className="nt-toolbar nt-inventory-toolbar">
          <input placeholder="Поиск предмета" value={query} onChange={(event) => setQuery(event.target.value)} />
          <div className="nt-category-row">
            {categories.map((item) => (
              <button key={item} className={category === item ? "active" : ""} onClick={() => setCategory(item)}>{item}</button>
            ))}
          </div>
        </div>
        <div className="nt-items-grid nt-column-list">
          {items.length ? items.map((item) => (
            <button key={item.id} className={`nt-item ${qualityClass(item.quality)}`} onClick={() => onOpenItem(item)}>
              <CardRow label={item.name} value={item.quality} />
              <CardRow label={item.type || "Предмет"} value={`ур. ${item.level} · ×${item.amount || 1}`} />
            </button>
          )) : <p className="nt-empty-text">Предметы не найдены.</p>}
        </div>
      </Panel>
    </div>
  );
}

function SkillsTab({ profile }) {
  return (
    <div className="nt-stack">
      <Panel title="Развитие" right={<span className="nt-badge">{profile.player.freeSkillPoints || 0}</span>}>
        <div className="nt-lines">
          <Row label="Свободные очки навыков" value={profile.player.freeSkillPoints || 0} />
          <Row label="Ветвь развития" value={profile.player.branch || "—"} />
        </div>
      </Panel>
      <Panel title="Активные навыки">
        <div className="nt-card-list nt-column-list">
          {(profile.skills?.active || []).length ? (profile.skills?.active || []).map((skill) => (
            <div key={skill.name} className="nt-mini-card">
              <CardRow label={skill.name} value={`ур. ${skill.level}`} />
              <p>{skill.description}</p>
            </div>
          )) : <p className="nt-empty-text">Активных навыков пока нет.</p>}
        </div>
      </Panel>
      <Panel title="Пассивные навыки">
        <div className="nt-card-list nt-column-list">
          {(profile.skills?.passive || []).length ? (profile.skills?.passive || []).map((skill) => (
            <div key={skill.name} className="nt-mini-card">
              <CardRow label={skill.name} value={`ур. ${skill.level}`} />
              <p>{skill.description}</p>
            </div>
          )) : <p className="nt-empty-text">Пассивных навыков пока нет.</p>}
        </div>
      </Panel>
    </div>
  );
}

function InfoTab({ profile }) {
  const info = profile.information || {};
  return (
    <div className="nt-stack">
      <Panel title="Активность">
        <div className="nt-lines">
          <Row label="PVE убийства" value={info.activity?.pveKills || 0} />
          <Row label="PVP убийства" value={info.activity?.pvpKills || 0} />
          <Row label="Частицы душ" value={info.activity?.soulParticlesAbsorbed || 0} />
          <Row label="Дата регистрации" value={profile.player.registrationDate} />
        </div>
      </Panel>
      <Panel title="Достижения">
        <div className="nt-card-list nt-column-list">
          {(info.achievements || []).length ? (info.achievements || []).map((achievement) => (
            <div key={achievement.name || achievement} className="nt-mini-card">
              <CardRow label={achievement.name || achievement} value="Получено" />
              <p>{achievement.description || "—"}</p>
            </div>
          )) : <p className="nt-empty-text">Достижений пока нет.</p>}
        </div>
      </Panel>
      <Panel title="Ремёсла">
        <div className="nt-card-list nt-column-list">
          {(info.activity?.craftingLevels || []).length ? (info.activity?.craftingLevels || []).map((craft) => (
            <div key={craft.name} className="nt-mini-card">
              <CardRow label={craft.name} value={`ур. ${craft.level}`} />
              <p>{craft.exp}</p>
            </div>
          )) : <p className="nt-empty-text">Ремёсла пока не развиты.</p>}
        </div>
      </Panel>
    </div>
  );
}

export function PlayerProfile({ profile = profileMockData, onSpendAttributePoints, onEquipItem, onUnequipItem, onUseItem }) {
  const [tab, setTab] = useState("character");
  const [modal, setModal] = useState(null);
  const background = profile.assets?.background || "/assets/profile/backgrounds/1.png";

  function openItem(item, slotKey = null) {
    setModal({ item, slotKey });
  }

  return (
    <main className="nt-profile" style={{ backgroundImage: `linear-gradient(rgba(5, 7, 7, .50), rgba(4, 4, 4, .70)), url(${background})` }}>
      <div className="nt-shell">
        <header className="nt-top">
          <div>
            <span className="nt-kicker">Мир Нер-Талис</span>
            <h1>Профиль персонажа</h1>
          </div>
          <div className="nt-id">ID: {profile.player.userGlobalId}</div>
        </header>

        <nav className="nt-tabs" aria-label="Разделы профиля">
          {TABS.map(({ id, label, icon }) => (
            <button key={id} className={tab === id ? "active" : ""} onClick={() => setTab(id)} title={label} aria-label={label}>
              <span className="nt-tab-icon">{icon}</span>
              <span className="nt-tab-text">{label}</span>
            </button>
          ))}
        </nav>

        <section className="nt-content">
          {tab === "character" ? <CharacterTab profile={profile} onOpenItem={openItem} onSpendAttributePoints={onSpendAttributePoints} /> : null}
          {tab === "inventory" ? <InventoryTab profile={profile} onOpenItem={openItem} /> : null}
          {tab === "skills" ? <SkillsTab profile={profile} /> : null}
          {tab === "info" ? <InfoTab profile={profile} /> : null}
        </section>
      </div>

      <Modal
        item={modal?.item}
        slotKey={modal?.slotKey}
        onClose={() => setModal(null)}
        onEquipItem={onEquipItem}
        onUnequipItem={onUnequipItem}
        onUseItem={onUseItem}
      />
    </main>
  );
}
