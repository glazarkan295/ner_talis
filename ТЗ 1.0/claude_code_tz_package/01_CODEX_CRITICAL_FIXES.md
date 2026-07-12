# 01. Срочные правки Codex

Этот файл нужно выполнить до крупных новых функций админ-панели.

## Правила исправления

- Если награда/посылка/списание уже сохранены, ошибка уведомления не должна делать действие повторяемым.
- Операции передачи предметов/монет должны быть атомарными или идемпотентными.
- Outbox нельзя очищать до успешной отправки сообщения.
- Published-контент нельзя убирать из игры простым редактированием draft.
- Read-only/admin-view права не должны выдавать edit-token.
- Ошибочные параметры dangerous endpoint не должны запускать импорт всего проекта.

## Безопасность / права / админ-токены

### [P1] Reject cross-kind site edits
- Источник: `https://github.com/glazarkan295/ner_talis/blob/f7fdfad6e6b3590e5d58510e26d4d14e59dbf176/ner_talis_game_project/admin_site_api.py#L203-L206`
- Суть: When content_id belongs to a different site kind, this update path still loads it by global ID and then overwrites _kind from the URL. For example, a content editor with news.edit but without site.homepage_edit can PUT /api/admin/v2/site/news/{page_id} and convert/overwrite a page, bypassing the per-kind RBAC model and corrupting the registry. Check the stored data._kind matches kind before update/status actions. ℹ️ About Codex in GitHub Your team has set up Codex to review pull requests in this repo. Reviews are triggered when you Open a pull request for review Mark a draft as ready Comment "@codex review". If Codex has suggestions, it will comment; otherwise it will react with 👍. Codex can also answer questions or update the PR. Try commenting "@codex address that feedback".
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P1] Require edit rights before minting profile edit tokens
- Источник: `https://github.com/glazarkan295/ner_talis/blob/22bef1adbe10a8cc16276b0ccdad4da6d906758e/ner_talis_game_project/admin_panel_v2_api.py#L393`
- Суть: With this check, any role that only has players.view (including read_only) can create an admin profile-view token; get_admin_player_view_profile then always returns an admin_profile_edit token, and the profile API accepts that scope for write endpoints. In practice a read-only admin can drop items, change names, spend points, or send courier transfers from the player profile, so this endpoint needs a mutation/edit permission before issuing an editable view.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P2] Apply published profile blocks
- Источник: `In web/src/components/player-profile/PlayerProfile.jsx:`
- Суть: The profile-layout constructor now lets admins publish profile_block records with block type, order, width and visibility, and the backend sends those blocks in profileLayout, but the runtime only applies tab metadata here and then renders the hard-coded CharacterTab/InventoryTab/etc. If an admin hides or reorders a block such as inventory/resources/fines, players still see the default profile, making the published block layout ineffective.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P2] Block clearing your own owner override
- Источник: `https://github.com/glazarkan295/ner_talis/blob/22bef1adbe10a8cc16276b0ccdad4da6d906758e/ner_talis_game_project/admin_panel_v2_api.py#L265`
- Суть: If an admin’s owner role comes from a role override rather than the ENV bootstrap, calling this delete endpoint on their own identity removes the only owner grant and immediately resolves them to read_only. The assign path has an explicit self-demotion guard, but this clear-override path skips it, so an override-only owner can lock themselves out of role management.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P2] Do not fail after saving admin rewards
- Источник: `In ner_talis_game_project/services/admin_panel_service.py:`
- Суть: If the new outbox enqueue raises after line 711 has already persisted the delivered rewards, the API returns an error even though the player now owns the items/coins. An admin retry in that scenario grants the same reward again, so notification failures should not make the already-committed delivery look retryable, or the reward and outbox write need to be committed atomically.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P2] Do not overwrite the admin's profile session token
- Суть: Opening an editable admin profile stores the target player's edit token in the same ner_talis_profile_session_token slot used by a normal player profile session. If an admin who also has their own profile open later visits /profile or performs profile actions in the same browser session, requests authenticate as the viewed player instead of the admin's own character; keep this edit token in a separate key or pass it only for the admin-view requests.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P2] Do not trust spoofed HTTPS proxy headers
- Источник: `https://github.com/glazarkan295/ner_talis/blob/22bef1adbe10a8cc16276b0ccdad4da6d906758e/ner_talis_game_project/web_app.py#L255-L256`
- Суть: When FORCE_HTTPS=true, a direct HTTP client can set X-Forwarded-Proto: https and bypass the HTTPS requirement because this header is trusted unconditionally. The code already treats proxy headers as spoofable for rate-limit IPs unless TRUST_PROXY_HEADERS and trusted proxies are configured; the same trust gate is needed here or forced HTTPS is ineffective on any deployment where the app is reachable directly.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P2] Keep achievement edits out of live definitions
- Источник: `https://github.com/glazarkan295/ner_talis/blob/22bef1adbe10a8cc16276b0ccdad4da6d906758e/ner_talis_game_project/admin_achievement_api.py#L195`
- Суть: This update writes into the existing achievement envelope regardless of its status after only requiring achievement.edit. The content role has that edit permission but not achievement.publish, and the runtime engine reads published definitions directly, so editing an already published achievement changes live conditions/rewards immediately without validation or publish rights. Published achievements should require a publish-level permission or be copied/demoted to a draft before mutation.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P2] Keep admin edit tokens out of the player session
- Суть: This stores the target player's ADMIN_PROFILE_EDIT_SCOPE token in the normal profile session storage. If the admin then navigates this same tab to /profile, the regular profile app reuses that remembered token and opens the target player's profile without adminView/adminEdit flags, exposing normal-player actions like courier/send until the admin edit token expires. Keep this token local to AdminProfileView instead of registering it as the active player profile session.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P2] Keep published world content live while editing
- Источник: `https://github.com/glazarkan295/ner_talis/blob/22bef1adbe10a8cc16276b0ccdad4da6d906758e/ner_talis_game_project/services/world_content_registry.py#L377-L378`
- Суть: When an admin edits an already published world object through PUT /api/admin/v2/world/{kind}/{id}, the route only requires world.edit_draft, but this mutates the same envelope from published to draft. Runtime code reads only published content, so a harmless edit to a live location, mob, button, or spawn immediately removes it from the game until someone with publish rights validates and republishes it. If this is meant to be a draft edit, it needs a separate draft/version instead of changing the live object’s status.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P2] Preserve legacy dict-backed effects
- Источник: `https://github.com/glazarkan295/ner_talis/blob/22bef1adbe10a8cc16276b0ccdad4da6d906758e/ner_talis_game_project/services/small_plateau_service.py#L121-L123`
- Суть: For players/tests that still store effects as key-presence flags in the legacy effects dict (for example {"ancient_curse": true}), this now returns false because only dict-valued entries are accepted. The module explicitly supports the dict representation and the previous behavior treated key presence as active, so those players lose curse/amulet behavior unless the fallback also accepts non-dict truthy values.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P2] Show no-results only for an empty filtered list
- Источник: `In web/src/components/admin-shell/SearchFilter.jsx:`
- Суть: As written, any non-empty search query renders the “Ничего не найдено” message, and the added section callers render NoResults before mapping filterEntities(...), so a successful search still displays the empty-state message above the matching rows. Gate this on the filtered list length instead of only on query.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P2] Use constructor mob rewards in live battles
- Источник: `https://github.com/glazarkan295/ner_talis/blob/22bef1adbe10a8cc16276b0ccdad4da6d906758e/ner_talis_game_project/services/pve_battle_service.py#L1526`
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P2] Verify site item kind before updating
- Источник: `https://github.com/glazarkan295/ner_talis/blob/22bef1adbe10a8cc16276b0ccdad4da6d906758e/ner_talis_game_project/admin_site_api.py#L175`
- Суть: Site content kinds share one EntityStore, but this update path never checks that the stored item’s data._kind matches the {kind} in the URL. A request such as PUT /api/admin/v2/site/faq/{news_id} will pass FAQ permissions and then overwrite the item with _kind: "faq", so a wrong or crafted URL can corrupt/move content between sections and apply the wrong permission family.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

