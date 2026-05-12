import React, { useMemo, useState } from "react";
import { profileMockData } from "./profileMockData.js";

const TABS = [
  ["character", "Персонаж"],
  ["inventory", "Инвентарь"],
  ["skills", "Навыки"],
  ["info", "Информация"],
];

function qualityClass(quality = "обычный") {
  return `quality-${String(quality).toLowerCase().replace(/\s+/g, "-")}`;
}

function Panel({ title, children, right }) {
  return (
    <section className="nt-panel">
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
  const raceModel = profile.assets?.raceModels?.[profile.player.raceKey];

  function spend(attributeKey) {
    const amount = Math.max(0, Math.floor(Number(inputs[attributeKey] || 0)));
    if (!amount) return;
    onSpendAttributePoints?.(attributeKey, amount);
    setInputs((current) => ({ ...current, [attributeKey]: "" }));
  }

  return (
    <div className="nt-character-grid">
      <Panel title="Персонаж и экипировка">
        <div className="nt-model-wrap">
          <div className="nt-model-card">
            {raceModel ? <img src={raceModel} alt={profile.player.raceName} /> : <div className="nt-model-placeholder">{profile.player.raceName}</div>}
          </div>
          <div className="nt-slots">
            {profile.equipmentSlots.map((slot) => {
              const item = profile.equipment?.[slot.key];
              return (
                <button
                  key={slot.key}
                  className={`nt-slot ${item ? qualityClass(item.quality) : "empty"}`}
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
          <div className="nt-summary">
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

        <Panel title="Характеристики" right={<span className="nt-badge">{freePoints} свободно</span>}>
          <div className="nt-attributes">
            {profile.attributes.map((attribute) => (
              <div key={attribute.key} className="nt-attribute">
                <div>
                  <strong>{attribute.label}: {attribute.value}</strong>
                  <p>{attribute.description}</p>
                </div>
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
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Параметры">
          <div className="nt-params">
            {profile.parameters.map((parameter) => <div key={parameter.label}><span>{parameter.label}</span><strong>{parameter.value}</strong></div>)}
          </div>
        </Panel>

        {profile.activeSets?.length ? (
          <Panel title="Активные сеты">
            <div className="nt-card-list">{profile.activeSets.map((set) => <div key={set.name} className="nt-mini-card"><strong>{set.name}</strong><p>{set.bonus}</p></div>)}</div>
          </Panel>
        ) : null}
      </div>
    </div>
  );
}

function InventoryTab({ profile, onOpenItem }) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("Всё");
  const categories = useMemo(() => ["Всё", ...new Set(profile.inventory.map((item) => item.category || "Прочее"))], [profile.inventory]);
  const items = profile.inventory.filter((item) => {
    const matchesCategory = category === "Всё" || item.category === category;
    const matchesQuery = item.name.toLowerCase().includes(query.toLowerCase());
    return matchesCategory && matchesQuery;
  });

  return (
    <Panel title="Инвентарь">
      <div className="nt-toolbar">
        <input placeholder="Поиск предмета" value={query} onChange={(event) => setQuery(event.target.value)} />
        <select value={category} onChange={(event) => setCategory(event.target.value)}>{categories.map((item) => <option key={item}>{item}</option>)}</select>
      </div>
      <div className="nt-items-grid">
        {items.map((item) => (
          <button key={item.id} className={`nt-item ${qualityClass(item.quality)}`} onClick={() => onOpenItem(item)}>
            <strong>{item.name}</strong>
            <span>{item.type} · ур. {item.level} · ×{item.amount || 1}</span>
            <em>{item.quality}</em>
          </button>
        ))}
      </div>
    </Panel>
  );
}

function SkillsTab({ profile }) {
  return (
    <div className="nt-two-columns">
      <Panel title="Активные навыки">
        <div className="nt-card-list">{(profile.skills?.active || []).map((skill) => <div key={skill.name} className="nt-mini-card"><strong>{skill.name}</strong><p>{skill.description}</p><span>ур. {skill.level}</span></div>)}</div>
      </Panel>
      <Panel title="Пассивные навыки">
        <div className="nt-card-list">{(profile.skills?.passive || []).map((skill) => <div key={skill.name} className="nt-mini-card"><strong>{skill.name}</strong><p>{skill.description}</p><span>ур. {skill.level}</span></div>)}</div>
      </Panel>
    </div>
  );
}

function InfoTab({ profile }) {
  const info = profile.information || {};
  return (
    <div className="nt-two-columns">
      <Panel title="Достижения">
        <div className="nt-card-list">{(info.achievements || []).map((achievement) => <div key={achievement.name || achievement} className="nt-mini-card"><strong>{achievement.name || achievement}</strong><p>{achievement.description || "—"}</p></div>)}</div>
      </Panel>
      <Panel title="Активность">
        <div className="nt-params">
          <div><span>PVE убийства</span><strong>{info.activity?.pveKills || 0}</strong></div>
          <div><span>PVP убийства</span><strong>{info.activity?.pvpKills || 0}</strong></div>
          <div><span>Частицы душ</span><strong>{info.activity?.soulParticlesAbsorbed || 0}</strong></div>
          <div><span>Дата регистрации</span><strong>{profile.player.registrationDate}</strong></div>
        </div>
      </Panel>
      <Panel title="Ремёсла">
        <div className="nt-card-list">{(info.activity?.craftingLevels || []).map((craft) => <div key={craft.name} className="nt-mini-card"><strong>{craft.name}</strong><p>Уровень {craft.level}</p><span>{craft.exp}</span></div>)}</div>
      </Panel>
    </div>
  );
}

export function PlayerProfile({ profile = profileMockData, onSpendAttributePoints, onEquipItem, onUnequipItem, onUseItem }) {
  const [tab, setTab] = useState("character");
  const [modal, setModal] = useState(null);
  const background = profile.assets?.background || "";

  function openItem(item, slotKey = null) {
    setModal({ item, slotKey });
  }

  return (
    <main className="nt-profile" style={background ? { backgroundImage: `linear-gradient(rgba(4,3,2,.72), rgba(4,3,2,.9)), url(${background})` } : undefined}>
      <div className="nt-shell">
        <header className="nt-top">
          <div>
            <span className="nt-kicker">Мир Нер-Талис</span>
            <h1>Профиль персонажа</h1>
          </div>
          <div className="nt-id">ID: {profile.player.userGlobalId}</div>
        </header>

        <nav className="nt-tabs">
          {TABS.map(([id, label]) => <button key={id} className={tab === id ? "active" : ""} onClick={() => setTab(id)}>{label}</button>)}
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
