"""Telegram inbox and order desk.

Anyone who sends the bot a photo or a file gets it stored under the inbox
folder, one folder per day, with a line in `inbox-log.csv` (who, when, caption).
With the LoomLab engine running (ENGINE=), the saved design then goes through
auto mode and the client gets the proof and the quote back, with Approve /
Change buttons; a job auto mode holds for review goes to the operator first
(see bot_orders.py). The colour work is the engine's; this only carries
messages.

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

from .bot_orders import Engine, EngineError, Jobs, multipart, parse_request, summary

API = "https://api.telegram.org"
# The Bot API hands a bot files up to 20 MB; larger ones it refuses to serve.
MAX_DOWNLOAD = 20 * 1024 * 1024
POLL_SECONDS = 50
QUEUE_RETRY_SECONDS = 30      # how often designs queued while the engine was closed are tried again

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

# Operator (mill ka banda) ki Telegram id, comma se alag. Jin designs me dikkat
# ho wo pehle inke paas jaate hain, aur approve hue orders ki zip bhi inhe milti hai.
OPERATOR=

# LoomLab engine ka pata. Engine chal raha ho to har design ka proof aur quote
# client ko apne aap jaata hai. "off" likho to bot sirf design save karega.
ENGINE=http://localhost:8003

# Print kitne inch chauda (khaali = file ka apna size). Client caption me
# "30 inch" likhe to wahi chalega.
WIDTH_IN=

# Quote kitne meter ka bane agar client caption me na likhe (jaise "500 m").
# Khaali = sirf proof, quote nahi.
METERS=
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
WORKING = "⏳ Proof aur quote ban raha hai, 1-2 minute lagenge…"
ENGINE_DOWN = ("Design save ho gaya hai. LoomLab abhi band hai; chalu hote hi proof aur "
               "quote yahin apne aap aa jaayenge.")
ENGINE_FAILED = "❌ Is design ka proof nahi ban paya: {why}\nHamari team dekh kar batayegi."
HELD = ("🔎 Design me kuch cheezein hamari team ek baar dekhegi, phir proof aur "
        "quote bhejenge.")
ASK = "Proof theek hai? ✅ Approve dabaiye, ya ✏️ Change."
APPROVED = "✅ Order approve ho gaya! Screens banne ja rahi hain. Dhanyavaad 🙏"
ASK_CHANGE = ("Kya badalna hai? Aise likhiye:\n• 6 inks\n• 30 inch (print ki chaudai)\n"
              "• 800 meter\nKuch aur badlav ho to wo bhi likh dijiye, team dekh legi.")
CHANGE_TO_TEAM = "Aapki baat team ko bhej di hai; woh badlav karke proof bhejenge."
REJECTED = ("Is design ke baare me hamari team aapse seedhe baat karegi. "
            "Dhanyavaad 🙏")
GONE = "Ye order ab nahi mila (48 ghante purana?). Design dobara bhejiye."


class SettingsError(Exception):
    pass


@dataclass
class Settings:
    token: str
    folder: Path
    allowed: set[int] = field(default_factory=set)
    operators: set[int] = field(default_factory=set)
    engine: str | None = None          # LoomLab engine URL, None = save only
    width_in: float | None = None      # default print width
    meters: float | None = None        # default run to quote


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
    def ids(key):
        out: set[int] = set()
        for part in re.split(r"[,\s]+", values.get(key, "")):
            if part:
                if not part.lstrip("-").isdigit():
                    raise SettingsError(f"{key} me '{part}' id nahi hai. Sirf number, "
                                        "comma se alag.")
                out.add(int(part))
        return out

    def number(key):
        raw = values.get(key, "")
        if not raw:
            return None
        try:
            v = float(raw)
        except ValueError:
            raise SettingsError(f"{key} me '{raw}' number nahi hai.") from None
        if v <= 0:
            raise SettingsError(f"{key} 0 se bada hona chahiye.")
        return v

    engine = values.get("ENGINE", "http://localhost:8003")
    engine = None if engine.lower() in ("", "off", "no", "0") else engine
    if engine and not re.match(r"^https?://", engine):
        raise SettingsError(f"ENGINE me '{engine}' pata nahi lag raha (jaise http://localhost:8003).")
    return Settings(token=token, folder=folder, allowed=ids("ALLOWED"), operators=ids("OPERATOR"),
                    engine=engine, width_in=number("WIDTH_IN"), meters=number("METERS"))


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
    """The Bot API calls the bot needs: JSON calls, file sends, downloads."""

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

    def send_file(self, method: str, field: str, filename: str, data: bytes, ctype: str,
                  **params) -> object:
        """sendPhoto / sendDocument with the file's bytes."""
        fields = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
                  for k, v in params.items()}
        body, content_type = multipart(fields, [(field, filename, data, ctype)])
        req = urllib.request.Request(f"{self._base}/{method}", data=body,
                                     headers={"Content-Type": content_type})
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                result = json.load(resp)
        except urllib.error.HTTPError as err:
            try:
                result = json.load(err)
            except ValueError:
                raise TelegramError(err.code, err.reason) from None
        if not result.get("ok"):
            raise TelegramError(result.get("error_code", 0), result.get("description", ""))
        return result["result"]

    def download(self, file_path: str) -> bytes:
        url = f"{self._files}/{urllib.parse.quote(file_path)}"
        with urllib.request.urlopen(url, timeout=120) as resp:
            return resp.read()


