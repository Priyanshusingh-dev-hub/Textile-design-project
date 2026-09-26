"""Telegram inbox: a bot that only receives designs and saves them on the PC.

Anyone who sends the bot a photo or a file gets it stored under the inbox
folder, one folder per day, with a line in `inbox-log.csv` (who, when, caption).
It does no colour work — the operator opens the saved design in LoomLab.

Standard library only, so any Python 3 runs it. It asks Telegram for new
messages (long polling), so the PC needs no public address or open port.

    python -m app.inbox_bot ..\\telegram-bot.txt      (run-bot-windows.bat)
"""
from __future__ import annotations

import csv
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

API = "https://api.telegram.org"
# The Bot API hands a bot files up to 20 MB; larger ones it refuses to serve.
MAX_DOWNLOAD = 20 * 1024 * 1024
POLL_SECONDS = 50

SETTINGS_TEMPLATE = """\
# LoomLab Telegram inbox — settings
# Telegram me @BotFather se mila token TOKEN= ke aage daalo.
# Ye password jaisa hai: kisi ko mat bhejna, kahin share mat karna.
TOKEN=

# Designs kahan save hon. Khaali chhodo to LoomLab folder me "Designs-Inbox".
FOLDER=

# Sirf in logon ke designs lo: Telegram id, comma se alag (bot ko /id bhejne
# par wo apni id bata deta hai). Khaali chhodo to jo bhi bheje, save hoga.
ALLOWED=
"""

_TOKEN = re.compile(r"^\d{5,}:[A-Za-z0-9_-]{30,}$")
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                     *(f"LPT{i}" for i in range(1, 10))}

WELCOME = ("Namaste! Design bhejiye, main use save kar dunga.\n"
           "Poori quality ke liye design 📎 File / Document ki tarah bhejiye, "
           "Photo ki tarah nahi.")
PHOTO_NOTE = ("\nℹ️ Photo ki tarah bheja gaya tha, to Telegram ne ise chhota/compress "
              "kar diya. Poori quality chahiye to 📎 File ki tarah bhejiye.")
NOT_A_FILE = "Design ki photo ya file bhejiye, main use save kar dunga."
TOO_BIG = ("❌ Ye file {mb:.0f} MB ki hai. Telegram bot 20 MB tak ki file hi le sakta "
           "hai. Ise zip karke, ya chhota karke bhejiye.")
FAILED = "❌ Ye save nahi ho paya. Dobara bhejiye, ya File ki tarah bhejiye."
NOT_ALLOWED = "Maaf kijiye, ye bot sirf mill ke liye hai. Aapki id: {uid}"


class SettingsError(Exception):
    pass


@dataclass
class Settings:
    token: str
    folder: Path
    allowed: set[int] = field(default_factory=set)


def load_settings(path: Path, default_folder: Path) -> Settings:
    """Read `KEY=value` lines. A missing file is created from the template."""
    if not path.exists():
        path.write_text(SETTINGS_TEMPLATE, encoding="utf-8")
        raise SettingsError(f"Settings file bana di: {path}\n"
                            "Usme TOKEN= ke aage BotFather wala token daalo, save karo, "
                            "aur bot dobara chalao.")
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip().upper()] = value.strip().strip('"').strip("'")
    token = values.get("TOKEN", "")
    if not token:
        raise SettingsError(f"{path} me TOKEN= khaali hai. BotFather wala token daalo.")
    if not _TOKEN.match(token):
        raise SettingsError(f"{path} me TOKEN sahi nahi lag raha. BotFather ne jo poori "
                            "line di thi (jaise 123456789:ABC...), wahi daalo.")
    folder = Path(values["FOLDER"]).expanduser() if values.get("FOLDER") else default_folder
    allowed: set[int] = set()
    for part in re.split(r"[,\s]+", values.get("ALLOWED", "")):
        if part:
            if not part.lstrip("-").isdigit():
                raise SettingsError(f"ALLOWED me '{part}' id nahi hai. Sirf number, "
                                    "comma se alag.")
            allowed.add(int(part))
    return Settings(token=token, folder=folder, allowed=allowed)