## Город / кнопки / переходы

### [P2] Scope live-city button labels by node
- Источник: `In ner_talis_game_project/services/city_runtime.py:`
- Суть: With CITY_CONSTRUCTOR_LIVE enabled, button presses are resolved from one global map keyed only by the rendered label. If two published nodes both have common labels such as “Назад” or “Войти” but different target_node_id values, setdefault keeps whichever button was indexed first, so pressing the same label in the second node jumps to the wrong target because the current node is not considered. Store/use the player's current node or key transitions by (node_id, label).
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

## Достижения

### [P2] Model curse achievement on ancient-curse days
- Суть: small_plateau_service.register_ancient_curse_active_day grants curse_what_curse after the ancient curse has more than 60 active days with 30+ minutes of activity, but this imported definition waits for a finish_event targeting pvp_death_curse, which current code does not record for that unlock. The published constructor definition will therefore show/auto-evaluate the wrong condition; represent the ancient-curse activity requirement instead.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

## Импорт / draft-publish / live content

### [P1] Re-publish world records after update-mode import
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P1] Reject invalid import kinds instead of importing everything
- Суть: When /run receives only unknown kind values (for example a typo or stale client), this filters them to an empty list and then or None makes ci.import_all execute every importer. Because this endpoint is dangerous and publishes content, a bad subset request can unexpectedly import all items, mobs, effects, skills, locations, events, and city nodes; return a 400 or preserve the empty selection instead of falling back to all kinds.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P2] Do not publish locations with empty descriptions
- Источник: `In ner_talis_game_project/services/constructor_import.py:`
- Суть: The default location import includes seldar_city.json, which has no short_description, description, entry_text, or lore_description, so this mapping creates the published seldar world location with both description fields empty. The world constructor validator requires at least one description, so a full import seeds invalid published content that check_import does not report; skip it with a needs-check error or derive a real description before publishing.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P2] Honor copy mode for legacy importers
- Источник: `In ner_talis_game_project/services/constructor_import.py:`
- Суть: The unified import endpoint exposes copy for every kind and import_all passes mode into these importers, but this line collapses the mode to a boolean overwrite flag; for item/mob/effect/skill, copy is therefore treated like new and existing records are skipped instead of copied. Either implement copy semantics for these importers or reject copy for these kinds so admins do not get a misleading successful copy run.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P2] Include small-plateau search events in event import
- Суть: This loop imports events only from hilly_meadows.json and ordinary_forest.json, but the repo also has the active small plateau event table in data/small_plateau_search_events.json (loaded by small_plateau_service.get_search_events_data() and referenced by data/small_plateau_location.json via finish_event_table). Importing locations/events therefore leaves that location's 28 existing search events invisible in the event constructor; add a reader for the list-shaped table or report it as unsupported instead of silently omitting it.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P2] Keep world import from importing non-world constructors
- Источник: `In ner_talis_game_project/services/constructor_import.py:`
- Суть: The legacy /api/admin/v2/world/import endpoint still calls import_all(payload.kinds or None), so after these new default importers were added an empty-kind world import now also publishes city nodes, achievements, and fine definitions under the world.import_existing action. That broadens the existing world-import endpoint unexpectedly; keep its default limited to world kinds or require admins to use the new unified /import/run route for cross-constructor imports.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P2] Preserve source event metadata during import
- Источник: `In ner_talis_game_project/services/constructor_import.py:`
- Суть: For the included hilly-meadows and ordinary-forest tables, the source JSON already carries event details such as event_texts, and runtime treats forest_trap as a trap, but the importer hard-codes a placeholder text and defaults unmapped event names to found_resource. Imported events therefore lose available player-facing descriptions and can be misclassified if published from the constructor; read the source metadata here instead of creating placeholders/default types.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P2] Preserve the source rarity for imported achievements
- Суть: For curse_what_curse, the live source in data/small_plateau_mechanics.json marks the achievement as legendary (and small_plateau_service.add_achievement copies that source dict into player state), but the importer publishes the constructor definition as epic. This makes the admin constructor disagree with the existing runtime achievement after import; use the source rarity when present or correct this seed value.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P2] Rewrite references when copying linked imports
- Суть: When copy mode is used for records that contain references, this creates a new envelope id but leaves the payload pointing at the original objects; for example copied search events still have location: hilly_meadows, and copied Seldar zone nodes still have parent_id: seldar. The copied set is therefore attached to the originals instead of forming an independent copy, so rewrite linked ids for copy mode or skip copying linked records.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P2] Validate effect seeds before publishing
- Источник: `In ner_talis_game_project/services/constructor_import.py:`
- Суть: When an admin runs the effect import, the seed records are immediately forced to published even though the data just created above omits fields that effect_constructor_service.validate() requires, such as player_text for show_to_player=True and type-specific fields like stat/control_kind. This leaves the constructor with published effects that the normal publish endpoint would reject, and any later runtime that consumes published effect definitions will receive incomplete records.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

