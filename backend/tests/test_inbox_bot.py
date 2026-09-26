"""The Telegram inbox, driven through a fake Telegram (no network)."""
import csv
import urllib.error
from datetime import datetime
from pathlib import Path

import pytest

from app.inbox_bot import (MAX_DOWNLOAD, SETTINGS_TEMPLATE, InboxBot, Settings,
                           SettingsError, TelegramError, load_settings, safe_name,
                           unique_path)

TOKEN = "123456789:AAH" + "x" * 32
WHEN = int(datetime(2026, 9, 26, 14, 5, 9).timestamp())


class FakeTelegram:
    def __init__(self, files=None, updates=None):
        self.files = files or {}          # file_id -> bytes
        self.updates = list(updates or [])
        self.sent: list[dict] = []
        self.fail_download: Exception | None = None

    def call(self, method, wait=30, **params):
        if method == "getUpdates":
            return [u for u in self.updates if u["update_id"] >= params["offset"]]
        if method == "getFile":
            if params["file_id"] not in self.files:
                raise TelegramError(400, "Bad Request: invalid file_id")
            return {"file_id": params["file_id"], "file_path": f"docs/{params['file_id']}.jpg"}
        if method == "sendMessage":
            self.sent.append(params)
            return {}
        raise AssertionError(method)

    def download(self, file_path):
        if self.fail_download:
            raise self.fail_download
        return self.files[Path(file_path).stem]


def msg(mid=1, uid=42, **extra):
    return {"message_id": mid, "date": WHEN, "chat": {"id": uid},
            "from": {"id": uid, "first_name": "Ravi", "last_name": "Kumar"}, **extra}


def doc(file_id, name, size=100):
    return {"file_id": file_id, "file_name": name, "file_size": size}


def bot_in(tmp_path, api, allowed=()):
    return InboxBot(api, Settings(TOKEN, tmp_path / "inbox", set(allowed)))


def test_a_document_is_saved_with_its_name_under_the_day(tmp_path):
    api = FakeTelegram({"f1": b"PNGDATA"})
    path = bot_in(tmp_path, api).handle(msg(document=doc("f1", "rose border.png"),
                                            caption="order 17"))
    assert path == tmp_path / "inbox" / "2026-09-26" / "140509_Ravi Kumar_rose border.png"
    assert path.read_bytes() == b"PNGDATA"
    assert "Save ho gaya" in api.sent[-1]["text"]
    assert api.sent[-1]["reply_parameters"]["message_id"] == 1
    rows = list(csv.reader((tmp_path / "inbox" / "inbox-log.csv")
                           .open(encoding="utf-8-sig")))
    assert rows[0] == ["time", "sender", "telegram_id", "file", "caption"]
    assert rows[1][1:] == ["Ravi Kumar", "42",
                           str(Path("2026-09-26") / path.name), "order 17"]


def test_a_photo_saves_the_largest_size_and_warns_about_compression(tmp_path):
    api = FakeTelegram({"small": b"s", "big": b"BIG"})
    photos = [{"file_id": "small", "width": 90, "height": 60, "file_size": 1},
              {"file_id": "big", "width": 1280, "height": 853, "file_size": 3}]
    path = bot_in(tmp_path, api).handle(msg(photo=photos))
    assert path.read_bytes() == b"BIG"
    assert path.suffix == ".jpg"
    assert "File ki tarah" in api.sent[-1]["text"]


def test_the_same_name_twice_is_kept_as_two_files(tmp_path):
    api = FakeTelegram({"a": b"one", "b": b"two"})
    bot = bot_in(tmp_path, api)
    first = bot.handle(msg(1, document=doc("a", "d.png")))
    second = bot.handle(msg(2, document=doc("b", "d.png")))
    assert first != second
    assert first.read_bytes() == b"one" and second.read_bytes() == b"two"


def test_text_and_commands_get_help_not_a_file(tmp_path):
    api = FakeTelegram()
    bot = bot_in(tmp_path, api)
    assert bot.handle(msg(text="/start")) is None
    assert "File / Document" in api.sent[-1]["text"]
    assert bot.handle(msg(text="hello")) is None
    assert "photo ya file" in api.sent[-1]["text"]
    assert bot.handle(msg(text="/id@loom_bot")) is None
    assert api.sent[-1]["text"].endswith("42")
    assert not (tmp_path / "inbox").exists() or not any((tmp_path / "inbox").rglob("*.*"))


