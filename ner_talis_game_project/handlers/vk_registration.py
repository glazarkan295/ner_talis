from dataclasses import dataclass
import logging

import vk_api
from vk_api.bot_longpoll import VkBotEventType, VkBotLongPoll
from vk_api.utils import get_random_id

from keyboards.vk_keyboards import (
    after_registration_keyboard,
    consent_keyboard,
    gender_confirm_keyboard,
    gender_keyboard,
    make_keyboard,
    name_confirm_keyboard,
    race_card_keyboard,
    race_confirm_keyboard,
    race_keyboard,
    start_keyboard,
)
from services.city_service import CITY_BUTTONS, process_world_action
from services.chat_log_service import append_player_chat_log, pop_pending_bot_messages
from services.promo_service import redeem_promo_code
from services.external_location_service import complete_active_timer
from services.runtime_timer_scheduler import attach_timer_notification, schedule_timer_delivery
from services.registration_service import (
    CONSENT_BUTTON,
    consent_message,
    create_player,
    format_race_card,
    get_race_id_by_name,
    load_races,
    validate_name,
)
from storage.base import PlayerStorage
from storage.storage_factory import create_storage

from services.web_profile import create_profile_site_link
from texts.registration_texts import (
    ASK_GENDER_TEXT,
    ASK_NAME_AGAIN_TEXT,
    ASK_NAME_TEXT,
    ASK_RACE_TEXT,
    FINAL_REGISTRATION_TEXT,
    GENDER_WARNING_TEXT,
    NAME_CONFIRM_TEXT_TEMPLATE,
    WORLD_SHORT_TEXT,
)

STATE_CONSENT = "consent"
STATE_START_MENU = "start_menu"
STATE_AWAITING_NAME = "awaiting_name"
STATE_NAME_CONFIRM = "name_confirm"
STATE_AWAITING_GENDER = "awaiting_gender"
STATE_GENDER_CONFIRM = "gender_confirm"
STATE_AWAITING_RACE = "awaiting_race"
STATE_RACE_CARD = "race_card"
STATE_RACE_CONFIRM = "race_confirm"
VK_PLATFORM = "vk"
logger = logging.getLogger(__name__)


@dataclass
class VkRegistrationSession:
    state: str = STATE_CONSENT
    name: str | None = None
    pending_name: str | None = None
    gender_id: str | None = None
    gender_label: str | None = None
    pending_gender_id: str | None = None
    pending_gender_label: str | None = None
    race_id: str | None = None