## Курьер / передача предметов / деньги / инвентарь

### [P1] Avoid requeuing after a committed delivery
- Источник: `In ner_talis_game_project/services/courier_service.py:`
- Суть: If queuing the bot notification fails after update_player(receiver) has already committed (for example a transient outbox DB/file error), the broad except below requeues the same transfer and the next courier tick will run _deliver_items_to again, duplicating the items/coins for the recipient. Requeue only failures that happen before the recipient mutation commits, or make the delivery step idempotent.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P1] Do not requeue after committing recipient rewards
- Источник: `In ner_talis_game_project/services/courier_service.py:`
- Суть: If update_player(receiver) succeeds but _notify raises (for example due to a transient outbox/storage failure), the broad except below requeues the same transfer even though the items/coins were already saved to the receiver. The next worker attempt will deliver the parcel again, duplicating contents; notification failures after a committed delivery need a separate path that does not reapply rewards.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P1] Do not retry courier transfers after saving rewards
- Источник: `In ner_talis_game_project/services/courier_service.py:`
- Суть: If enqueue_bot_messages raises after update_player(receiver) succeeds (for example, a transient DB/outbox failure), the broad except below requeues the same transfer even though the recipient already received the items/coins. The next courier tick will deliver the parcel again, duplicating the contents; once the reward save succeeds, notification failures need to be handled without retrying the delivery itself.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P1] Handle recipient inventory overflow during delivery
- Суть: When the recipient's regular and overflow inventory slots are full, add_inventory_item can return with discarded > 0, but this result is ignored and the receiver notification still lists the original parcel contents. In that full-inventory scenario the sender already lost the items at send time, while delivery silently discards some or all of them; check the add result and requeue/refund or report the actual partial delivery.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P1] Make courier sends atomically debit the sender
- Суть: When the same sender submits two courier sends concurrently (for example a double-click or two profile tabs), both requests can validate against the same pre-debit inventory and money, then both append transfers; this update_player(sender) call only writes each stale post-debit snapshot, so the sender is effectively charged once while two packages are queued for delivery. The debit and queue insertion need to be protected by a per-sender atomic claim/lock or conditional update.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P1] Update courier balances in both money fields
- Суть: When a player already has money_copper (set by market, fine, promo, or admin flows), this deducts only money, while the rest of the economy reads money_copper first (for example market_service._money). Sending coins or paying the courier then leaves the authoritative balance unchanged, so the sender can still spend the old amount elsewhere; the same helper should update money and money_copper together for courier debits/credits.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P2] Do not drop misdelivered parcels without a recipient
- Источник: `In ner_talis_game_project/services/courier_service.py:`
- Суть: If the 0.1% misdelivery branch triggers when there is no eligible third player (for example only the sender and intended receiver exist, or every other player is dead), _pick_random_recipient returns None but the transfer is still counted as processed and the sender is told it was delivered to someone else. In that scenario no recipient receives the items/coins and the parcel is not requeued, so the contents are silently lost outside the intended stolen outcome.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P2] Do not resave after queuing a courier transfer
- Суть: create_courier_transfer has already persisted the sender debit and queued the transfer before this extra save runs. If this second save_player fails, the endpoint returns an error after the durable side effects are committed, so a client retry creates another paid/queued parcel instead of just reporting the already-created transfer. Remove the redundant save or make the queued transfer and final save atomic.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P2] Handle full recipient inventories before clearing packages
- Суть: When the recipient's regular and overflow inventory are full, add_inventory_item can return a partial/zero add with discarded items, but this result is ignored here; the transfer is still removed from the queue and the notification lists the original contents. In that full-inventory case the sender loses the attachments while the recipient receives fewer items or none, so the courier should requeue/return/record undelivered items instead of silently discarding them.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P2] Keep courier coin transfers in both balance fields
- Суть: When a courier delivers coins to a player that already has a money_copper field, this updates only money, while market/admin code reads money_copper first. In that case the recipient sees or receives coins via the courier but still cannot spend them in the NPC market until some later path resynchronizes the fields; the courier debit/credit paths should update money_copper and money together.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P2] Preserve parcels when no misdelivery target exists
- Источник: `https://github.com/glazarkan295/ner_talis/blob/22bef1adbe10a8cc16276b0ccdad4da6d906758e/ner_talis_game_project/services/courier_service.py#L562`
- Суть: When the random misdelivery branch is selected but _pick_random_recipient returns None (for example, only the sender and receiver exist, or all other players are dead), this if skips delivery, still notifies the sender, increments processed, and the transfer was already removed from the queue. That permanently loses the items/coins; fall back to normal delivery, refund, or requeue when there is no wrong recipient.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P2] Reject bound or protected items before courier transfer
- Суть: When the requested inventory stack is a bound/protected/quest item, this path only checks that the stack exists and has enough quantity, so the website API can courier items that the rest of the inventory rules keep out of player trading (for example starter gear with bound_on_receive or quest/protected stacks). Add the same transferability guard here before snapshotting and removing the item.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P2] Reject non-tradable stacks before courier transfer
- Суть: When the selected stack is starter/bound gear (bound_on_receive or can_trade: false) or a protected/quest/locked stack, this validation still accepts it and removes it for delivery. The repo already uses those flags to keep protected stacks separate and to block player trading, so courier transfers let players give away items that should not leave their account; reject those flags before adding the stack to planned.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P2] Split tool durability when couriering part of a stack
- Суть: When a player sends only part of a stackable gathering tool stack that has already been used, this subtraction leaves the sender's reduced stack with the same tool_uses_left while the package snapshot carries that same counter to the receiver. For example, splitting 1 rod from a stack of 3 with 5 uses left makes both stacks partially used and reduces the total remaining uses, so partial courier sends need to split/reset the durability counter consistently.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

