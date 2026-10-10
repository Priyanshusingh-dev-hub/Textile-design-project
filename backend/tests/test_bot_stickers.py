"""Loomy's stickers in the Telegram bot (MASCOT=on): after the right texts only, silent, sent as
a file once and by Telegram's id after that, and never in an order's way."""
import json
from datetime import datetime

import pytest
from PIL import Image

from app.inbox_bot import (APPROVED, ASK, ENGINE_DOWN, HELD, SETTINGS_TEMPLATE, STICKER_EMOJI, STICKERS_DIR,
                           WELCOME, WORKING, InboxBot, Settings, SettingsError, TelegramError, load_settings)
from app.bot_orders import EngineError

TOKEN = "123456789:AAH" + "x" * 32
WHEN = int(datetime(2026, 10, 10, 11, 0, 0).timestamp())
CLIENT, OPERATOR = 42, 7


class FakeTelegram:
    """Every message, photo and sticker the bot sends, in order."""

    def __init__(self):
        self.out = []          # (kind, chat, what): kind text | file | sticker
        self.uploads = []      # the params of each sticker sent as a file
        self.fail = {}         # method -> exception, raised every time

    def call(self, method, wait=30, **params):
        if method in self.fail:
            raise self.fail[method]
        if method == "getFile":
            return {"file_path": "documents/design.png"}
        if method == "sendMessage":
            self.out.append(("text", params["chat_id"], params["text"]))
        elif method == "sendSticker":
            self.out.append(("sticker", params["chat_id"], params["sticker"]))
            assert params["disable_notification"] is True
        return {}

    def download(self, file_path):
        return b"PNG-DESIGN"

    def send_file(self, method, field, filename, data, ctype, **params):
        if method in self.fail:
            raise self.fail[method]
        if method == "sendSticker":
            assert ctype == "image/webp" and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
            self.uploads.append(params)
            name = filename.removesuffix(".webp")
            self.out.append(("sticker", params["chat_id"], name))
            return {"sticker": {"file_id": f"STK-{name}"}}
        self.out.append(("file", params["chat_id"], filename))
        return {}

    def to(self, chat):
        return [(k, w) for k, c, w in self.out if c == chat]


class FakeEngine:
    def __init__(self, status="auto_ok", down=False):
        self.status, self.down = status, down

    def auto(self, data, filename, params):
        if self.down:
            raise EngineError("not reachable", down=True)
        self.last = {"job_id": "1" * 32, "status": self.status, "accuracy": 91.2, "reduced_id": "a" * 32,
                     "inks": [{"name": "Ink 1", "hex": "#DE1464", "coverage": 60.0}],
                     "print": {"width_in": 4.83, "height_in": 3.62, "dpi": 300},
                     "warnings": [{"code": "low_match", "blocking": True, "message": "82% match."}]
                     if self.status == "needs_review" else [],
                     "quote": {"meters": 500, "total": 69577, "per_meter": 139, "currency": "₹",
                               "image_url": "/api/image/" + "b" * 32}}
        return self.last

    def stage(self, *a):
        pass

    def fetch(self, path):
        if path.endswith("/package"):
            return b"PK-ZIP"
        if path.startswith("/api/auto/"):
            return json.dumps(self.last).encode()
        return b"PNG-IMAGE"


def bot(tmp_path, mascot=True, engine=None):
    s = Settings(TOKEN, tmp_path / "inbox", operators={OPERATOR}, engine="http://x", mascot=mascot)
    tg = FakeTelegram()
    return InboxBot(tg, s, engine=engine or FakeEngine()), tg


def start(uid=CLIENT):
    return {"message_id": 1, "date": WHEN, "chat": {"id": uid}, "from": {"id": uid}, "text": "/start"}


def design(caption="500 m"):
    return {"message_id": 2, "date": WHEN, "chat": {"id": CLIENT}, "caption": caption,
            "from": {"id": CLIENT, "first_name": "Ravi"},
            "document": {"file_id": "f1", "file_name": "rose.png", "file_size": 10}}


def press(b, who, data):
    b.handle_button({"id": "cb1", "from": {"id": who}, "data": data,
                     "message": {"chat": {"id": who}, "message_id": 99}})