def safe_name(name: str, limit: int = 80) -> str:
    """A file name Windows and Linux both accept, keeping it readable."""
    name = _UNSAFE.sub("_", name).strip().strip(".")
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    if stem.upper() in _WINDOWS_RESERVED:
        stem = f"_{stem}"
    stem = stem[: max(1, limit - len(ext) - 1)].rstrip(" .") or "file"
    return f"{stem}.{ext}" if ext else stem


def unique_path(path: Path) -> Path:
    """`path`, or `name_2.ext`, `name_3.ext` ... if it is taken."""
    if not path.exists():
        return path
    n = 2
    while True:
        candidate = path.with_name(f"{path.stem}_{n}{path.suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def sender_name(user: dict) -> str:
    name = " ".join(p for p in (user.get("first_name"), user.get("last_name")) if p)
    return name or user.get("username") or str(user.get("id", "unknown"))


class TelegramError(Exception):
    def __init__(self, code: int, description: str):
        super().__init__(f"{code}: {description}")
        self.code = code
        self.description = description


class TelegramApi:
    """The four Bot API calls the inbox needs."""

    def __init__(self, token: str):
        self._base = f"{API}/bot{token}"
        self._files = f"{API}/file/bot{token}"

    def call(self, method: str, wait: float = 30, **params) -> object:
        data = json.dumps(params).encode()
        req = urllib.request.Request(f"{self._base}/{method}", data=data,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=wait) as resp:
                body = json.load(resp)
        except urllib.error.HTTPError as err:
            try:
                body = json.load(err)
            except ValueError:
                raise TelegramError(err.code, err.reason) from None
        if not body.get("ok"):
            raise TelegramError(body.get("error_code", 0), body.get("description", ""))
        return body["result"]

    def download(self, file_path: str) -> bytes:
        url = f"{self._files}/{urllib.parse.quote(file_path)}"
        with urllib.request.urlopen(url, timeout=120) as resp:
            return resp.read()


class InboxBot:
    def __init__(self, api, settings: Settings, now=datetime.now):
        self.api = api
        self.settings = settings
        self.now = now
        self.folder = settings.folder
        self._offset_file = self.folder / ".telegram-offset"

    # -- polling -----------------------------------------------------------
    def load_offset(self) -> int:
        try:
            return int(self._offset_file.read_text().strip())
        except (OSError, ValueError):
            return 0

    def save_offset(self, offset: int) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        self._offset_file.write_text(str(offset))

    def poll_once(self, timeout: int = POLL_SECONDS) -> int:
        """Fetch and handle one batch of messages; returns how many came."""
        updates = self.api.call("getUpdates", wait=timeout + 15, offset=self.load_offset(),
                                timeout=timeout, allowed_updates=["message"])
        return self._handle_all(updates)

    def _handle_all(self, updates) -> int:
        for update in updates:
            message = update.get("message")
            if message:
                try:
                    self.handle(message)
                except OSError:
                    # Network or disk trouble: leave the offset where it is, so
                    # the same message is fetched and saved on the next try.
                    raise
                except TelegramError as err:
                    if err.code == 429 or err.code >= 500:  # Telegram busy: retry
                        raise
                    self._failed(message, err)
                except Exception as err:  # a message this bot cannot handle
                    self._failed(message, err)
            self.save_offset(update["update_id"] + 1)
        return len(updates)

    def _failed(self, message: dict, err: Exception) -> None:
        print(f"Message {message.get('message_id')} save nahi hua: {err!r}")
        try:
            self.reply(message, FAILED)
        except Exception:
            pass

    # -- one message -------------------------------------------------------
    def reply(self, message: dict, text: str) -> None:
        self.api.call("sendMessage", chat_id=message["chat"]["id"], text=text,
                      reply_parameters={"message_id": message["message_id"],
                                        "allow_sending_without_reply": True})

    def handle(self, message: dict) -> Path | None:
        user = message.get("from") or {}
        uid = user.get("id", 0)
        text = (message.get("text") or "").strip()
        command = text.split()[0].split("@")[0].lower() if text.startswith("/") else ""
        if command == "/id":
            self.reply(message, f"Aapki Telegram id: {uid}")
            return None
        if self.settings.allowed and uid not in self.settings.allowed:
            self.reply(message, NOT_ALLOWED.format(uid=uid))
            return None
        if command in ("/start", "/help"):
            self.reply(message, WELCOME)
            return None

        item = self._file_of(message)
        if item is None:
            self.reply(message, NOT_A_FILE)
            return None
        file_id, name, size, is_photo = item
        if size and size > MAX_DOWNLOAD:
            self.reply(message, TOO_BIG.format(mb=size / 1024 / 1024))
            return None
        try:
            info = self.api.call("getFile", file_id=file_id)
            data = self.api.download(info["file_path"])
        except TelegramError as err:
            if "too big" in err.description.lower():
                self.reply(message, TOO_BIG.format(mb=(size or MAX_DOWNLOAD) / 1024 / 1024))
                return None
            raise
        if not name:
            name = Path(info.get("file_path", "")).name or "design.jpg"
        path = self.store(message, user, name, data)
        self.reply(message, f"✅ Save ho gaya: {path.name} ({len(data) / 1024 / 1024:.1f} MB)"
                   + (PHOTO_NOTE if is_photo else ""))
        return path

    @staticmethod
    def _file_of(message: dict):
        """(file_id, name, size, is_photo) of the design in `message`, or None."""
        doc = message.get("document")
        if doc:
            return doc["file_id"], doc.get("file_name") or "", doc.get("file_size"), False
        photos = message.get("photo")
        if photos:
            # Telegram sends several sizes of a photo; the last is the largest.
            best = max(photos, key=lambda p: (p.get("width", 0) * p.get("height", 0),
                                              p.get("file_size", 0)))
            return best["file_id"], "", best.get("file_size"), True
        return None

    def store(self, message: dict, user: dict, name: str, data: bytes) -> Path:
        when = datetime.fromtimestamp(message["date"]) if "date" in message else self.now()
        day = self.folder / when.strftime("%Y-%m-%d")
        day.mkdir(parents=True, exist_ok=True)
        who = safe_name(sender_name(user), limit=30)
        path = unique_path(day / safe_name(f"{when:%H%M%S}_{who}_{name}"))
        tmp = path.with_name(path.name + ".part")
        tmp.write_bytes(data)
        tmp.replace(path)
        self._log(when, user, path, message.get("caption") or "")
        return path

    def _log(self, when: datetime, user: dict, path: Path, caption: str) -> None:
        log = self.folder / "inbox-log.csv"
        new = not log.exists()
        # utf-8-sig so Excel on Windows shows Hindi names and captions properly.
        with log.open("a", newline="", encoding="utf-8-sig" if new else "utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["time", "sender", "telegram_id", "file", "caption"])
            w.writerow([when.strftime("%Y-%m-%d %H:%M:%S"), sender_name(user),
                        user.get("id", ""), str(path.relative_to(self.folder)), caption])


def run(settings_path: Path) -> int:
    default_folder = settings_path.resolve().parent / "Designs-Inbox"
    try:
        settings = load_settings(settings_path, default_folder)
    except SettingsError as err:
        print(err)
        return 2
    api = TelegramApi(settings.token)
    try:
        me = api.call("getMe")
    except TelegramError as err:
        if err.code == 401:
            print("Token galat hai (Telegram ne mana kar diya). BotFather se token "
                  "dobara copy karke settings me daalo.")
            return 2
        raise
    except urllib.error.URLError as err:
        print(f"Telegram tak nahi pahunch pa rahe ({err.reason}). Internet check karo.")
        return 1
    bot = InboxBot(api, settings)
    print(f"Bot chal raha hai: @{me.get('username')}")
    print(f"Designs yahan save honge: {settings.folder}")
    print("Band karne ke liye ye window band kar do (ya Ctrl+C).")
    wait = 2
    while True:
        try:
            bot.poll_once()
            wait = 2
        except KeyboardInterrupt:
            return 0
        except TelegramError as err:
            if err.code == 409:
                print("Ye bot kahin aur bhi chal raha hai. Ek hi jagah chalao.")
            else:
                print(f"Telegram error: {err}")
            time.sleep(wait)
            wait = min(wait * 2, 60)
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as err:
            print(f"Internet me dikkat ({err}); {wait} second me dobara koshish...")
            time.sleep(wait)
            wait = min(wait * 2, 60)


if __name__ == "__main__":
    here = Path(__file__).resolve().parents[2]
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else here / "telegram-bot.txt"
    try:
        sys.exit(run(target))
    except KeyboardInterrupt:
        sys.exit(0)