class InboxBot:
    def __init__(self, api, settings: Settings, now=datetime.now, engine=None):
        self.api = api
        self.settings = settings
        self.now = now
        self.folder = settings.folder
        self._offset_file = self.folder / ".telegram-offset"
        self.engine = engine if engine is not None else (Engine(settings.engine) if settings.engine else None)
        self._queue_tried = float("-inf")
        self.jobs = Jobs(self.folder / "orders.json")

    # -- polling -----------------------------------------------------------
    def load_offset(self) -> int:
        try:
            return int(self._offset_file.read_text().strip())
        except (OSError, ValueError):
            return 0

    def save_offset(self, offset: int) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        self._offset_file.write_text(str(offset))

    def retry_queue(self) -> int:
        """Designs that arrived while the engine was closed, oldest first, once
        it answers again. Each leaves the queue before it runs: once its job
        is made a failure is reported, never retried (a second job)."""
        done = 0
        while self.engine and self.jobs.queue:
            item = self.jobs.queue[0]
            path = Path(item["path"])
            self.jobs.dequeue()
            if not path.exists():
                self.tell_operators(f"⚠️ Queue ka design {path.name} ab folder me nahi hai; chhod diya.")
                continue
            message = {"chat": {"id": item["chat"]}, "message_id": item["message_id"]}
            try:
                self.process(message, item["user"], path, item["params"], queued=True)
                done += 1
            except EngineError as err:
                if err.down:                     # still closed: back to the front, try later
                    self.jobs.enqueue(item, front=True)
                    break
                raise
            except (OSError, TelegramError) as err:
                print(f"Queue ka {path.name} chala, par jawab nahi gaya: {err!r}")
                self.tell_operators(f"⚠️ {path.name}: proof client tak nahi gaya ({err}). Order: orders.json")
        return done

    def poll_once(self, timeout: int = POLL_SECONDS) -> int:
        """Fetch and handle one batch of messages; returns how many came."""
        if self.jobs.queue and time.monotonic() - self._queue_tried > QUEUE_RETRY_SECONDS:
            self._queue_tried = time.monotonic()
            self.retry_queue()
        updates = self.api.call("getUpdates", wait=timeout + 15, offset=self.load_offset(),
                                timeout=timeout, allowed_updates=["message", "callback_query"])
        return self._handle_all(updates)

    def _handle_all(self, updates) -> int:
        for update in updates:
            message = update.get("message")
            if update.get("callback_query"):
                cq = update["callback_query"]
                message = cq.get("message") or {"chat": {"id": cq["from"]["id"]}, "message_id": 0}
            if message:
                try:
                    if update.get("callback_query"):
                        self.handle_button(update["callback_query"])
                    else:
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
            job_id = self.jobs.awaiting(message["chat"]["id"])
            if text and not command and job_id:
                self.handle_change(message, user, job_id, text)
            else:
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
        # From here the design is saved: a failure is reported, never retried
        # (a retry would save it again and run a second job).
        try:
            self.reply(message, f"✅ Save ho gaya: {path.name} ({len(data) / 1024 / 1024:.1f} MB)"
                       + (PHOTO_NOTE if is_photo else ""))
        except (OSError, TelegramError) as err:
            print(f"{path.name} save hua, par jawab nahi gaya: {err!r}")
        if self.engine:
            params = {"width_in": self.settings.width_in, "meters": self.settings.meters}
            params.update(parse_request(message.get("caption") or ""))
            try:
                self.process(message, user, path, params)
            except (OSError, TelegramError) as err:
                # The design is saved and the job recorded: retrying the
                # message would save it again and run a second job, so say so
                # and move on.
                print(f"Proof {path.name} ka jawab nahi gaya: {err!r}")
                self.tell_operators(f"⚠️ {path.name}: proof client tak nahi gaya ({err}). Order: orders.json")
        return path

    # -- the order desk ----------------------------------------------------
    def process(self, message: dict, user: dict, path: Path, params: dict, queued: bool = False) -> str | None:
        """Run the saved design through auto mode and send the result on:
        to the client, or to the operator first when auto mode holds it.
        With the engine closed the design waits in the queue (`queued`: this
        is the queue retrying it, and a closed engine is raised, not queued twice)."""
        chat = message["chat"]["id"]
        if not queued:
            self.reply(message, WORKING)
        try:
            report = self.engine.auto(path.read_bytes(), path.name,
                                      params | {"client": sender_name(user)[:60]})
        except EngineError as err:
            if err.down and queued:
                raise
            if err.down:
                self.jobs.enqueue({"chat": chat, "message_id": message.get("message_id", 0),
                                   "user": {k: user.get(k) for k in ("id", "first_name", "last_name", "username")},
                                   "path": str(path), "params": params})
                self.reply(message, ENGINE_DOWN)
                self.tell_operators(f"⏸ LoomLab band hai: {sender_name(user)} ka design ({path.name}) queue me hai "
                                    f"({len(self.jobs.queue)} ruke hue). Engine chalu karo, proof apne aap jaayega.")
                return None
            self.reply(message, ENGINE_FAILED.format(why=err))
            self.tell_operators(f"⚠️ {sender_name(user)} ka design ({path.name}) auto mode me nahi "
                                f"chala: {err}\nFile: {path}")
            return None
        job_id = report["job_id"]
        try:
            proof = self.engine.fetch(f"/api/image/{report['reduced_id']}?max_side=1600")
        except EngineError as err:
            # the job is made: whatever went wrong now is reported, never queued
            # to run again (that would be a second job)
            self.reply(message, ENGINE_FAILED.format(why=err))
            self.tell_operators(f"⚠️ {sender_name(user)} ka job {job_id[:8]} bana, par proof nahi mila: {err}\n"
                                f"Jobs page par dekho. File: {path}")
            return None
        job = {"client_chat": chat, "client_id": user.get("id"), "client_name": sender_name(user),
               "design": str(path), "params": params, "status": report["status"], "stage": "sent",
               "at": self.now().strftime("%Y-%m-%d %H:%M")}
        if report["status"] == "needs_review" and self.settings.operators:
            job["stage"] = "review"
            self.jobs.put(job_id, job)
            reached = 0
            for op in self.settings.operators:
                try:   # one operator who never opened the bot must not block the rest
                    self._send_result(op, report, proof, for_operator=True, buttons=[
                        [{"text": "📤 Client ko bhejo", "callback_data": f"send:{job_id}"},
                         {"text": "❌ Rok do", "callback_data": f"rej:{job_id}"}]],
                        header=f"👤 {sender_name(user)} · {path.name}")
                    reached += 1
                except TelegramError as err:
                    print(f"Operator {op} tak review nahi gaya: {err}")
            if reached:
                self.reply(message, HELD)
                return job_id
            # no operator could be reached: the client gets it, marked for a check
        self.jobs.put(job_id, job)
        self._send_to_client(job_id, job, report, proof)
        return job_id

    def _send_to_client(self, job_id: str, job: dict, report: dict, proof: bytes) -> None:
        self._send_result(job["client_chat"], report, proof, buttons=[
            [{"text": "✅ Approve", "callback_data": f"ok:{job_id}"},
             {"text": "✏️ Change", "callback_data": f"chg:{job_id}"}]])
        job["stage"] = "sent"
        self.jobs.put(job_id, job)
        self._stage(job_id, "sent", "bot")

    def _send_result(self, chat: int, report: dict, proof: bytes, buttons, for_operator=False, header=""):
        caption = ((header + "\n") if header else "") + summary(report, for_operator)
        if report["status"] == "needs_review" and not for_operator:
            caption += "\nℹ️ Hamari team bhi ise ek baar check karegi."
        self.api.send_file("sendPhoto", "photo", "proof.png", proof, "image/png",
                           chat_id=chat, caption=caption[:1024])
        if report.get("quote"):
            try:
                quote = self.engine.fetch(report["quote"]["image_url"])
                self.api.send_file("sendPhoto", "photo", "quote.png", quote, "image/png", chat_id=chat)
            except EngineError as err:   # the proof and the buttons still go
                print(f"Quote image nahi mili: {err}")
        self.api.call("sendMessage", chat_id=chat, text=ASK if not for_operator else "Kya karna hai?",
                      reply_markup={"inline_keyboard": buttons})

    def _stage(self, job_id: str, stage: str, by: str = "") -> None:
        """Best effort: the dashboard showing a stage late never blocks a client."""
        try:
            self.engine.stage(job_id, stage, by)
        except (EngineError, AttributeError) as err:
            print(f"Dashboard par {job_id[:8]} = {stage} nahi likh paaye: {err}")

    def tell_operators(self, text: str) -> None:
        for op in self.settings.operators:
            try:
                self.api.call("sendMessage", chat_id=op, text=text)
            except (TelegramError, OSError) as err:
                print(f"Operator {op} ko message nahi gaya: {err}")

    def handle_button(self, cq: dict) -> None:
        """A press on Approve / Change (client) or Send / Reject (operator)."""
        action, _, job_id = (cq.get("data") or "").partition(":")
        uid = cq["from"]["id"]
        job = self.jobs.get(job_id)

        def answer(text=""):
            self.api.call("answerCallbackQuery", callback_query_id=cq["id"], text=text)

        if job is None:
            return answer(GONE)
        client_action = action in ("ok", "chg")
        allowed = (uid == job["client_id"] or uid in self.settings.operators) if client_action \
            else uid in self.settings.operators
        if not allowed:
            return answer("Ye aapka order nahi hai.")
        if job["stage"] != ("sent" if client_action else "review"):
            return answer("Is order par faisla ho chuka hai.")
        try:
            answer()
        except TelegramError as err:
            # a press answered late (the bot was busy with a job) is still a press
            print(f"Button ka jawab der se: {err}")
        msg = cq.get("message")
        if msg:   # the buttons have done their job: take them away
            try:
                self.api.call("editMessageReplyMarkup", chat_id=msg["chat"]["id"],
                              message_id=msg["message_id"], reply_markup={"inline_keyboard": []})
            except TelegramError as err:
                print(f"Buttons hat nahi paaye: {err}")
        client = {"chat": {"id": job["client_chat"]}, "message_id": 0}
        if action == "ok":
            self.approve(job_id, job, client)
        elif action == "chg":
            self.jobs.await_change(job["client_chat"], job_id)
            self.reply(client, ASK_CHANGE)
        elif action == "send":
            try:
                report = json.loads(self.engine.fetch(f"/api/auto/{job_id}"))
                proof = self.engine.fetch(f"/api/image/{report['reduced_id']}?max_side=1600")
            except EngineError as err:
                self.tell_operators(f"Order {job_id[:8]} nahi bhej paaye: {err}")
                return
            self._send_to_client(job_id, job, report, proof)
        elif action == "rej":
            job["stage"] = "rejected"
            self.jobs.put(job_id, job)
            self._stage(job_id, "rejected", f"operator {uid}")
            self.reply(client, REJECTED)

    def approve(self, job_id: str, job: dict, client: dict) -> None:
        try:
            data = self.engine.fetch(f"/api/auto/{job_id}/package")
        except EngineError as err:
            self.tell_operators(f"Order {job_id[:8]} approve hua par zip nahi mili: {err}\n"
                                f"Design: {job['design']}")
            data = None
        if data is not None:
            day = self.folder / "approved" / self.now().strftime("%Y-%m-%d")
            day.mkdir(parents=True, exist_ok=True)
            zpath = unique_path(day / safe_name(f"{Path(job['design']).stem}_{job_id[:8]}.zip"))
            zpath.write_bytes(data)
            job["package"] = str(zpath)
            text = f"✅ {job['client_name']} ne order approve kiya ({Path(job['design']).name})."
            for op in self.settings.operators:
                try:
                    if len(data) <= 49 * 1024 * 1024:   # the Bot API's upload limit is 50 MB
                        self.api.send_file("sendDocument", "document", zpath.name, data,
                                           "application/zip", chat_id=op, caption=text)
                    else:
                        self.api.call("sendMessage", chat_id=op,
                                      text=f"{text}\nZip badi hai ({len(data) // 2**20} MB), PC par hai: {zpath}")
                except TelegramError as err:
                    print(f"Operator {op} ko zip nahi gayi: {err}")
        job["stage"] = "approved"
        self.jobs.put(job_id, job)
        self._stage(job_id, "approved", job["client_name"])
        self.reply(client, APPROVED)

    def handle_change(self, message: dict, user: dict, job_id: str, text: str) -> None:
        job = self.jobs.get(job_id)
        change = parse_request(text)
        if not change or job is None:
            self.jobs.await_change(message["chat"]["id"], None)
            self.tell_operators(f"✏️ {sender_name(user)} ne badlav maanga (order {job_id[:8]}): \"{text}\""
                                + (f"\nDesign: {job['design']}" if job else ""))
            self.reply(message, CHANGE_TO_TEAM)
            return
        path = Path(job["design"])
        if not path.exists():
            self.jobs.await_change(message["chat"]["id"], None)
            self.reply(message, GONE)
            return
        # A network drop before the engine has made the new job leaves the
        # message to be fetched again, so the change is still made. Once the
        # job exists, a failure is reported, never retried: a retry would run
        # a second job (as for a new design).
        made_before = set(self.jobs.data["jobs"])
        try:
            self.process(message, user, path, job["params"] | change)
        except (OSError, TelegramError) as err:
            if set(self.jobs.data["jobs"]) == made_before:
                raise
            print(f"Badlav ({job_id[:8]}) ka naya proof client tak nahi gaya: {err!r}")
            self.tell_operators(f"⚠️ {job['client_name']} ka badlav ho gaya, par naya proof client tak "
                                f"nahi gaya ({err}). Order: orders.json")
        self.jobs.await_change(message["chat"]["id"], None)
        job["stage"] = "changed"
        self.jobs.put(job_id, job)
        self._stage(job_id, "changed", job["client_name"])

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
    print(f"Proof aur quote: {'LoomLab engine ' + settings.engine if settings.engine else 'band (ENGINE=off)'}")
    if bot.jobs.queue:
        print(f"{len(bot.jobs.queue)} design queue me hain (engine band tha) — engine milte hi chalenge.")
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
