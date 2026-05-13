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

function qualityClass(quality = "обычный") {
  return `quality-${String(quality).toLowerCase().replace(/\s+/g, "-")}`;
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
        <div className="nt-summary nt-lines">
          <div><span>Ник</span><strong>{profile.player.nickname}</strong></div>
          <div><span>Раса</span><strong>{profile.player.raceName}</strong></div>
          <div><span>Уровень</span><strong>{profile.player.level}</strong></div>
          <div><span>Баланс</span><strong>{profile.player.balanceText}</strong></div>
          <div><span>Свободные характеристики</span><strong>{freePoints}</strong></div>
          <div><span>Свободные очки навыков</span><strong>{profile.player.freeSkillPoints}</strong></div>
        </div>
        <div className="nt-progress-label">Опыт: {profile.player.experienceCurrent} / {profile.player.experienceToNext}</div>
        <div className="nt-progress"><i style={{ width: `${expPercent}%` }} /></div>
      </Panel>

      <Panel title="Характеристики" right={<span className="nt-badge">{freePoints}</span>}>
        <div className="nt-attributes nt-lines">
          {profile.attributes.map((attribute) => (
            <div key={attribute.key} className="nt-attribute">
              <strong>{attribute.label}</strong>
              <span>{attribute.value}</span>
              {freePoints ? (
                <div className="nt-attribute-controls">
                  <input
                    type="number"
                    min="1"
                    max={freePoints}
                    value={inputs[attribute.key] || ""}
                    onChange={(event) => setInputs((current) => ({ ...current, [attribute.key]: event.target.value }))}
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
            <div key={parameter.label}>
              <span>{parameter.label}</span>
              <strong>{parameter.value}</strong>
            </div>
          ))}
        </div>
      </Panel>

      {profile.effects?.length ? (
        <Panel title="Эффекты">
          <div className="nt-card-list nt-column-list">
            {profile.effects.map((effect) => (
              <div key={effect.name || effect} className="nt-mini-card">
                <strong>{effect.name || effect}</strong>
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
                <strong>{set.name}</strong>
                <p>{set.bonus}</p>
              </div>
            ))}
          </div>
        ) : <p className="nt-empty-text">Активных сетов нет.</p>}
      </Panel>
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
              <strong>{item.name}</strong>
              <span>{item.type} · ур. {item.level} · ×{item.amount || 1}</span>
              <em>{item.quality}</em>
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
      <Panel title="Развитие" right={<span className="nt-badge">{profile.player.freeSkillPoints || 0} очков</span>}>
        <div className="nt-lines">
          <div><span>Свободные очки навыков</span><strong>{profile.player.freeSkillPoints || 0}</strong></div>
          <div><span>Ветвь развития</span><strong>{profile.player.branch || "—"}</strong></div>
        </div>
      </Panel>
      <Panel title="Активные навыки">
        <div className="nt-card-list nt-column-list">
          {(profile.skills?.active || []).map((skill) => (
            <div key={skill.name} className="nt-mini-card"><strong>{skill.name}</strong><p>{skill.description}</p><span>ур. {skill.level}</span></div>
          ))}
        </div>
      </Panel>
      <Panel title="Пассивные навыки">
        <div className="nt-card-list nt-column-list">
          {(profile.skills?.passive || []).map((skill) => (
            <div key={skill.name} className="nt-mini-card"><strong>{skill.name}</strong><p>{skill.description}</p><span>ур. {skill.level}</span></div>
          ))}
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
          <div><span>PVE убийства</span><strong>{info.activity?.pveKills || 0}</strong></div>
          <div><span>PVP убийства</span><strong>{info.activity?.pvpKills || 0}</strong></div>
          <div><span>Частицы душ</span><strong>{info.activity?.soulParticlesAbsorbed || 0}</strong></div>
          <div><span>Дата регистрации</span><strong>{profile.player.registrationDate}</strong></div>
        </div>
      </Panel>
      <Panel title="Достижения">
        <div className="nt-card-list nt-column-list">
          {(info.achievements || []).length ? (info.achievements || []).map((achievement) => (
            <div key={achievement.name || achievement} className="nt-mini-card"><strong>{achievement.name || achievement}</strong><p>{achievement.description || "—"}</p></div>
          )) : <p className="nt-empty-text">Достижений пока нет.</p>}
        </div>
      </Panel>
      <Panel title="Ремёсла">
        <div className="nt-card-list nt-column-list">
          {(info.activity?.craftingLevels || []).map((craft) => (
            <div key={craft.name} className="nt-mini-card"><strong>{craft.name}</strong><p>Уровень {craft.level}</p><span>{craft.exp}</span></div>
          ))}
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
    <main className="nt-profile" style={{ backgroundImage: `linear-gradient(rgba(5, 7, 7, .58), rgba(4, 4, 4, .76)), url(${background})` }}>
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
              <span>{label}</span>
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