## Очередь сообщений / outbox / доставка уведомлений

### [P2] Keep outbox messages until bot sends succeed
- Источник: `In ner_talis_game_project/handlers/city.py:`
- Суть: This dequeues and clears durable bot messages before any Telegram sends happen; the VK registration handler follows the same pattern. If the bot API fails, rate-limits, or the process dies during the subsequent send loop, courier/admin-gift/broadcast messages have already been removed from storage and will never be retried. Peek the outbox and acknowledge after successful sends, or re-enqueue messages on send failure.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P2] Preserve outbox messages until they are sent
- Источник: `In ner_talis_game_project/handlers/city.py:`
- Суть: This clears the durable outbox before any Telegram messages are sent, so if reply_text fails or the process crashes while sending a courier/admin/broadcast notification, the message has already been removed and will never be retried. The same pre-send dequeue pattern is used in the VK handler; read the pending messages but only acknowledge/clear them after successful sends, or re-enqueue failures.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P2] Read SQLite outbox after acquiring the write lock
- Источник: `In ner_talis_game_project/storage/sqlite_storage.py:`
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P2] Read the SQLite outbox after acquiring the write lock
- Источник: `In ner_talis_game_project/storage/sqlite_storage.py:`
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P2] Restrict queue claims to registered platforms
- Источник: `https://github.com/glazarkan295/ner_talis/blob/22bef1adbe10a8cc16276b0ccdad4da6d906758e/ner_talis_game_project/services/bot_message_queue.py#L416`
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P2] Take the SQLite write lock before reading outbox
- Источник: `In ner_talis_game_project/storage/sqlite_storage.py:`
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