class VkRegistrationBot:
    def __init__(
        self,
        token: str,
        group_id: int,
        storage_path: str | None = None,
        storage: PlayerStorage | None = None,
    ):
        self.vk_session = vk_api.VkApi(token=token)
        self.vk = self.vk_session.get_api()
        self.longpoll = VkBotLongPoll(self.vk_session, group_id)
        self.storage = storage or create_storage(storage_path or "data/players.json")
        self.sessions: dict[str, VkRegistrationSession] = {}

    def run(self) -> None:
        print("VK bot started")
        for event in self.longpoll.listen():
            if event.type != VkBotEventType.MESSAGE_NEW:
                continue

            message = self._extract_message(event)
            if not message:
                continue

            peer_id = message.get("peer_id")
            from_id = message.get("from_id")
            text = (message.get("text") or "").strip()

            if not peer_id or not from_id or not text:
                continue

            try:
                self.handle_message(
                    external_user_id=str(from_id),
                    peer_id=peer_id,
                    text=text,
                )
            except Exception:
                logger.exception("VK message handling failed: peer_id=%s from_id=%s text=%r", peer_id, from_id, text)
                try:
                    self.send(
                        peer_id,
                        "Команда не выполнилась из-за внутренней ошибки. Попробуйте ещё раз или вернитесь в город командой /city.",
                    )
                except Exception:
                    logger.exception("Failed to send VK error notice: peer_id=%s", peer_id)

    def handle_message(self, external_user_id: str, peer_id: int, text: str) -> None:
        session_key = f"{VK_PLATFORM}:{external_user_id}"
        lowered = text.casefold()

        if lowered in {"/start", "начать заново"}:
            existing_player = self.storage.get_player_by_platform(VK_PLATFORM, external_user_id)
            if existing_player is not None:
                self.sessions.pop(session_key, None)
                self.send(
                    peer_id,
                    "Ты уже зарегистрирован. Команда /start повторно не запускает регистрацию.",
                )
                return

            self.sessions[session_key] = VkRegistrationSession(
                state=STATE_CONSENT,
            )
            self.send(peer_id, consent_message(), consent_keyboard())
            return

        if lowered == "/profile" or text == "Профиль":
            self.send_profile(external_user_id, peer_id)
            return

        if lowered.startswith("/promo"):
            parts = text.split(maxsplit=1)
            code = parts[1].strip() if len(parts) > 1 else ""
            self.redeem_promo(external_user_id, peer_id, code)
            return

        if lowered == "/link":
            self.send_link_code(external_user_id, peer_id)
            return

        if lowered.startswith("/connect"):
            parts = text.split(maxsplit=1)
            code = parts[1].strip() if len(parts) > 1 else ""
            self.connect_by_code(external_user_id, peer_id, code)
            return

        existing_player = self.storage.get_player_by_platform(VK_PLATFORM, external_user_id)
        session = self.sessions.get(session_key)

        # Registration must own its own reply buttons before the shared city
        # router sees them. Labels such as «Назад», «Да» and «Нет» are also
        # used by city/crafting flows; routing them to the city service while
        # the player has no character breaks the final registration step.
        if existing_player is None:
            session = self.sessions.setdefault(
                session_key,
                VkRegistrationSession(state=STATE_CONSENT),
            )

            # Согласие — обязательный первый шаг (в т.ч. при первом запуске VK,
            # когда приложение сразу присылает кнопку «Начать»).
            if session.state == STATE_CONSENT:
                if text == CONSENT_BUTTON:
                    session.state = STATE_START_MENU
                    self.send(
                        peer_id,
                        "Спасибо! Выберите действие:",
                        start_keyboard(),
                    )
                else:
                    self.send(peer_id, consent_message(), consent_keyboard())
                return

            if text == "Кратко о мире":
                self.send(peer_id, WORLD_SHORT_TEXT, start_keyboard())
                session.state = STATE_START_MENU
                return

            if text == "Начать":
                self.begin_registration(external_user_id, peer_id, session)
                return

            if session.state == STATE_AWAITING_NAME:
                self.receive_name(external_user_id, peer_id, session, text)
                return

            if session.state == STATE_NAME_CONFIRM:
                self.handle_name_confirmation(peer_id, session, text)
                return

            if session.state == STATE_AWAITING_GENDER:
                self.receive_gender(peer_id, session, text)
                return

            if session.state == STATE_GENDER_CONFIRM:
                self.handle_gender_confirmation(peer_id, session, text)
                return

            if session.state == STATE_AWAITING_RACE:
                self.receive_race(peer_id, session, text)
                return

            if session.state == STATE_RACE_CARD:
                self.handle_race_card(peer_id, session, text)
                return

            if session.state == STATE_RACE_CONFIRM:
                self.handle_race_confirmation(external_user_id, peer_id, session, text)
                return

            if lowered == "/city" or text in CITY_BUTTONS:
                self.send(
                    peer_id,
                    "Сначала нужно создать персонажа. Нажми /start и выбери «Начать».",
                    start_keyboard(),
                )
                return

            self.send(
                peer_id,
                "Нажми /start, чтобы открыть начальное меню.",
                start_keyboard(),
            )
            return

        # A persisted character wins over any stale in-memory registration session.
        # This avoids accidental registration handlers intercepting city buttons
        # after a restart/reconnect race.
        if session is not None:
            self.sessions.pop(session_key, None)

        if lowered == "/city":
            self.handle_city_action(external_user_id, peer_id, "В город")
            return

        if text in CITY_BUTTONS:
            self.handle_city_action(external_user_id, peer_id, text)
            return

        # Registered VK players should keep their current game context for any
        # free-form text, just like Telegram users do through the catch-all city
        # message handler.  Otherwise a player at the outside crossroads, in a
        # newly added city zone or on an unknown button could receive the start
        # menu instead of the correct current-location keyboard.
        self.handle_city_action(external_user_id, peer_id, text)
        return

    def begin_registration(
        self,
        external_user_id: str,
        peer_id: int,
        session: VkRegistrationSession,
    ) -> None:
        player = self.storage.get_player_by_platform(VK_PLATFORM, external_user_id)
        if player is not None:
            self.send(
                peer_id,
                "У тебя уже есть персонаж. Можно открыть профиль или войти в город.",
                after_registration_keyboard(),
            )
            return

        session.state = STATE_AWAITING_NAME
        session.name = None
        session.pending_name = None
        session.gender_id = None
        session.gender_label = None
        session.pending_gender_id = None
        session.pending_gender_label = None
        session.race_id = None
        self.send(peer_id, ASK_NAME_TEXT)

    def receive_name(
        self,
        external_user_id: str,
        peer_id: int,
        session: VkRegistrationSession,
        raw_name: str,
    ) -> None:
        is_valid, result = validate_name(raw_name)

        if not is_valid:
            self.send(peer_id, result)
            return

        if self.storage.is_name_taken(result):
            self.send(peer_id, "Такое имя уже зарегистрировано. Введи другое имя.")
            return

        session.pending_name = result
        session.state = STATE_NAME_CONFIRM
        self.send(
            peer_id,
            NAME_CONFIRM_TEXT_TEMPLATE.format(player_name=result),
            name_confirm_keyboard(),
        )

    def handle_name_confirmation(
        self,
        peer_id: int,
        session: VkRegistrationSession,
        text: str,
    ) -> None:
        if text == "Ввести заново":
            session.pending_name = None
            session.name = None
            session.state = STATE_AWAITING_NAME
            self.send(peer_id, ASK_NAME_AGAIN_TEXT)
            return

        if text != "Подтвердить":
            self.send(
                peer_id,
                "Выбери действие на клавиатуре: «Подтвердить» или «Ввести заново».",
                name_confirm_keyboard(),
            )
            return

        if not session.pending_name:
            session.state = STATE_AWAITING_NAME
            self.send(peer_id, ASK_NAME_AGAIN_TEXT)
            return

        if self.storage.is_name_taken(session.pending_name):
            session.pending_name = None
            session.state = STATE_AWAITING_NAME
            self.send(peer_id, "Пока ты подтверждал имя, его уже заняли. Введи другое имя.")
            return

        session.name = session.pending_name
        session.pending_name = None
        session.state = STATE_AWAITING_GENDER
        self.send(peer_id, ASK_GENDER_TEXT)
        self.send(peer_id, GENDER_WARNING_TEXT, gender_keyboard())

    @staticmethod
    def _gender_choice_from_text(text: str) -> tuple[str, str] | None:
        if text == "Муж.":
            return "male", "Муж."
        if text == "Жен.":
            return "female", "Жен."
        return None

    def receive_gender(
        self,
        peer_id: int,
        session: VkRegistrationSession,
        text: str,
    ) -> None:
        choice = self._gender_choice_from_text(text)
        if choice is None:
            self.send(peer_id, "Выбери пол кнопкой на клавиатуре.", gender_keyboard())
            return

        session.pending_gender_id, session.pending_gender_label = choice
        session.state = STATE_GENDER_CONFIRM
        self.send(peer_id, "— Вы уверены?", gender_confirm_keyboard())

    def handle_gender_confirmation(
        self,
        peer_id: int,
        session: VkRegistrationSession,
        text: str,
    ) -> None:
        if text == "Нет":
            session.pending_gender_id = None
            session.pending_gender_label = None
            session.state = STATE_AWAITING_GENDER
            self.send(peer_id, "— Какого вы пола?", gender_keyboard())
            return

        if text != "Да":
            self.send(
                peer_id,
                "Выбери действие на клавиатуре: «Да» или «Нет».",
                gender_confirm_keyboard(),
            )
            return

        if not session.pending_gender_id or not session.pending_gender_label:
            session.state = STATE_AWAITING_GENDER
            self.send(peer_id, "— Какого вы пола?", gender_keyboard())
            return

        session.gender_id = session.pending_gender_id
        session.gender_label = session.pending_gender_label
        session.pending_gender_id = None
        session.pending_gender_label = None
        session.state = STATE_AWAITING_RACE
        self.send(peer_id, ASK_RACE_TEXT, race_keyboard())

    def receive_race(
        self,
        peer_id: int,
        session: VkRegistrationSession,
        race_name: str,
    ) -> None:
        races = load_races()
        race_id = get_race_id_by_name(races, race_name)

        if race_id is None:
            self.send(
                peer_id,
                "Такой расы нет. Выбери расу кнопкой на клавиатуре.",
                race_keyboard(),
            )
            return

        session.race_id = race_id
        session.state = STATE_RACE_CARD
        self.send(peer_id, format_race_card(race_id, races), race_card_keyboard())

    def handle_race_card(
        self,
        peer_id: int,
        session: VkRegistrationSession,
        text: str,
    ) -> None:
        if text == "Назад":
            session.state = STATE_AWAITING_RACE
            self.send(peer_id, "Выбери расу:", race_keyboard())
            return

        if text == "Выбрать":
            races = load_races()
            race_id = session.race_id

            if race_id is None:
                session.state = STATE_AWAITING_RACE
                self.send(peer_id, "Сначала выбери расу.", race_keyboard())
                return

            race_name = races[race_id]["name"]
            session.state = STATE_RACE_CONFIRM
            self.send(
                peer_id,
                f"Ты уверен, что хочешь выбрать расу: {race_name}?",
                race_confirm_keyboard(),
            )
            return

        self.send(
            peer_id,
            "Выбери действие на клавиатуре: «Выбрать» или «Назад».",
            race_card_keyboard(),
        )

    def handle_race_confirmation(
        self,
        external_user_id: str,
        peer_id: int,
        session: VkRegistrationSession,
        text: str,
    ) -> None:
        races = load_races()
        race_id = session.race_id

        if text == "Нет":
            if race_id is None:
                session.state = STATE_AWAITING_RACE
                self.send(peer_id, "Выбери расу:", race_keyboard())
                return

            session.state = STATE_RACE_CARD
            self.send(peer_id, format_race_card(race_id, races), race_card_keyboard())
            return

        if text != "Да":
            self.send(
                peer_id,
                "Выбери действие на клавиатуре: «Да» или «Нет».",
                race_confirm_keyboard(),
            )
            return

        if self.storage.get_player_by_platform(VK_PLATFORM, external_user_id) is not None:
            self.send(peer_id, "Персонаж уже создан.", after_registration_keyboard())
            self.sessions.pop(f"{VK_PLATFORM}:{external_user_id}", None)
            return

        if not session.name or not race_id or not session.gender_id or not session.gender_label:
            session.state = STATE_START_MENU
            self.send(
                peer_id,
                "Данные регистрации потеряны. Нажми «Начать» ещё раз.",
                start_keyboard(),
            )
            return

        if self.storage.is_name_taken(session.name):
            session.state = STATE_AWAITING_NAME
            self.send(
                peer_id,
                "Пока ты выбирал расу, это имя уже заняли. Введи другое имя.",
            )
            return

        game_id = self.storage.generate_game_id()
        player = create_player(
            game_id=game_id,
            platform=VK_PLATFORM,
            external_user_id=external_user_id,
            name=session.name,
            race_id=race_id,
            races=races,
            gender_id=session.gender_id,
            gender_label=session.gender_label,
        )
        self.storage.save_new_player(player, VK_PLATFORM, external_user_id)
        self.sessions.pop(f"{VK_PLATFORM}:{external_user_id}", None)

        self.send(
            peer_id,
            FINAL_REGISTRATION_TEXT.format(player_name=player["name"]),
            after_registration_keyboard(),
        )

    def send_profile(self, external_user_id: str, peer_id: int) -> None:
        player = self.storage.get_player_by_platform(VK_PLATFORM, external_user_id)

        if player is None:
            self.send(
                peer_id,
                "У тебя ещё нет персонажа. Нажми /start и выбери «Начать».\n\n"
                "Если персонаж уже создан в Telegram, введи /connect код_привязки.",
                start_keyboard(),
            )
            return

        profile_url = create_profile_site_link(self.storage, player, VK_PLATFORM)
        # Не передаём keyboard: ссылка на профиль не должна менять текущие кнопки.
        self.send(
            peer_id,
            f"🔮 Временная ссылка на профиль игрока {player['name']}:\n"
            f"Единый игровой ID: {player['game_id']}\n"
            f"Ссылка: {profile_url}\n\n"
            "Ссылка действует ограниченное время. Когда она истечёт, нажми «Профиль» ещё раз.",
        )

    def redeem_promo(self, external_user_id: str, peer_id: int, code: str) -> None:
        player = self.storage.get_player_by_platform(VK_PLATFORM, external_user_id)
        if player is None:
            self.send(peer_id, "Сначала нужно создать персонажа. Нажми /start и выбери «Начать».", start_keyboard())
            return
        if not code:
            self.send(peer_id, "Формат: /promo CODE")
            return
        ok, message = redeem_promo_code(self.storage, str(player.get("game_id")), code)
        prefix = "✅" if ok else "⚠️"
        self.send(peer_id, f"{prefix} {message}")

    def send_link_code(self, external_user_id: str, peer_id: int) -> None:
        player = self.storage.get_player_by_platform(VK_PLATFORM, external_user_id)

        if player is None:
            self.send(
                peer_id,
                "Сначала нужно создать персонажа. Нажми /start и выбери «Начать».",
                start_keyboard(),
            )
            return

        code = self.storage.create_link_code(player["game_id"])
        self.send(
            peer_id,
            "🔗 Код привязки создан.\n\n"
            f"Единый игровой ID: {player['game_id']}\n"
            f"Код: {code}\n\n"
            "Открой Telegram-бота и введи:\n"
            f"/connect {code}\n\n"
            "Код одноразовый и действует 15 минут.",
            after_registration_keyboard(),
        )

    def connect_by_code(self, external_user_id: str, peer_id: int, code: str) -> None:
        if not code:
            self.send(peer_id, "Введите код привязки. Пример:\n/connect AB12CD", start_keyboard())
            return

        ok, message, player = self.storage.connect_platform_by_code(
            code=code,
            platform=VK_PLATFORM,
            external_user_id=external_user_id,
        )

        if not ok:
            self.send(peer_id, message, start_keyboard())
            return

        self.sessions.pop(f"{VK_PLATFORM}:{external_user_id}", None)
        self.send(
            peer_id,
            f"✅ {message}\n\n"
            f"Персонаж: {player['name']}\n"
            f"Единый игровой ID: {player['game_id']}",
            after_registration_keyboard(),
        )

    def handle_city_action(self, external_user_id: str, peer_id: int, action: str) -> None:
        player = self.storage.get_player_by_platform(VK_PLATFORM, external_user_id)

        if player is None:
            self.send(
                peer_id,
                "Сначала нужно создать персонажа. Нажми /start и выбери «Начать».",
                start_keyboard(),
            )
            return

        append_player_chat_log(player, direction="player", text=action, platform=VK_PLATFORM)
        result = process_world_action(
            storage=self.storage,
            player=player,
            action=action,
            platform=VK_PLATFORM,
        )
        for message in [*pop_pending_bot_messages(player), *getattr(result, "extra_messages", ())]:
            append_player_chat_log(player, direction="bot", text=message, platform=VK_PLATFORM)
            self.send(peer_id, message)
        append_player_chat_log(player, direction="bot", text=result.text, platform=VK_PLATFORM)
        self.send(peer_id, result.text, make_keyboard(result.buttons))
        self.storage.update_player(player)
        self.schedule_timer_notification(peer_id, result.scheduled_timer)

    def schedule_timer_notification(self, peer_id: int, timer_data: dict | None) -> None:
        if not timer_data:
            return
        seconds = max(0.05, float(timer_data.get("seconds") or 0.05))
        game_id = timer_data.get("game_id")
        timer_id = timer_data.get("timer_id")
        if not game_id or not timer_id:
            return

        attach_timer_notification(
            storage=self.storage,
            game_id=str(game_id),
            timer_id=str(timer_id),
            platform=VK_PLATFORM,
            target_id=str(peer_id),
        )

        def send_timer_result(_platform: str, target_id: str, response) -> None:
            self.send(int(target_id), response.text, make_keyboard(response.buttons))

        schedule_timer_delivery(
            storage=self.storage,
            game_id=str(game_id),
            timer_id=str(timer_id),
            seconds=seconds,
            send_callback=send_timer_result,
            platform_filter=VK_PLATFORM,
        )

    def send(self, peer_id: int, text: str, keyboard: str | None = None) -> None:
        params = {
            "peer_id": peer_id,
            "message": text,
            "random_id": get_random_id(),
        }
        if keyboard is not None:
            params["keyboard"] = keyboard
        self.vk.messages.send(**params)

    @staticmethod
    def _extract_message(event) -> dict | None:
        obj = getattr(event, "obj", None)

        if obj is None:
            obj = getattr(event, "object", None)

        if isinstance(obj, dict):
            message = obj.get("message", obj)
            return message if isinstance(message, dict) else None

        message = getattr(obj, "message", None)
        if isinstance(message, dict):
            return message

        return None