def test_mascot_is_off_unless_the_mill_says_on(tmp_path):
    assert "\nMASCOT=off\n" in SETTINGS_TEMPLATE
    f = tmp_path / "telegram-bot.txt"
    f.write_text(f"TOKEN={TOKEN}\n", encoding="utf-8")
    assert load_settings(f, tmp_path).mascot is False                  # an older settings file: off
    for word, on in (("on", True), ("haan", True), ("off", False), ("", False)):
        f.write_text(f"TOKEN={TOKEN}\nMASCOT={word}\n", encoding="utf-8")
        assert load_settings(f, tmp_path).mascot is on
    f.write_text(f"TOKEN={TOKEN}\nMASCOT=maybe\n", encoding="utf-8")
    with pytest.raises(SettingsError):
        load_settings(f, tmp_path)


def test_off_sends_no_sticker_anywhere(tmp_path):
    b, tg = bot(tmp_path, mascot=False)
    b.handle(start())
    b.handle(design())
    press(b, CLIENT, "ok:" + "1" * 32)
    assert not [o for o in tg.out if o[0] == "sticker"]
    assert "stickers" not in b.jobs.data


def test_start_waves_after_the_welcome_once_uploaded_then_by_id(tmp_path):
    b, tg = bot(tmp_path)
    b.handle(start())
    assert tg.to(CLIENT) == [("text", WELCOME), ("sticker", "wave")]
    assert tg.uploads == [{"chat_id": CLIENT, "emoji": STICKER_EMOJI["wave"], "disable_notification": "true"}]
    b.handle(start())
    assert tg.to(CLIENT)[-1] == ("sticker", "STK-wave")                  # Telegram's id, not a second upload
    assert len(tg.uploads) == 1
    assert json.loads((tmp_path / "inbox" / "orders.json").read_text(encoding="utf-8"))["stickers"] == {"wave": "STK-wave"}


def test_an_order_works_then_gets_a_thumbs_up_and_nothing_sits_between_proof_quote_and_buttons(tmp_path):
    b, tg = bot(tmp_path)
    b.handle(design())
    saved, *rest = tg.to(CLIENT)
    assert saved[1].startswith("✅ Save ho gaya")
    assert rest == [("text", WORKING), ("sticker", "working"), ("file", "proof.png"), ("file", "quote.png"), ("text", ASK)]
    press(b, CLIENT, "ok:" + "1" * 32)
    assert tg.to(CLIENT)[-2:] == [("text", APPROVED), ("sticker", "thumbs_up")]
    assert not [w for k, w in tg.to(OPERATOR) if k == "sticker"]          # operators get the facts only


def test_bad_news_gets_no_sticker_of_its_own(tmp_path):
    b, tg = bot(tmp_path, engine=FakeEngine(status="needs_review"))
    b.handle(design())
    assert tg.to(CLIENT)[1:] == [("text", WORKING), ("sticker", "working"), ("text", HELD)]
    b, tg = bot(tmp_path / "2", engine=FakeEngine(down=True))
    b.handle(design())
    assert tg.to(CLIENT)[-1] == ("text", ENGINE_DOWN)


@pytest.mark.parametrize("failure", [TelegramError(500, "Internal"), TelegramError(400, "Bad sticker"),
                                     OSError("network down")])
def test_a_sticker_that_fails_never_stops_an_order(tmp_path, failure):
    b, tg = bot(tmp_path)
    tg.fail["sendSticker"] = failure
    b.handle(design())
    press(b, CLIENT, "ok:" + "1" * 32)
    assert ("file", "proof.png") in tg.to(CLIENT) and ("text", APPROVED) in tg.to(CLIENT)
    assert b.jobs.get("1" * 32)["stage"] == "approved"


def test_an_id_from_another_bot_is_replaced_by_the_file_again(tmp_path):
    b, tg = bot(tmp_path)
    b.jobs.data["stickers"] = {"wave": "OLD-ID"}
    real_call = tg.call

    def call(method, wait=30, **params):
        if method == "sendSticker" and params["sticker"] == "OLD-ID":
            raise TelegramError(400, "Bad Request: wrong file identifier")
        return real_call(method, wait, **params)
    tg.call = call
    b.handle(start())
    assert tg.to(CLIENT)[-1] == ("sticker", "wave") and b.jobs.data["stickers"]["wave"] == "STK-wave"


def test_the_sticker_files_are_telegram_ready():
    for name in STICKER_EMOJI:
        path = STICKERS_DIR / f"{name}.webp"
        assert path.stat().st_size < 512 * 1024, name                  # Telegram's static sticker limit
        with Image.open(path) as img:
            assert img.format == "WEBP" and max(img.size) == 512 and img.mode == "RGBA", name
            assert img.getchannel("A").getextrema()[0] == 0, name         # a transparent background
