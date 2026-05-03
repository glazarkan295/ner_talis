from dataclasses import dataclass

import vk_api
from vk_api.bot_longpoll import VkBotEventType, VkBotLongPoll
from vk_api.utils import get_random_id

from keyboards.vk_keyboards import (
    after_registration_keyboard,
    make_keyboard,
    race_card_keyboard,
    race_confirm_keyboard,
    race_keyboard,
    start_keyboard,
)
from services.city_service import (
    CITY_BUTTONS,
    apply_city_transition,
    build_response_text,
    get_city_response,
)
from services.registration_service import (
    build_profile_url,
    create_player,
    format_race_card,
    get_race_id_by_name,
    load_races,
    validate_name,
)
from storage.json_storage import JsonStorage
from texts.registration_texts import (
    ASK_NAME_TEXT,
    ASK_RACE_TEXT,
    FINAL_REGISTRATION_TEXT,
    WORLD_SHORT_TEXT,
)

STATE_START_MENU = "start_menu"
STATE_AWAITING_NAME = "awaiting_name"
STATE_AWAITING_RACE = "awaiting_race"
STATE_RACE_CARD = "race_card"
STATE_RACE_CONFIRM = "race_confirm"
VK_PLATFORM = "vk"


@dataclass
class VkRegistrationSession:
    state: str = STATE_START_MENU
    name: str | None = None
    race_id: str | None = None


class VkRegistrationBot:
    def __init__(self, token: str, group_id: int, storage_path: str):
        self.vk_session = vk_api.VkApi(token=token)
        self.vk = self.vk_session.get_api()
        self.longpoll = VkBotLongPoll(self.vk_session, group_id)
        self.storage = JsonStorage(storage_path)
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

            self.handle_message(
                external_user_id=str(from_id),
                peer_id=peer_id,
                text=text,
            )

    def handle_message(self, external_user_id: str, peer_id: int, text: str) -> None:
        session_key = f"{VK_PLATFORM}:{external_user_id}"
        lowered = text.casefold()

        if lowered in {"/start", "начать заново"}:
            self.sessions[session_key] = VkRegistrationSession(
                state=STATE_START_MENU,
            )
            self.send(peer_id, "Выберите действие:", start_keyboard())
            return

        if lowered == "/profile" or text == "Профиль":
            self.send_profile(external_user_id, peer_id)
            return

        if lowered == "/link":
            self.send_link_code(external_user_id, peer_id)
            return

        if lowered.startswith("/connect"):
            parts = text.split(maxsplit=1)
            code = parts[1].strip() if len(parts) > 1 else ""
            self.connect_by_code(external_user_id, peer_id, code)
            return

        if lowered == "/city":
            self.handle_city_action(external_user_id, peer_id, "В город")
            return

        if text in CITY_BUTTONS:
            self.handle_city_action(external_user_id, peer_id, text)
            return

        session = self.sessions.setdefault(
            session_key,
            VkRegistrationSession(state=STATE_START_MENU),
        )

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

        if session.state == STATE_AWAITING_RACE:
            self.receive_race(peer_id, session, text)
            return

        if session.state == STATE_RACE_CARD:
            self.handle_race_card(peer_id, session, text)
            return

        if session.state == STATE_RACE_CONFIRM:
            self.handle_race_confirmation(external_user_id, peer_id, session, text)
            return

        self.send(
            peer_id,
            "Нажми /start, чтобы открыть начальное меню.",
            start_keyboard(),
        )

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

        session.name = result
        session.state = STATE_AWAITING_RACE
        self.send(
            peer_id,
            f"{ASK_RACE_TEXT}\n\nВыбери расу:",
            race_keyboard(),
        )

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

        if not session.name or not race_id:
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

        profile_url = build_profile_url(player)
        self.send(
            peer_id,
            f"🔮 Профиль игрока {player['name']}:\n"
            f"Единый игровой ID: {player['game_id']}\n"
            f"Ссылка: {profile_url}",
            after_registration_keyboard(),
        )

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

        response = get_city_response(action)
        player = apply_city_transition(self.storage, player, response)
        text = build_response_text(
            storage=self.storage,
            player=player,
            response=response,
            platform=VK_PLATFORM,
        )
        self.send(peer_id, text, make_keyboard(response.buttons))

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