def test_a_file_over_twenty_mb_is_refused_politely(tmp_path):
    api = FakeTelegram({"f": b"x"})
    assert bot_in(tmp_path, api).handle(
        msg(document=doc("f", "huge.tif", MAX_DOWNLOAD + 1))) is None
    assert "20 MB" in api.sent[-1]["text"]


def test_only_allowed_senders_are_saved_but_anyone_can_ask_their_id(tmp_path):
    api = FakeTelegram({"f": b"x"})
    bot = bot_in(tmp_path, api, allowed={7})
    assert bot.handle(msg(uid=42, document=doc("f", "a.png"))) is None
    assert "42" in api.sent[-1]["text"]
    bot.handle(msg(uid=42, text="/id"))
    assert api.sent[-1]["text"] == "Aapki Telegram id: 42"
    assert bot.handle(msg(uid=7, document=doc("f", "a.png"))) is not None


def test_polling_saves_each_message_once_and_remembers_where_it_was(tmp_path):
    updates = [{"update_id": 500, "message": msg(1, document=doc("a", "a.png"))},
               {"update_id": 501, "message": msg(2, document=doc("b", "b.png"))}]
    api = FakeTelegram({"a": b"A", "b": b"B"}, updates)
    assert bot_in(tmp_path, api).poll_once() == 2
    # A restarted bot carries on after the last message, not from the start.
    assert bot_in(tmp_path, api).poll_once() == 0
    assert len(list((tmp_path / "inbox").rglob("*.png"))) == 2


def test_a_network_drop_mid_download_retries_the_same_message(tmp_path):
    updates = [{"update_id": 9, "message": msg(document=doc("a", "a.png"))}]
    api = FakeTelegram({"a": b"A"}, updates)
    api.fail_download = urllib.error.URLError("connection reset")
    bot = bot_in(tmp_path, api)
    with pytest.raises(urllib.error.URLError):
        bot.poll_once()
    api.fail_download = None
    assert bot.poll_once() == 1
    assert [p.read_bytes() for p in (tmp_path / "inbox").rglob("*.png")] == [b"A"]


def test_a_message_that_cannot_be_saved_is_answered_and_skipped(tmp_path):
    updates = [{"update_id": 9, "message": msg(document=doc("missing", "a.png"))},
               {"update_id": 10, "message": msg(2, document=doc("b", "b.png"))}]
    api = FakeTelegram({"b": b"B"}, updates)
    bot = bot_in(tmp_path, api)
    assert bot.poll_once() == 2
    assert "save nahi ho paya" in api.sent[0]["text"]
    assert bot.poll_once() == 0
    assert len(list((tmp_path / "inbox").rglob("*.png"))) == 1


def test_file_names_are_safe_on_windows():
    assert safe_name('a<b>:c"d/e\\f|g?h*.png') == "a_b_c_d_e_f_g_h_.png"
    assert safe_name("CON.png") == "_CON.png"
    assert safe_name("...") == "file"
    assert safe_name("x" * 300 + ".tif").endswith(".tif")
    assert len(safe_name("x" * 300 + ".tif")) <= 80


def test_unique_path_counts_up(tmp_path):
    (tmp_path / "d.png").write_bytes(b"")
    (tmp_path / "d_2.png").write_bytes(b"")
    assert unique_path(tmp_path / "d.png") == tmp_path / "d_3.png"


def test_settings_file_is_created_then_read(tmp_path):
    path = tmp_path / "telegram-bot.txt"
    with pytest.raises(SettingsError, match="bana di"):
        load_settings(path, tmp_path / "Inbox")
    assert path.read_text(encoding="utf-8") == SETTINGS_TEMPLATE
    with pytest.raises(SettingsError, match="khaali"):
        load_settings(path, tmp_path / "Inbox")

    path.write_text(SETTINGS_TEMPLATE.replace("TOKEN=", f"TOKEN= {TOKEN} ")
                    .replace("ALLOWED=", "ALLOWED=11, 22"), encoding="utf-8-sig")
    s = load_settings(path, tmp_path / "Inbox")
    assert s.token == TOKEN and s.folder == tmp_path / "Inbox" and s.allowed == {11, 22}

    path.write_text("TOKEN=not-a-token\n", encoding="utf-8")
    with pytest.raises(SettingsError, match="sahi nahi"):
        load_settings(path, tmp_path / "Inbox")
