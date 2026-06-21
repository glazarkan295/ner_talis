import React, { useCallback, useEffect, useState } from "react";
import { assignRole, clearRole, fetchRoles } from "../../../api/adminV2Api.js";
import { ConfirmModal } from "../ConfirmModal.jsx";

export function RolesSection({ guarded }) {
  const [data, setData] = useState(null);
  const [platform, setPlatform] = useState("telegram");
  const [adminUserId, setAdminUserId] = useState("");
  const [role, setRole] = useState("read_only");
  const [confirm, setConfirm] = useState(null); // {type, ...}

  const load = useCallback(async () => {
    const payload = await guarded(() => fetchRoles());
    if (payload) setData(payload);
  }, [guarded]);

  useEffect(() => { load(); }, [load]);

  const roles = data?.roles || [];
  const matrix = data?.matrix || {};
  const overrides = data?.overrides || [];

  function roleLabel(key) {
    return roles.find((r) => r.role === key)?.label || key;
  }

  function askAssign() {
    if (!adminUserId.trim()) return;
    setConfirm({
      type: "assign",
      platform,
      adminUserId: adminUserId.trim(),
      role,
    });
  }

  async function doConfirm(reason) {
    const c = confirm;
    if (!c) return;
    if (c.type === "assign") {
      await guarded(() => assignRole(c.platform, c.adminUserId, c.role, reason), "Роль назначена.");
    } else if (c.type === "clear") {
      await guarded(() => clearRole(c.platform, c.adminUserId), "Override роли снят.");
    }
    setConfirm(null);
    setAdminUserId("");
    await load();
  }

  if (!data) return <section className="ntv2-section"><h2>Роли и доступ</h2><p className="ntv2-hint">Загрузка…</p></section>;

  return (
    <section className="ntv2-section">
      <h2>Роли и доступ</h2>

      <div className="ntv2-panel">
        <h3>Назначить роль</h3>
        <div className="ntv2-form-row">
          <select value={platform} onChange={(e) => setPlatform(e.target.value)}>
            <option value="telegram">telegram</option>
            <option value="vk">vk</option>
          </select>
          <input placeholder="ID администратора" value={adminUserId} onChange={(e) => setAdminUserId(e.target.value)} />
          <select value={role} onChange={(e) => setRole(e.target.value)}>
            {roles.map((r) => <option key={r.role} value={r.role}>{r.label}</option>)}
          </select>
          <button type="button" className="ntv2-btn ntv2-btn-primary" disabled={!adminUserId.trim()} onClick={askAssign}>Назначить</button>
        </div>
        <p className="ntv2-hint">Назначение роли — действие с подтверждением и причиной (записывается в аудит).</p>
      </div>

      <div className="ntv2-panel">
        <h3>Переопределения ролей ({overrides.length})</h3>
        {!overrides.length ? <p className="ntv2-hint">Нет переопределений — все админы используют роль по умолчанию (ENV-bootstrap → owner).</p> : null}
        <div className="ntv2-list">
          {overrides.map((o) => (
            <div className="ntv2-list-row" key={o.key}>
              <span className="ntv2-mono">{o.key}</span>
              <span className="ntv2-badge">{roleLabel(o.role)}</span>
              <button
                type="button"
                className="ntv2-btn ntv2-btn-danger"
                onClick={() => {
                  const [plat, uid] = o.key.split(":");
                  setConfirm({ type: "clear", platform: plat, adminUserId: uid, role: o.role });
                }}
              >Снять override</button>
            </div>
          ))}
        </div>
      </div>

      <div className="ntv2-panel">
        <h3>Матрица прав</h3>
        <div className="ntv2-matrix">
          {roles.map((r) => (
            <details className="ntv2-tech" key={r.role}>
              <summary>{r.label} — {(matrix[r.role] || []).includes("*") ? "все права" : `${(matrix[r.role] || []).length} прав`}</summary>
              <div className="ntv2-perm-grid">
                {(matrix[r.role] || []).map((perm) => <span key={perm} className="ntv2-perm-chip">{perm}</span>)}
              </div>
            </details>
          ))}
        </div>
      </div>

      <ConfirmModal
        open={Boolean(confirm)}
        dangerous
        title={confirm?.type === "clear" ? "Снять переопределение роли?" : "Назначить роль?"}
        body={
          confirm?.type === "clear" ? (
            <p>Снять override для <b>{confirm?.platform}:{confirm?.adminUserId}</b>. Роль вернётся к значению по умолчанию.</p>
          ) : (
            <p>Назначить роль <b>{roleLabel(confirm?.role)}</b> для <b>{confirm?.platform}:{confirm?.adminUserId}</b>.</p>
          )
        }
        confirmLabel={confirm?.type === "clear" ? "Снять" : "Назначить"}
        onConfirm={doConfirm}
        onCancel={() => setConfirm(null)}
      />
    </section>
  );
}
