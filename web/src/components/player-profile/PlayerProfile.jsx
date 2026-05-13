import React, { useMemo, useState } from "react";
import { profileMockData } from "./profileMockData.js";

const TABS = [
  { id: "character", label: "Персонаж", icon: "♟" },
  { id: "inventory", label: "Инвентарь", icon: "▦" },
  { id: "skills", label: "Навыки", icon: "✦" },
  { id: "info", label: "Информация", icon: "◎" },
];

const INVENTORY_CATEGORIES = ["Всё", "Снаряжение", "Оружие", "Бижутерия", "Алхимия", "Ресурсы", "Прочее", "Особое"];

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
        {item.compare?.length ? (
          <div className="nt-modal-block">
            <h4>Сравнение</h4>
            <ul>{item.compare.map((line) => <li key={line}>{line}</li>)}</ul>
          </div>
        ) : null}
        {item.enchantments?.length ? (
          <div className="nt-modal-block">
            <h4>Зачарования</h4>
            <ul>{item.enchantments.map((line) => <li key={line}>{line}</li>)}</ul>
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

function EffectsBlock({ effects = [] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="nt-effects">
      <button className="nt-effects-toggle" onClick={() => setOpen((value) => !value)}>
        <span>Эффекты</span>
        <strong>{effects.length || "нет"}</strong>
      </button>
      {open ? (
        <div className="nt-effects-list">
          {effects.length ? effects.map((effect) => (
            <div key={effect.name || effect} className="nt-effect-row">
              <strong>{effect.name || effect}</strong>
              <span>{effect.description || effect.duration || "активен"}</span>
            </div>
          )) : <div className="nt-effect-row muted">На персонаже нет активных эффектов.</div>}
        </div>
      ) : null}
    </div>
  );
}

function CharacterTab({ profile, onOpenItem, onSpendAttributePoints }) {
  const [inputs, setInputs] = useState({});
  const freePoints = profile.player.freeAttributePoints || 0;
  const expMax = Math.max(1, profile.player.experienceToNext || 1);
  const expPercent = Math.min(100, Math.round(((profile.player.experienceCurrent || 0) / expMax) * 100));
  const raceModel = profile.assets?.raceModels?.[profile.player.raceKey];

  function spend(attributeKey) {
    const amount = Math.max(0, Math.floor(Number(inputs[attributeKey] || 0)));
    if (!amount) return;
    onSpendAttributePoints?.(attributeKey, amount);
    setInputs((current) => ({ ...current, [attributeKey]: "" }));
  }

  return (
    <div className="nt-tab-body nt-character-grid">
      <Panel title="Экипировка" className="nt-equipment-panel">
        <div className="nt-model-wrap">
          <div className={`nt-model-card race-${profile.player.raceKey || "human"}`}>
            {raceModel ? <img src={raceModel} alt={profile.player.raceName} /> : <div className="nt-model-placeholder">{profile.player.raceName}</div>}
          </div>
          <div className="nt-slots">
            {profile.equipmentSlots.map((slot) => {
              const item = profile.equipment?.[slot.key];
              const positionClass = slot.positionClass || `slot-${slot.key}`;
              return (
                <button
                  key={slot.key}
                  className={`nt-slot ${positionClass} ${item ? qualityClass(item.quality) : "empty"}`}
                  onClick={() => item && onOpenItem(item, slot.key)}
                  title={item?.name || slot.label}
                >
                  <span>{slot.icon}</span>
                  <small>{slot.label}</small>
                </button>
              );
            })}
          </div>
        </div>
      </Panel>

      <div className="nt-side-stack">
        <Panel title="Сводка" right={<span className="nt-badge">{profile.player.branch}</span>}>
          <div className="nt-summary nt-compact-grid">
            <div><span>Ник</span><strong>{profile.player.nickname}</strong></div>
            <div><span>Раса</span><strong>{profile.player.raceName}</strong></div>
            <div><span>Уровень</span><strong>{profile.player.level}</strong></div>
            <div><span>Баланс</span><strong>{profile.player.balanceText}</strong></div>
            <div><span>Характеристики</span><strong>{freePoints}</strong></div>
            <div><span>Навыки</span><strong>{profile.player.freeSkillPoints}</strong></div>
          </div>
          <div className="nt-progress-label">Опыт: {profile.player.experienceCurrent} / {profile.player.experienceToNext}</div>
          <div className="nt-progress"><i style={{ width: `${expPercent}%` }} /></div>
        </Panel>

        <Panel title="Характеристики" right={<span className="nt-badge">{freePoints}</span>}>
          <div className="nt-attributes">
            {profile.attributes.map((attribute) => (
              <div key={attribute.key} className="nt-attribute">
                <strong>{attribute.label}</strong>
                <span>{attribute.value}</span>
                {freePoints > 0 ? (
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
                ) : <em>—</em>}
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Параметры">
          <div className="nt-params nt-compact-grid">
            {profile.parameters.map((parameter) => <div key={parameter.label}><span>{parameter.label}</span><strong>{parameter.value}</strong></div>)}
          </div>
          <EffectsBlock effects={profile.effects || []} />
        </Panel>

        <Panel title="Активные сеты">
          {profile.activeSets?.length ? (
            <div className="nt-card-list compact">{profile.activeSets.map((set) => <div key={set.name} className="nt-mini-card"><strong>{set.name}</strong><p>{set.bonus}</p></div>)}</div>
          ) : <div className="nt-empty-line">Активных сетов нет.</div>}
        </Panel>
      </div>
    </div>
  );
}

function InventoryTab({ profile, onOpenItem }) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("Всё");
  const categories = useMemo(() => {
    const extra = profile.inventory
      .map((item) => item.category || "Прочее")
      .filter((item) => !INVENTORY_CATEGORIES.includes(item));
    return [...INVENTORY_CATEGORIES, ...new Set(extra)];
  }, [profile.inventory]);
  const items = profile.inventory.filter((item) => {
    const matchesCategory = category === "Всё" || item.category === category;
    const matchesQuery = item.name.toLowerCase().includes(query.toLowerCase());
    return matchesCategory && matchesQuery;
  });

  return (
    <div className="nt-tab-body nt-inventory-body">
      <Panel title="Инвентарь" className="nt-full-panel">
        <div className="nt-inventory-top">
          <input className="nt-search-input" placeholder="Поиск предмета" value={query} onChange={(event) => setQuery(event.target.value)} />
          <div className="nt-category-row">
            {categories.map((item) => (
              <button key={item} className={category === item ? "active" : ""} onClick={() => setCategory(item)}>{item}</button>
            ))}
          </div>
        </div>
        <div className="nt-items-grid">
          {items.map((item) => (
            <button key={item.id} className={`nt-item ${qualityClass(item.quality)}`} onClick={() => onOpenItem(item)}>
              <strong>{item.name}</strong>
              <span>{item.type} · ур. {item.level} · ×{item.amount || 1}</span>
              <em>{item.quality}</em>
            </button>
          ))}
          {!items.length ? <div className="nt-empty-line">Предметы не найдены.</div> : null}
        </div>
      </Panel>
    </div>
  );
}

function SkillsTab({ profile }) {
  return (
    <div className="nt-tab-body nt-two-columns">
      <Panel title="Активные навыки" className="nt-scroll-panel">
        <div className="nt-card-list">{(profile.skills?.active || []).map((skill) => <div key={skill.name} className="nt-mini-card"><strong>{skill.name}</strong><p>{skill.description}</p><span>ур. {skill.level}</span></div>)}</div>
      </Panel>
      <Panel title="Пассивные навыки" className="nt-scroll-panel">
        <div className="nt-card-list">{(profile.skills?.passive || []).map((skill) => <div key={skill.name} className="nt-mini-card"><strong>{skill.name}</strong><p>{skill.description}</p><span>ур. {skill.level}</span></div>)}</div>
      </Panel>
    </div>
  );
}

function InfoTab({ profile }) {
  const info = profile.information || {};
  return (
    <div className="nt-tab-body nt-two-columns nt-info-grid">
      <Panel title="Достижения" className="nt-scroll-panel">
        <div className="nt-card-list">{(info.achievements || []).map((achievement) => <div key={achievement.name || achievement} className="nt-mini-card"><strong>{achievement.name || achievement}</strong><p>{achievement.description || "—"}</p></div>)}</div>
      </Panel>
      <Panel title="Активность" className="nt-scroll-panel">
        <div className="nt-params nt-compact-grid">
          <div><span>PVE</span><strong>{info.activity?.pveKills || 0}</strong></div>
          <div><span>PVP</span><strong>{info.activity?.pvpKills || 0}</strong></div>
          <div><span>Души</span><strong>{info.activity?.soulParticlesAbsorbed || 0}</strong></div>
          <div><span>Регистрация</span><strong>{profile.player.registrationDate}</strong></div>
        </div>
      </Panel>
      <Panel title="Ремёсла" className="nt-scroll-panel nt-info-wide">
        <div className="nt-card-list compact">{(info.activity?.craftingLevels || []).map((craft) => <div key={craft.name} className="nt-mini-card"><strong>{craft.name}</strong><p>Уровень {craft.level}</p><span>{craft.exp}</span></div>)}</div>
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
    <main className="nt-profile" style={{ backgroundImage: `linear-gradient(rgba(5, 7, 7, .66), rgba(3, 3, 3, .88)), url(${background})` }}>
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
            </button>
          ))}
        </nav>

        {tab === "character" ? <CharacterTab profile={profile} onOpenItem={openItem} onSpendAttributePoints={onSpendAttributePoints} /> : null}
        {tab === "inventory" ? <InventoryTab profile={profile} onOpenItem={openItem} /> : null}
        {tab === "skills" ? <SkillsTab profile={profile} /> : null}
        {tab === "info" ? <InfoTab profile={profile} /> : null}
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