## Прочее

### [P2] Model Seeker as 1000 plateau searches
- Суть: The source mechanics and small_plateau_service.apply_search_milestone grant seeker only at the 1000th Small Plateau search, but this imported published definition is satisfied by a single discover_location progress event. If the constructor definition is used by the achievement engine or by admins to reason about progress, it unlocks seeker-only content far earlier than the current runtime rule; import the search-count requirement instead.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

### [P2] Traverse nested data when building search text
- Суть: When constructor records keep searchable values inside arrays or objects, this loop drops them because push ignores non-string/non-number values. For example imported recipes store ingredient item IDs under data.ingredients[].item_id, and achievements/events use nested conditions, rewards, or special_loot, so searching for those linked IDs will never match even though the feature is described as searching all data values. Recursively collect nested primitive values before filtering.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

## Публичный сайт / site content

### [P2] Honor non-public site visibility
- Источник: `In ner_talis_game_project/services/site_content_registry.py:`
- Суть: When admins publish content with visibility: "hidden" or "authorized", the public API still returns it because this filter only checks lifecycle status and kind. The admin UI exposes visibility for pages/lore, so hidden or member-only material becomes publicly enumerable/readable as soon as it is published; skip non-public records here and apply the same rule in published_page() before returning _public_view.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

## Рынок / портовый рынок

### [P2] Revalidate port rotations when claiming stock
- Источник: `In ner_talis_game_project/services/market_service.py:`
- Суть: If a player opens a port-market item before the rotation expires but submits the quantity after expires_at, this claim path reads the raw state file and reserves stock without checking expiry or regenerating the rotation. That lets expired rotation items remain purchasable until some other action calls port_market_rotation; validate expires_at under the same lock before decrementing stock.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.

## Штрафы

### [P2] Preserve legacy active fines during repair
- Суть: For players still stored in the legacy shape with only an active active_fine and no active_fines list, this sync step sees an empty list and removes the valid legacy fine before active_fines() can migrate it. Using the new “Проверить штрафы” action on such a player silently clears their debt/restriction and even reports fixed: false, so migrate active legacy fines into the list before syncing or dropping only terminal aliases.
- Требование: исправить причину, добавить защиту от повторов/потерь/обхода прав и тест на регрессию.
