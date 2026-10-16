"""The bot's order desk: proof and quote back to the client, Approve / Change,
operator review — driven through a fake Telegram and a fake engine."""
import io
import json
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.bot_orders import EngineError, multipart, parse_request, summary
from app.inbox_bot import TelegramError, APPROVED, ASK_CHANGE, CHANGE_TO_TEAM, ENGINE_DOWN, HELD, REJECTED, InboxBot, Settings

TOKEN = "123456789:AAH" + "x" * 32
WHEN = int(datetime(2026, 9, 27, 11, 0, 0).timestamp())
CLIENT, OPERATOR = 42, 7


class FakeTelegram:
    def __init__(self):
        self.calls = []      # (method, params)
        self.files = []      # (method, chat_id, caption)
        self.fail = None     # (method, chat_id or None, exception) to raise once matched

    def _maybe_fail(self, method, chat):
        if self.fail and self.fail[0] == method and self.fail[1] in (None, chat):
            err, self.fail = self.fail[2], None
            raise err

    def call(self, method, wait=30, **params):
        self._maybe_fail(method, params.get("chat_id"))
        self.calls.append((method, params))
        if method == "getFile":
            return {"file_path": "documents/design.png"}
        return {}

    def download(self, file_path):
        return b"PNG-DESIGN"

    def send_file(self, method, field, filename, data, ctype, **params):
        self._maybe_fail(method, params["chat_id"])
        self.files.append((method, params["chat_id"], params.get("caption", ""), filename))
        if "reply_markup" in params:          # a photo with buttons under it
            self.calls.append((method, params))
        return {}

    def texts(self, chat):
        return [p["text"] for m, p in self.calls if m == "sendMessage" and p["chat_id"] == chat]

    def buttons(self, chat):
        return [b["callback_data"] for m, p in self.calls if m in ("sendMessage", "sendPhoto") and p["chat_id"] == chat
                and "reply_markup" in p for row in p["reply_markup"]["inline_keyboard"] for b in row]


class FakeEngine:
    def __init__(self, status="auto_ok", down=False):
        self.status, self.down = status, down
        self.runs, self.stages = [], []

    def _report(self, n, params):
        rep = {"job_id": f"{n:032x}", "status": self.status, "accuracy": 91.2, "reduced_id": "a" * 32,
               "inks": [{"name": "Ink 1", "hex": "#DE1464", "coverage": 60.0}],
               "print": {"width_in": params.get("width_in") or 4.83, "height_in": 3.62, "dpi": 300},
               "warnings": [{"code": "low_match", "blocking": True, "message": "82% match."}]
               if self.status == "needs_review" else []}
        if params.get("meters"):
            rep["quote"] = {"meters": params["meters"], "total": 69577, "per_meter": 139, "currency": "₹",
                            "image_url": "/api/image/" + "b" * 32}
        return rep

    def auto(self, data, filename, params):
        if self.down:
            raise EngineError("not reachable", down=True)
        self.runs.append(params)
        rep = self._report(len(self.runs), params)
        self.last = rep
        return rep

    def stage(self, job_id, stage, by="", note=""):
        self.stages.append((job_id, stage))

    def fetch(self, path):
        if getattr(self, "quote_broken", False) and path.startswith("/api/image/b"):
            raise EngineError("image gone")
        if path.endswith("/package"):
            return b"PK-ZIP"
        if path.startswith("/api/auto/"):
            return json.dumps(self.last).encode()
        return b"PNG-IMAGE"


def bot(tmp_path, engine, operators=(OPERATOR,), meters=None):
    s = Settings(TOKEN, tmp_path / "inbox", operators=set(operators), engine="http://x", meters=meters)
    tg = FakeTelegram()
    return InboxBot(tg, s, engine=engine), tg


def design_msg(caption="", mid=1):
    return {"message_id": mid, "date": WHEN, "chat": {"id": CLIENT}, "caption": caption,
            "from": {"id": CLIENT, "first_name": "Ravi"},
            "document": {"file_id": "f1", "file_name": "rose.png", "file_size": 10}}


def press(b, who, data, chat=None):
    b.handle_button({"id": "cb1", "from": {"id": who}, "data": data,
                     "message": {"chat": {"id": chat or who}, "message_id": 99}})


def test_a_clean_design_comes_back_to_the_client_with_proof_quote_and_buttons(tmp_path):
    eng = FakeEngine()
    b, tg = bot(tmp_path, eng)
    b.handle(design_msg("500 m, 30 inch"))
    assert eng.runs[0] | {} == {"width_in": 30.0, "meters": 500.0, "client": "Ravi"}
    sent = [(m, chat, name) for m, chat, _, name in tg.files]
    assert sent == [("sendPhoto", CLIENT, "proof.png"), ("sendPhoto", CLIENT, "quote.png")]
    assert "₹69,577" in tg.files[0][2] and "30 × 3.62 inch" in tg.files[0][2]
    job = eng.last["job_id"]
    assert tg.buttons(CLIENT) == [f"ok:{job}", f"chg:{job}", f"cw:{job}"]
    assert b.jobs.get(job)["stage"] == "sent"


def test_the_default_run_is_quoted_when_the_caption_has_none(tmp_path):
    eng = FakeEngine()
    b, tg = bot(tmp_path, eng, meters=250)
    b.handle(design_msg(""))
    assert eng.runs[0]["meters"] == 250 and eng.runs[0]["width_in"] is None


def test_approve_saves_the_package_and_sends_it_to_the_operator(tmp_path):
    eng = FakeEngine()
    b, tg = bot(tmp_path, eng)
    b.handle(design_msg())
    job = eng.last["job_id"]
    press(b, CLIENT, f"ok:{job}")
    saved = list((tmp_path / "inbox" / "approved").rglob("*.zip"))
    assert len(saved) == 1 and saved[0].read_bytes() == b"PK-ZIP"
    assert ("sendDocument", OPERATOR) in [(m, c) for m, c, _, _ in tg.files]
    assert APPROVED in tg.texts(CLIENT)
    assert b.jobs.get(job)["stage"] == "approved"
    assert eng.stages == [(job, "sent"), (job, "approved")]     # the dashboard follows
    # the buttons are taken away, and a second press does nothing
    assert any(m == "editMessageReplyMarkup" for m, _ in tg.calls)
    press(b, CLIENT, f"ok:{job}")
    assert len(list((tmp_path / "inbox" / "approved").rglob("*.zip"))) == 1


def test_change_in_words_makes_a_new_proof_keeping_the_rest(tmp_path):
    eng = FakeEngine()
    b, tg = bot(tmp_path, eng)
    b.handle(design_msg("500 m"))
    press(b, CLIENT, f"chg:{eng.last['job_id']}")
    assert ASK_CHANGE in tg.texts(CLIENT)
    b.handle({"message_id": 5, "date": WHEN, "chat": {"id": CLIENT}, "from": {"id": CLIENT, "first_name": "Ravi"},
              "text": "6 inks aur 40 inch"})
    assert eng.runs[1] == {"width_in": 40.0, "meters": 500.0, "colors": 6, "client": "Ravi"}
    assert sum(m == "sendPhoto" and c == CLIENT and n == "proof.png" for m, c, _, n in tg.files) == 2


def test_a_change_the_bot_cannot_read_goes_to_the_operator(tmp_path):
    eng = FakeEngine()
    b, tg = bot(tmp_path, eng)
    b.handle(design_msg())
    press(b, CLIENT, f"chg:{eng.last['job_id']}")
    b.handle({"message_id": 5, "date": WHEN, "chat": {"id": CLIENT}, "from": {"id": CLIENT, "first_name": "Ravi"},
              "text": "laal ko thoda gehra kar do"})
    assert len(eng.runs) == 1
    assert any("laal ko thoda gehra" in t for t in tg.texts(OPERATOR))
    assert CHANGE_TO_TEAM in tg.texts(CLIENT)
    # and the next plain text is not taken as another change
    b.handle({"message_id": 6, "date": WHEN, "chat": {"id": CLIENT}, "from": {"id": CLIENT}, "text": "ok"})
    assert len(eng.runs) == 1


def test_a_held_job_goes_to_the_operator_first(tmp_path):
    eng = FakeEngine(status="needs_review")
    b, tg = bot(tmp_path, eng)
    b.handle(design_msg())
    job = eng.last["job_id"]
    assert HELD in tg.texts(CLIENT) and tg.buttons(CLIENT) == []
    assert tg.buttons(OPERATOR) == [f"send:{job}", f"rej:{job}"]
    assert "match" in tg.files[0][2] and "Rukne ki wajah" in tg.files[0][2]
    # the client cannot release it; the operator can
    press(b, CLIENT, f"send:{job}", chat=CLIENT)
    assert tg.buttons(CLIENT) == []
    press(b, OPERATOR, f"send:{job}")
    assert tg.buttons(CLIENT) == [f"ok:{job}", f"chg:{job}", f"cw:{job}"]


def test_the_operator_can_stop_a_held_job(tmp_path):
    eng = FakeEngine(status="needs_review")
    b, tg = bot(tmp_path, eng)
    b.handle(design_msg())
    press(b, OPERATOR, f"rej:{eng.last['job_id']}")
    assert REJECTED in tg.texts(CLIENT)
    assert b.jobs.get(eng.last["job_id"])["stage"] == "rejected"


def test_without_an_operator_a_held_job_still_reaches_the_client(tmp_path):
    eng = FakeEngine(status="needs_review")
    b, tg = bot(tmp_path, eng, operators=())
    b.handle(design_msg())
    assert tg.buttons(CLIENT) == [f"ok:{eng.last['job_id']}", f"chg:{eng.last['job_id']}", f"cw:{eng.last['job_id']}"]
    assert "team bhi ise ek baar check" in tg.files[0][2]


def test_someone_else_cannot_approve_a_clients_order(tmp_path):
    eng = FakeEngine()
    b, tg = bot(tmp_path, eng)
    b.handle(design_msg())
    press(b, 555, f"ok:{eng.last['job_id']}")
    assert b.jobs.get(eng.last["job_id"])["stage"] == "sent"
    assert ("answerCallbackQuery", {"callback_query_id": "cb1", "text": "Ye aapka order nahi hai."}) in tg.calls


def test_with_the_engine_off_the_design_is_kept_and_the_operator_told(tmp_path):
    b, tg = bot(tmp_path, FakeEngine(down=True))
    path = b.handle(design_msg())
    assert path.exists()
    assert ENGINE_DOWN in tg.texts(CLIENT)
    assert any("queue me hai" in t for t in tg.texts(OPERATOR))
    assert len(b.jobs.queue) == 1


def test_designs_queued_while_the_engine_was_off_go_through_when_it_is_back(tmp_path):
    eng = FakeEngine(down=True)
    b, tg = bot(tmp_path, eng)
    b.handle(design_msg("500 m"))
    b.handle(design_msg("6 inks"))
    assert len(b.jobs.queue) == 2 and eng.runs == []
    assert b.retry_queue() == 0 and len(b.jobs.queue) == 2          # still off: both kept, in order
    b2, tg2 = bot(tmp_path, eng)                                      # the bot restarted meanwhile
    assert len(b2.jobs.queue) == 2
    eng.down = False
    assert b2.retry_queue() == 2 and b2.jobs.queue == []
    assert eng.runs[0]["meters"] == 500 and eng.runs[1]["colors"] == 6   # oldest first, settings kept
    assert [f[3] for f in tg2.files if f[1] == CLIENT].count("proof.png") == 2
    assert f"ok:{eng.last['job_id']}" in tg2.buttons(CLIENT)
    assert b2.retry_queue() == 0                                      # never run twice


def test_a_queued_design_whose_proof_is_lost_is_not_run_again(tmp_path):
    eng = FakeEngine(down=True)
    b, tg = bot(tmp_path, eng)
    b.handle(design_msg())
    eng.down = False
    tg.fail = ("sendPhoto", CLIENT, ConnectionError("reset"))
    b.retry_queue()
    assert len(eng.runs) == 1 and b.jobs.queue == []
    b.retry_queue()
    assert len(eng.runs) == 1
    assert any("proof client tak nahi gaya" in t for t in tg.texts(OPERATOR))


def test_the_queue_is_tried_from_the_poll_loop(tmp_path):
    eng = FakeEngine(down=True)
    b, tg = bot(tmp_path, eng)
    b.handle(design_msg())
    eng.down = False
    b.poll_once(timeout=0)
    assert len(eng.runs) == 1 and b.jobs.queue == []


def test_orders_survive_a_restart(tmp_path):
    eng = FakeEngine()
    b, _ = bot(tmp_path, eng)
    b.handle(design_msg())
    b2, tg2 = bot(tmp_path, eng)            # a new bot on the same folder
    press(b2, CLIENT, f"ok:{eng.last['job_id']}")
    assert APPROVED in tg2.texts(CLIENT)


@pytest.mark.parametrize("text,want", [
    ("500 m", {"meters": 500.0}), ("1200 meter, 30 inch", {"meters": 1200.0, "width_in": 30.0}),
    ('6 inks 24"', {"colors": 6, "width_in": 24.0}), ("8 rang", {"colors": 8}),
    ("300mtr", {"meters": 300.0}), ("0.2 mm dots", {}), ("namaste", {}), ("", {}),
])
def test_job_settings_are_read_from_plain_words(text, want):
    assert parse_request(text) == want


def test_the_bots_upload_is_accepted_by_the_real_engine():
    """The multipart body the bot builds, posted to the real API."""
    from app.main import app
    big = Image.new("RGB", (1200, 800), "#F4ECD8"); ImageDraw.Draw(big).ellipse([100, 100, 600, 600], fill="#8A1C1C")
    buf = io.BytesIO(); big.resize((600, 400), Image.LANCZOS).save(buf, "PNG")
    body, ctype = multipart({"meters": 100, "client": "Ravi ✓", "width_in": None},
                            [("file", 'rose "v2".png', buf.getvalue(), "image/png")])
    r = TestClient(app).post("/api/auto/upload", content=body, headers={"Content-Type": ctype})
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["quote"]["meters"] == 100 and len(rep["inks"]) == 2
    assert "Rukne" not in summary(rep) and "screens" in summary(rep)


# -- found in review: each of these once lost an order or doubled a job -------

@pytest.mark.parametrize("text,want", [
    ("1,500 m", {"meters": 1500.0}), ("2,000 meter", {"meters": 2000.0}),
    ("1,50,000 mtr", {"meters": 150000.0}), ("120 colours", {}), ("12.5 inks", {}),
])
def test_numbers_are_read_whole(text, want):
    assert parse_request(text) == want


def test_a_missing_quote_image_still_sends_the_proof_and_the_buttons(tmp_path):
    eng = FakeEngine(); eng.quote_broken = True
    b, tg = bot(tmp_path, eng)
    b.handle(design_msg("500 m"))
    assert [n for _, c, _, n in tg.files if c == CLIENT] == ["proof.png"]
    assert tg.buttons(CLIENT) == [f"ok:{eng.last['job_id']}", f"chg:{eng.last['job_id']}", f"cw:{eng.last['job_id']}"]


def test_a_failed_saved_reply_does_not_run_the_design_twice(tmp_path):
    eng = FakeEngine()
    b, tg = bot(tmp_path, eng)
    tg.fail = ("sendMessage", CLIENT, TelegramError(429, "Too Many Requests"))
    b.handle(design_msg())            # must not raise: raising would refetch and save it again
    tg.fail = None
    assert len(eng.runs) == 1 and len(list((tmp_path / "inbox").rglob("*.png"))) == 1


def test_one_unreachable_operator_does_not_block_the_others(tmp_path):
    eng = FakeEngine(status="needs_review")
    b, tg = bot(tmp_path, eng, operators=(OPERATOR, 8))
    tg.fail = ("sendPhoto", OPERATOR, TelegramError(403, "Forbidden: bot was blocked by the user"))
    b.handle(design_msg())
    assert tg.buttons(8) == [f"send:{eng.last['job_id']}", f"rej:{eng.last['job_id']}"]
    assert HELD in tg.texts(CLIENT)


def test_with_no_operator_reachable_the_client_still_gets_the_proof(tmp_path):
    eng = FakeEngine(status="needs_review")
    b, tg = bot(tmp_path, eng)
    tg.fail = ("sendPhoto", OPERATOR, TelegramError(403, "Forbidden"))
    b.handle(design_msg())
    assert tg.buttons(CLIENT) == [f"ok:{eng.last['job_id']}", f"chg:{eng.last['job_id']}", f"cw:{eng.last['job_id']}"]
    assert b.jobs.get(eng.last["job_id"])["stage"] == "sent"


def test_a_long_client_name_is_cut_to_what_the_engine_takes(tmp_path):
    eng = FakeEngine()
    b, _ = bot(tmp_path, eng)
    msg = design_msg(); msg["from"]["first_name"] = "R" * 80
    b.handle(msg)
    assert len(eng.runs[0]["client"]) == 60


def test_a_press_answered_too_late_still_approves(tmp_path):
    eng = FakeEngine()
    b, tg = bot(tmp_path, eng)
    b.handle(design_msg())
    tg.fail = ("answerCallbackQuery", None, TelegramError(400, "query is too old"))
    press(b, CLIENT, f"ok:{eng.last['job_id']}")
    assert b.jobs.get(eng.last["job_id"])["stage"] == "approved" and APPROVED in tg.texts(CLIENT)


def test_a_change_survives_a_network_drop_before_the_new_job_is_made(tmp_path):
    eng = FakeEngine()
    b, tg = bot(tmp_path, eng)
    b.handle(design_msg("500 m"))
    job = eng.last["job_id"]
    press(b, CLIENT, f"chg:{job}")
    change = {"message_id": 5, "date": WHEN, "chat": {"id": CLIENT}, "from": {"id": CLIENT, "first_name": "Ravi"},
              "text": "6 inks"}
    tg.fail = ("sendMessage", CLIENT, ConnectionError("reset"))   # "working on it" never leaves
    with pytest.raises(ConnectionError):
        b.handle(change)              # the poller leaves the message for the next try
    assert b.jobs.awaiting(CLIENT) == job and len(eng.runs) == 1
    tg.fail = None
    b.handle(change)                  # the retry makes the change
    assert b.jobs.awaiting(CLIENT) is None and eng.runs[-1]["colors"] == 6


def test_a_change_whose_proof_is_lost_is_reported_not_run_twice(tmp_path):
    eng = FakeEngine()
    b, tg = bot(tmp_path, eng)
    b.handle(design_msg("500 m"))
    job = eng.last["job_id"]
    press(b, CLIENT, f"chg:{job}")
    change = {"message_id": 5, "date": WHEN, "chat": {"id": CLIENT}, "from": {"id": CLIENT, "first_name": "Ravi"},
              "text": "6 inks"}
    tg.fail = ("sendPhoto", CLIENT, ConnectionError("reset"))     # the new job is made, its proof is lost
    b.handle(change)                  # no exception: the offset moves on
    assert len(eng.runs) == 2 and eng.runs[-1]["colors"] == 6
    assert b.jobs.awaiting(CLIENT) is None and b.jobs.get(job)["stage"] == "changed"
    assert any("badlav ho gaya" in t for t in tg.texts(OPERATOR))


def test_a_proof_lost_after_the_job_is_made_is_reported_not_queued(tmp_path):
    eng = FakeEngine()
    b, tg = bot(tmp_path, eng)
    real_fetch = eng.fetch
    def fetch(path):
        if path.startswith("/api/image/"):
            raise EngineError("engine restarted", down=True)
        return real_fetch(path)
    eng.fetch = fetch
    b.handle(design_msg())
    assert len(eng.runs) == 1 and b.jobs.queue == []
    assert any("proof nahi mila" in t for t in tg.texts(OPERATOR))


def test_an_engine_that_takes_too_long_is_not_closed(monkeypatch):
    import urllib.request
    from app.bot_orders import Engine
    def slow(req, timeout):
        raise TimeoutError("timed out")
    monkeypatch.setattr(urllib.request, "urlopen", slow)
    with pytest.raises(EngineError) as e:
        Engine("http://x", timeout=5).fetch("/api/health")
    assert not e.value.down and "longer than 5 s" in str(e.value)


# -- repeat orders, against the real engine ------------------------------------

def _real_bot(tmp_path, monkeypatch):
    from app.core import store
    from conftest import LocalEngine
    monkeypatch.setattr(store, "ROOT", tmp_path / "cache"); (tmp_path / "cache").mkdir()
    b, tg = bot(tmp_path, LocalEngine())
    im = Image.new("RGB", (300, 200), "#F4ECD8"); ImageDraw.Draw(im).ellipse([40, 40, 160, 160], fill="#8A1C1C")
    buf = io.BytesIO(); im.save(buf, "PNG")
    tg.download = lambda file_path: buf.getvalue()
    return b, tg


def _text_msg(text, mid=7):
    return {"message_id": mid, "date": WHEN, "chat": {"id": CLIENT}, "text": text,
            "from": {"id": CLIENT, "first_name": "Ravi"}}


def test_a_client_orders_the_same_design_again_without_new_screens(tmp_path, monkeypatch):
    b, tg = _real_bot(tmp_path, monkeypatch)
    b.handle(design_msg("500 m"))
    job = next(iter(b.jobs.data["jobs"]))
    press(b, CLIENT, f"ok:{job}")                         # approved: kept in the library
    b.handle(_text_msg("repeat karna hai"))
    assert "meter bhi likhiye" in tg.texts(CLIENT)[-1]
    b.handle(_text_msg("wahi design 1,200 m aur"))
    assert [f[3] for f in tg.files if f[1] == CLIENT][-1] == "quote.png"
    token = tg.buttons(CLIENT)[-1]
    assert token.startswith("rpk:")
    press(b, 555, token)                                  # a stranger cannot confirm it
    assert all("pakka ho gaya" not in t for t in tg.texts(CLIENT))
    press(b, CLIENT, token)
    assert "pakka ho gaya" in tg.texts(CLIENT)[-1]
    assert any("Repeat order pakka" in t and "1200 m" in t for t in tg.texts(OPERATOR))
    press(b, CLIENT, token)                               # a second press does nothing more
    assert sum("Repeat order pakka" in t for t in tg.texts(OPERATOR)) == 1


def _repeat_token(b, tg, text="repeat 700 m"):
    b.handle(_text_msg(text))
    token = tg.buttons(CLIENT)[-1]
    assert token.startswith("rpk:")
    return token


def _repeats(b, job):
    return next(d for d in b.engine.get("/api/library")["designs"] if d["id"] == job)["repeats"]


def test_a_design_approved_on_the_dashboard_can_be_ordered_again_with_no_operator(tmp_path, monkeypatch):
    b, tg = _real_bot(tmp_path, monkeypatch)
    b.settings.operators = set()                          # nobody on Telegram to tell
    b.handle(design_msg("500 m"))
    job = next(iter(b.jobs.data["jobs"]))
    b.engine.post(f"/api/jobs/{job}/stage", {"stage": "approved", "by": "Ravi (mill)"})
    press(b, CLIENT, _repeat_token(b, tg))
    assert "pakka ho gaya" in tg.texts(CLIENT)[-1]
    assert _repeats(b, job) == 1                          # the order is in LoomLab, not only in the chat
    assert b.engine.get("/api/stats?days=30")["repeat_meters"] == 700


def test_a_confirm_lost_on_the_way_to_the_client_is_finished_by_the_next_press(tmp_path, monkeypatch):
    b, tg = _real_bot(tmp_path, monkeypatch)
    b.handle(design_msg("500 m"))
    job = next(iter(b.jobs.data["jobs"]))
    press(b, CLIENT, f"ok:{job}")
    token = _repeat_token(b, tg)
    tg.fail = ("sendMessage", CLIENT, TelegramError(502, "Bad Gateway"))
    with pytest.raises(TelegramError):
        press(b, CLIENT, token)
    press(b, CLIENT, token)                               # the client presses again
    assert "pakka ho gaya" in tg.texts(CLIENT)[-1]
    assert _repeats(b, job) == 1                          # recorded once, however often it was sent
    press(b, CLIENT, token)
    assert _repeats(b, job) == 1 and sum("pakka ho gaya" in t for t in tg.texts(CLIENT)) == 1


def test_a_client_with_no_approved_design_is_asked_for_the_file(tmp_path, monkeypatch):
    b, tg = _real_bot(tmp_path, monkeypatch)
    b.handle(design_msg())                                # made, but never approved
    b.handle(_text_msg("repeat 500 m"))
    assert "approved design nahi mila" in tg.texts(CLIENT)[-1]


def test_with_several_approved_designs_the_client_picks_one(tmp_path, monkeypatch):
    b, tg = _real_bot(tmp_path, monkeypatch)
    for mid in (1, 2):
        b.handle(design_msg(f"{mid * 100} m", mid=mid))
        press(b, CLIENT, f"ok:{list(b.jobs.data['jobs'])[-1]}")
    b.handle(_text_msg("same design 800 m"))
    picks = [t for t in tg.buttons(CLIENT) if t.startswith("rpq:")]
    assert len(picks) == 2 and "Kaunsa design" in tg.texts(CLIENT)[-1]
    b.handle_button({"id": "cb2", "from": {"id": CLIENT}, "data": picks[0],
                     "message": {"chat": {"id": CLIENT}, "message_id": 99}})
    assert tg.buttons(CLIENT)[-1].startswith("rpk:")


# -- colourways: the client tries the same screens in other inks -----------------

def _photo_buttons(tg, chat):
    return [b["callback_data"] for m, p in tg.calls if m == "sendPhoto" and p["chat_id"] == chat
            for row in p["reply_markup"]["inline_keyboard"] for b in row]


def _colour_job(tmp_path, monkeypatch):
    b, tg = _real_bot(tmp_path, monkeypatch)
    b.handle(design_msg("500 m"))
    job = next(iter(b.jobs.data["jobs"]))
    if b.jobs.get(job)["stage"] != "sent":              # held for review: the operator sends it on
        press(b, OPERATOR, f"send:{job}")
    return b, tg, job


def _delivered(b, tg, job):
    """The colourway job the bot made from `job`, sent on to the client."""
    new = b.jobs.get(job)["colourway_job"]
    if b.jobs.get(new)["stage"] == "review":            # held: the operator sends it on
        press(b, OPERATOR, f"send:{new}")
    assert tg.buttons(CLIENT)[-3:] == [f"ok:{new}", f"chg:{new}", f"cw:{new}"]
    return new


def test_a_client_sees_their_design_in_other_colours_and_orders_in_them(tmp_path, monkeypatch):
    b, tg, job = _colour_job(tmp_path, monkeypatch)
    press(b, CLIENT, f"cw:{job}")
    ask = tg.texts(CLIENT)[-1]
    assert ask.startswith("🎨 Is design me 2 rang hain") and "1) " in ask and "Kapda: white" in ask
    b.handle(_text_msg("laal ko neela, kapda kala"))
    shot = [f for f in tg.files if f[1] == CLIENT][-1]
    assert shot[3] == "colourway.png" and "blue #1F5FBF" in shot[2] and "Kapda: black" in shot[2]
    b.handle(_text_msg("1 cream"))                      # builds on the last one shown
    shot = [f for f in tg.files if f[1] == CLIENT][-1]
    assert "cream #F2E8CF" in shot[2] and "blue #1F5FBF" in shot[2] and "Kapda: black" in shot[2]
    token = _photo_buttons(tg, CLIENT)[-1]
    assert token.startswith("cwk:")
    press(b, 555, token)                                # not theirs
    assert "colourway_job" not in b.jobs.get(job)
    press(b, CLIENT, token)
    new = _delivered(b, tg, job)
    rep = b.engine.get(f"/api/auto/{new}")
    assert rep["colourway_of"] == job and [i["hex"] for i in rep["inks"]] == ["#F2E8CF", "#1F5FBF"]
    assert rep["underbase"] and rep["quote"]["meters"] == 500          # black cloth: a white base under the inks
    assert b.engine.get(f"/api/auto/{job}")["stage"] == "changed"
    assert "Colourway: new job" in b.engine.get(f"/api/auto/{job}")["history"][-1]["note"]
    press(b, CLIENT, token)                             # a second press does nothing more
    assert len(b.jobs.data["jobs"]) == 2
    assert b.jobs.colours_for(CLIENT) is None           # back to normal messages
    press(b, CLIENT, f"ok:{job}")                       # the original proof is decided now
    assert b.engine.get(f"/api/auto/{job}")["stage"] == "changed"
    press(b, CLIENT, f"ok:{new}")                       # the colourway is approved like any job
    assert b.engine.get(f"/api/auto/{new}")["stage"] == "approved"
    assert any(d["id"] == new for d in b.engine.get("/api/library")["designs"])


def test_words_the_bot_cannot_read_are_asked_again_and_bas_stops(tmp_path, monkeypatch):
    b, tg, job = _colour_job(tmp_path, monkeypatch)
    press(b, CLIENT, f"cw:{job}")
    b.handle(_text_msg("kuch sundar sa"))
    assert tg.texts(CLIENT)[-1].startswith("Ye samajh nahi aaya: kuch sundar sa")
    b.handle(_text_msg("bas"))
    assert tg.texts(CLIENT)[-1] == "Theek hai, rang wahi rahenge."
    b.handle(_text_msg("laal ko neela"))                # an ordinary message again
    assert "colourway.png" not in [f[3] for f in tg.files if f[1] == CLIENT]


def test_colours_typed_after_change_are_shown_not_sent_to_the_team(tmp_path, monkeypatch):
    b, tg, job = _colour_job(tmp_path, monkeypatch)
    press(b, CLIENT, f"chg:{job}")
    b.handle(_text_msg("laal ki jagah mehroon"))
    assert [f[3] for f in tg.files if f[1] == CLIENT][-1] == "colourway.png"
    assert all("badlav maanga" not in t for t in tg.texts(OPERATOR))


def test_a_colourway_order_lost_on_the_way_is_finished_by_the_next_press(tmp_path, monkeypatch):
    b, tg, job = _colour_job(tmp_path, monkeypatch)
    press(b, CLIENT, f"cw:{job}")
    b.handle(_text_msg("2 navy"))
    token = _photo_buttons(tg, CLIENT)[-1]
    b.settings.operators = set()                        # straight to the client, held or not
    tg.fail = ("sendPhoto", CLIENT, TelegramError(502, "Bad Gateway"))
    with pytest.raises(TelegramError):
        press(b, CLIENT, token)                         # the job is made, its proof lost
    press(b, CLIENT, token)
    new = b.jobs.get(job)["colourway_job"]
    assert tg.buttons(CLIENT)[-3:] == [f"ok:{new}", f"chg:{new}", f"cw:{new}"]
    changed = [h for h in b.engine.get(f"/api/auto/{job}")["history"] if h["stage"] == "changed"]
    assert len(changed) == 1 and len(b.jobs.data["jobs"]) == 2       # one colourway job, recorded once


def test_a_client_sees_only_their_own_orders(tmp_path):
    eng = FakeEngine()
    b, tg = bot(tmp_path, eng)
    b.handle(_text_msg("mere order"))
    assert tg.texts(CLIENT)[-1].startswith("Abhi aapka koi order nahi hai")
    b.handle(design_msg("500 m"))
    press(b, CLIENT, f"ok:{eng.last['job_id']}")
    b.jobs.put("f" * 32, {"client_chat": 9, "client_id": 9, "client_name": "Other", "design": "x/secret.png",
                          "params": {}, "status": "auto_ok", "stage": "sent", "at": "2026-09-27 10:00"})
    b.handle(_text_msg("mera hisaab batao"))
    text = tg.texts(CLIENT)[-1]
    assert text.startswith("📋 Aapke order (1):") and "500 m — ✅ pakka" in text and "secret" not in text
    b.handle({"message_id": 9, "date": WHEN, "chat": {"id": CLIENT}, "text": "/orders", "from": {"id": CLIENT}})
    assert tg.texts(CLIENT)[-1] == text


def test_a_decision_ends_the_colour_trial_and_the_next_text_is_read_as_usual(tmp_path, monkeypatch):
    b, tg, job = _colour_job(tmp_path, monkeypatch)
    press(b, CLIENT, f"cw:{job}")
    b.handle(_text_msg("1 navy"))
    press(b, CLIENT, f"chg:{job}")                      # the client wants a change instead
    assert b.jobs.colours_for(CLIENT) is None
    b.handle(_text_msg("bas ek baat, logo bada karo"))  # not ink words: it goes to the team
    assert any("badlav maanga" in t for t in tg.texts(OPERATOR))


def test_a_trial_left_open_is_dropped_once_the_order_is_decided(tmp_path, monkeypatch):
    b, tg, job = _colour_job(tmp_path, monkeypatch)
    press(b, CLIENT, f"cw:{job}")
    b.jobs.get(job)["stage"] = "approved"               # decided elsewhere (the dashboard, an operator)
    b.handle(_text_msg("mere order"))
    assert tg.texts(CLIENT)[-1].startswith("📋 Aapke order")
    assert b.jobs.colours_for(CLIENT) is None


def test_only_the_newest_buttons_are_remembered(tmp_path):
    from app import bot_orders
    b, _ = bot(tmp_path, FakeEngine())
    tokens = [b.jobs.remember_colourway({"n": i}) for i in range(bot_orders.MAX_TOKENS + 3)]
    assert len(b.jobs.data["colourways"]) == bot_orders.MAX_TOKENS
    assert b.jobs.colourway(tokens[0]) is None and b.jobs.colourway(tokens[-1]) == {"n": bot_orders.MAX_TOKENS + 2}


# -- a late Approve: the job's files aged out of the 48 h cache (R-0005 #3) ----

class GoneEngine(FakeEngine):
    """The engine after the job's report and zip were deleted: 404 for them."""
    def __init__(self, gone=("package", "stage", "report"), **kw):
        super().__init__(**kw)
        self.gone = set()
        self._will_be_gone = set(gone)

    def expire(self):
        self.gone = set(self._will_be_gone)

    def fetch(self, path):
        if "package" in self.gone and path.endswith("/package"):
            raise EngineError("This job is no longer available. Run it again.", status=404)
        if "report" in self.gone and path.startswith("/api/auto/"):
            raise EngineError("This job is no longer available. Run it again.", status=404)
        return super().fetch(path)

    def stage(self, job_id, stage, by="", note=""):
        if "stage" in self.gone:
            raise EngineError("This job is no longer available. Run it again.", status=404)
        super().stage(job_id, stage, by, note)


def _sent_job(tmp_path, eng):
    b, tg = bot(tmp_path, eng)
    b.handle(design_msg("500 m"))
    job = eng.last["job_id"]
    assert b.jobs.get(job)["stage"] == "sent"
    return b, tg, job


def test_a_late_approve_of_an_expired_job_is_not_told_screens_are_being_made(tmp_path):
    from app.inbox_bot import EXPIRED
    eng = GoneEngine()
    b, tg, job = _sent_job(tmp_path, eng)
    eng.expire()
    press(b, CLIENT, f"ok:{job}")
    assert APPROVED not in tg.texts(CLIENT) and EXPIRED in tg.texts(CLIENT)
    assert b.jobs.get(job)["stage"] == "expired"                 # orders.json: not approved
    assert eng.stages == [(job, "sent")]                         # the job log was never told 'approved'
    assert not list((tmp_path / "inbox" / "approved").rglob("*.zip"))
    op = tg.texts(OPERATOR)
    assert len(op) == 1 and job[:8] in op[0] and "APPROVE NAHI" in op[0] and "rose.png" in op[0]
    assert not any(f[0] == "sendDocument" for f in tg.files)
    # the restarted bot reads it back the same way, and a second press changes nothing
    b2 = InboxBot(tg, b.settings, engine=eng)
    assert b2.jobs.get(job)["stage"] == "expired"
    press(b2, CLIENT, f"ok:{job}")
    assert APPROVED not in tg.texts(CLIENT) and len(tg.texts(OPERATOR)) == 1
    assert "purana ho gaya" in b2.my_orders(CLIENT)


def test_a_zip_without_its_report_is_not_approved_either(tmp_path):
    """The zip fetched but the approval cannot be written (report gone): no zip
    saved, nothing approved, the operator told."""
    from app.inbox_bot import EXPIRED
    eng = GoneEngine(gone=("stage",))
    b, tg, job = _sent_job(tmp_path, eng)
    eng.expire()
    press(b, CLIENT, f"ok:{job}")
    assert EXPIRED in tg.texts(CLIENT) and APPROVED not in tg.texts(CLIENT)
    assert b.jobs.get(job)["stage"] == "expired"
    assert not list((tmp_path / "inbox" / "approved").rglob("*.zip"))
    assert any("APPROVE NAHI" in t for t in tg.texts(OPERATOR))


def test_an_approve_while_loomlab_is_off_changes_nothing_and_can_be_pressed_again(tmp_path):
    from app.inbox_bot import APPROVE_RETRY

    class OffEngine(FakeEngine):
        off = False
        def fetch(self, path):
            if self.off and path.endswith("/package"):
                raise EngineError("not reachable", down=True)
            return super().fetch(path)

    eng = OffEngine()
    b, tg, job = _sent_job(tmp_path, eng)
    eng.off = True
    press(b, CLIENT, f"ok:{job}")
    assert APPROVED not in tg.texts(CLIENT) and tg.texts(CLIENT)[-1] == APPROVE_RETRY
    assert b.jobs.get(job)["stage"] == "sent" and eng.stages == [(job, "sent")]
    assert any(job[:8] in t and "'sent'" in t for t in tg.texts(OPERATOR))
    assert tg.buttons(CLIENT)[-2:] == [f"ok:{job}", f"chg:{job}"]   # a fresh Approve to press later
    eng.off = False
    press(b, CLIENT, f"ok:{job}")
    assert tg.texts(CLIENT)[-1] == APPROVED and b.jobs.get(job)["stage"] == "approved"
    assert eng.stages == [(job, "sent"), (job, "approved")]


def _age_cache(root, hours):
    import os, time
    then = time.time() - hours * 3600
    for p in root.iterdir():
        os.utime(p, (then, then))


def test_a_proof_sent_three_days_ago_survives_cleanup_and_its_approve_completes(tmp_path, monkeypatch):
    """Against the real engine: the 48 h cleanup keeps a job the client has not
    answered yet, so Approve on day 3 gets its zip, job log and library entry."""
    from app.core import joblog, library, store
    b, tg = _real_bot(tmp_path, monkeypatch)
    b.handle(design_msg("500 m"))
    job = next(iter(b.jobs.data["jobs"]))
    assert b.engine.get(f"/api/auto/{job}")["stage"] == "sent"
    _age_cache(store.ROOT, 72)
    store.cleanup_expired()
    assert store.auto_path(job, "json").exists() and store.auto_path(job, "zip").exists()
    press(b, CLIENT, f"ok:{job}")
    assert tg.texts(CLIENT)[-1] == APPROVED
    assert b.jobs.get(job)["stage"] == "approved"
    assert b.engine.get(f"/api/auto/{job}")["stage"] == "approved"
    assert [r["stage"] for r in joblog.read() if r.get("job_id") == job and r.get("event") == "stage"] == ["sent", "approved"]
    kept = library.get(job)
    assert kept.get("has_package") and kept.get("has_proof")
    assert len(list((tmp_path / "inbox" / "approved").rglob("*.zip"))) == 1


def test_a_job_really_gone_from_the_real_engine_is_marked_expired_not_approved(tmp_path, monkeypatch):
    from app.core import joblog, library, store
    from app.inbox_bot import EXPIRED
    b, tg = _real_bot(tmp_path, monkeypatch)
    b.handle(design_msg("500 m"))
    job = next(iter(b.jobs.data["jobs"]))
    store.auto_path(job, "json").unlink(); store.auto_path(job, "zip").unlink()   # aged out past every cap
    press(b, CLIENT, f"ok:{job}")
    assert tg.texts(CLIENT)[-1] == EXPIRED and APPROVED not in tg.texts(CLIENT)
    assert b.jobs.get(job)["stage"] == "expired"
    # M1: the job log says expired too (not 'sent' forever), and the client is not counted as waiting
    assert [r["stage"] for r in joblog.read() if r.get("job_id") == job and r.get("event") == "stage"] == ["sent", "expired"]
    ravi = next(c for c in b.engine.get("/api/clients?days=30")["clients"] if c["client"] == "Ravi")
    assert ravi["waiting"] == 0 and ravi["approved"] == 0
    assert b.engine.get("/api/stats?days=30")["stages"].get("expired") == 1
    with pytest.raises(FileNotFoundError):
        library.get(job)
    assert any("APPROVE NAHI" in t for t in tg.texts(OPERATOR))


# -- follow-up (R-0013): ask LoomLab before expiring or retrying ---------------

def test_an_approval_loomlab_wrote_but_answered_too_late_is_finished_not_retried(tmp_path):
    """H1 (FakeEngine): the stage POST ran but its answer timed out (no status).
    LoomLab's report says approved, so the bot finishes the approval."""
    class LateEngine(FakeEngine):
        recorded = False
        def stage(self, job_id, stage, by="", note=""):
            super().stage(job_id, stage, by, note)
            if stage == "approved":
                self.recorded = True
                raise EngineError("LoomLab engine took longer than 600 s")
        def fetch(self, path):
            if path.startswith("/api/auto/") and not path.endswith("/package"):
                return json.dumps(self.last | ({"stage": "approved"} if self.recorded else {"stage": "sent"})).encode()
            return super().fetch(path)

    from app.inbox_bot import APPROVE_RETRY
    eng = LateEngine()
    b, tg, job = _sent_job(tmp_path, eng)
    press(b, CLIENT, f"ok:{job}")
    assert tg.texts(CLIENT)[-1] == APPROVED and APPROVE_RETRY not in tg.texts(CLIENT)
    assert b.jobs.get(job)["stage"] == "approved"
    assert len(list((tmp_path / "inbox" / "approved").rglob("*.zip"))) == 1
    assert ("sendDocument", OPERATOR) in [(m, c) for m, c, _, _ in tg.files]


def _late_local(tmp_path, monkeypatch):
    """The real engine, whose answer to an approval is lost after it wrote it (H1 probe)."""
    b, tg = _real_bot(tmp_path, monkeypatch)
    real_stage = b.engine.stage
    def stage(job_id, stage, by="", note=""):
        answer = real_stage(job_id, stage, by, note)
        if stage == "approved":
            raise EngineError("LoomLab engine took longer than 600 s")
        return answer
    b.engine.stage = stage
    return b, tg


def test_h1_probe_a_late_answer_then_the_48h_cleanup_never_ends_in_expired(tmp_path, monkeypatch):
    """Chunnu's H1 probe on the real engine: the approval is written, the answer is
    lost. The bot finishes it at once, so the files leaving the cache later changes
    nothing: orders.json, job log and library all say approved."""
    from app.core import joblog, library, store
    from app.inbox_bot import EXPIRED
    b, tg = _late_local(tmp_path, monkeypatch)
    b.handle(design_msg("500 m"))
    job = next(iter(b.jobs.data["jobs"]))
    press(b, CLIENT, f"ok:{job}")
    assert tg.texts(CLIENT)[-1] == APPROVED and b.jobs.get(job)["stage"] == "approved"
    _age_cache(store.ROOT, 72)
    store.cleanup_expired()                                  # approved: no longer protected, files go
    assert not store.auto_path(job, "json").exists()
    press(b, CLIENT, f"ok:{job}")                            # a second press: already decided
    assert EXPIRED not in tg.texts(CLIENT) and b.jobs.get(job)["stage"] == "approved"
    assert [r["stage"] for r in joblog.read() if r.get("job_id") == job and r.get("event") == "stage"] == ["sent", "approved"]
    assert library.get(job).get("has_package")


def test_an_approval_already_in_the_library_is_finished_from_the_library_zip(tmp_path, monkeypatch):
    """H1, the other half: orders.json still 'sent' (an older bot, a lost answer) but
    LoomLab approved the job and its cache files are gone: the library has it."""
    from app.core import store
    b, tg = _real_bot(tmp_path, monkeypatch)
    b.handle(design_msg("500 m"))
    job = next(iter(b.jobs.data["jobs"]))
    b.engine.post(f"/api/jobs/{job}/stage", {"stage": "approved", "by": "dashboard"})
    kept = b.engine.fetch(f"/api/library/{job}/package")
    store.auto_path(job, "json").unlink(); store.auto_path(job, "zip").unlink()
    assert b.jobs.get(job)["stage"] == "sent"
    press(b, CLIENT, f"ok:{job}")
    assert tg.texts(CLIENT)[-1] == APPROVED and b.jobs.get(job)["stage"] == "approved"
    saved = list((tmp_path / "inbox" / "approved").rglob("*.zip"))
    assert len(saved) == 1 and saved[0].read_bytes() == kept


def test_a_404_that_is_not_loomlab_saying_gone_is_not_expired(tmp_path):
    """M2: a wrong ENGINE= path (or a proxy) answers 404 'Not Found' for everything:
    the order stays 'sent', the client may press again, the operator is told to check ENGINE=."""
    from app.inbox_bot import APPROVE_RETRY, EXPIRED
    class WrongPath(FakeEngine):
        wrong = False
        def fetch(self, path):
            if self.wrong:
                raise EngineError("Not Found", status=404)
            return super().fetch(path)
    eng = WrongPath()
    b, tg, job = _sent_job(tmp_path, eng)
    eng.wrong = True
    press(b, CLIENT, f"ok:{job}")
    assert EXPIRED not in tg.texts(CLIENT) and tg.texts(CLIENT)[-1] == APPROVE_RETRY
    assert b.jobs.get(job)["stage"] == "sent" and eng.stages == [(job, "sent")]
    assert any("ENGINE=" in t for t in tg.texts(OPERATOR))


def test_a_wrong_engine_path_on_the_real_engine_is_not_expired(tmp_path, monkeypatch):
    """M2 on the real API: a base URL with a wrong path gets FastAPI's own 404."""
    from app.inbox_bot import APPROVE_RETRY
    b, tg = _real_bot(tmp_path, monkeypatch)
    b.handle(design_msg("500 m"))
    job = next(iter(b.jobs.data["jobs"]))
    real_open = b.engine._open
    b.engine._open = lambda req: real_open(type(req)(req.full_url.replace("/api/", "/wrong/api/"), data=req.data,
                                                     headers=dict(req.header_items()), method=req.get_method()))
    press(b, CLIENT, f"ok:{job}")
    assert tg.texts(CLIENT)[-1] == APPROVE_RETRY and b.jobs.get(job)["stage"] == "sent"
    b.engine._open = real_open
    assert b.engine.get(f"/api/auto/{job}")["stage"] == "sent"


def test_with_no_operator_an_expiry_is_written_to_the_bot_window(tmp_path, capsys):
    """M1: OPERATOR= empty: tell_operators reaches nobody on Telegram, so the window says it."""
    eng = GoneEngine()
    b, tg, job = _sent_job(tmp_path, eng)
    b.settings.operators = set()
    eng.expire()
    press(b, CLIENT, f"ok:{job}")
    out = capsys.readouterr().out
    assert "OPERATOR= khaali" in out and job[:8] in out and "APPROVE NAHI" in out
    assert b.jobs.get(job)["stage"] == "expired"


def test_the_expired_row_reaches_the_job_log_even_without_the_report(tmp_path, monkeypatch):
    """M1, the engine side: 'expired' for a job whose report is gone goes straight to
    the job log, named as before, once; any other stage for it is still a 404."""
    from app.core import joblog, store
    b, tg = _real_bot(tmp_path, monkeypatch)
    b.handle(design_msg("500 m"))
    job = next(iter(b.jobs.data["jobs"]))
    store.auto_path(job, "json").unlink()
    for _ in range(2):
        b.engine.post(f"/api/jobs/{job}/stage", {"stage": "expired", "by": "bot"})
    rows = [r for r in joblog.read() if r.get("job_id") == job and r.get("event") == "stage"]
    assert [r["stage"] for r in rows] == ["sent", "expired"] and rows[-1]["client"] == "Ravi"
    with pytest.raises(EngineError) as e:
        b.engine.post(f"/api/jobs/{job}/stage", {"stage": "approved"})
    assert e.value.status == 404
    with pytest.raises(EngineError) as e:
        b.engine.post(f"/api/jobs/{'f' * 32}/stage", {"stage": "expired"})   # never made: gone
    assert e.value.status == 404


def test_a_held_job_is_marked_in_loomlab_so_cleanup_keeps_it(tmp_path):
    """H2 (bot side): holding a job tells LoomLab, whichever hold it is."""
    class Recording(FakeEngine):
        posts = []
        def post(self, path, body):
            self.posts.append((path, body))
            return {}
    eng = Recording(status="needs_review")
    b, tg = bot(tmp_path, eng)
    b.handle(design_msg())
    job = eng.last["job_id"]
    assert b.jobs.get(job)["stage"] == "review"
    assert eng.posts == [(f"/api/jobs/{job}/hold", {"why": "needs_review", "by": "bot"})]


def test_a_held_job_survives_the_48h_cleanup_on_the_real_engine(tmp_path, monkeypatch):
    """H2 (engine side): a job still 'new' (OPERATOR= empty holds auto_ok jobs too)
    and marked held keeps its files; the same job unmarked goes at 48 h."""
    from app.core import store
    b, tg = _real_bot(tmp_path, monkeypatch)
    b.handle(design_msg("500 m"))
    b.handle(design_msg("400 m", mid=2))
    held, unheld = list(b.jobs.data["jobs"])
    for job in (held, unheld):     # back to 'new', as a job the bot never sent
        r = json.loads(store.auto_path(job, "json").read_text()); r["stage"], r["history"] = "new", []
        store.auto_path(job, "json").write_text(json.dumps(r))
    b._mark_held(held, "no_operator")
    assert b.engine.get(f"/api/auto/{held}")["held"]["why"] == "no_operator"
    assert b.engine.get(f"/api/auto/{held}")["stage"] == "new"     # no stage change, no job-log row
    _age_cache(store.ROOT, 72)
    store.cleanup_expired()
    assert store.auto_path(held, "json").exists() and store.auto_path(held, "zip").exists()
    assert not store.auto_path(unheld, "json").exists()
    with pytest.raises(EngineError):
        b.engine.post(f"/api/jobs/{'f' * 32}/hold", {"why": "x"})


def test_a_full_disk_after_loomlab_approved_still_tells_the_client_once(tmp_path):
    """L1: the zip cannot be saved on the PC; LoomLab's library has it. No exception
    (so the update is not run again), APPROVED once, the operator told."""
    eng = FakeEngine()
    b, tg, job = _sent_job(tmp_path, eng)
    (tmp_path / "inbox" / "approved").write_text("a file where the folder should be")
    press(b, CLIENT, f"ok:{job}")
    assert tg.texts(CLIENT).count(APPROVED) == 1 and b.jobs.get(job)["stage"] == "approved"
    assert any("save NAHI" in f[2] for f in tg.files if f[1] == OPERATOR)


def test_a_lost_retry_button_is_not_reported_as_a_failed_save(tmp_path):
    """L2: the retry message itself fails on Telegram: caught, the order stays 'sent'."""
    from app.inbox_bot import FAILED
    class OffEngine(FakeEngine):
        def fetch(self, path):
            if path.endswith("/package"):
                raise EngineError("not reachable", down=True)
            return super().fetch(path)
    eng = OffEngine()
    b, tg, job = _sent_job(tmp_path, eng)
    tg.fail = ("sendMessage", CLIENT, TelegramError(403, "blocked"))
    press(b, CLIENT, f"ok:{job}")
    assert b.jobs.get(job)["stage"] == "sent" and FAILED not in tg.texts(CLIENT)
    assert any("'sent'" in t for t in tg.texts(OPERATOR))


def test_an_approval_that_missed_the_library_is_told_to_the_operator(tmp_path):
    """L3: LoomLab approved but could not keep it in the library (a film open on Windows)."""
    class NoLibrary(FakeEngine):
        def stage(self, job_id, stage, by="", note=""):
            super().stage(job_id, stage, by, note)
            return {"library": False, "library_error": "Approved, but not added to the library (file in use)."}
    eng = NoLibrary()
    b, tg, job = _sent_job(tmp_path, eng)
    press(b, CLIENT, f"ok:{job}")
    assert tg.texts(CLIENT)[-1] == APPROVED
    assert any("Library me nahi gaya" in t and "file in use" in t for t in tg.texts(OPERATOR))


# -- R-0017: N1 (library entry without its zip), N2 (holds from before the upgrade) --

def test_an_approval_kept_in_the_library_without_its_zip_is_not_expired(tmp_path, monkeypatch):
    """N1: the report is gone and the library entry has no package.zip, but the entry
    is there, so LoomLab did approve it: finished as approved (operator told to look
    in the Library), never 'expired' next to a library entry."""
    from app.core import joblog, library, store
    from app.inbox_bot import EXPIRED
    b, tg = _real_bot(tmp_path, monkeypatch)
    b.handle(design_msg("500 m"))
    job = next(iter(b.jobs.data["jobs"]))
    b.engine.post(f"/api/jobs/{job}/stage", {"stage": "approved", "by": "dashboard"})
    (library.folder(job) / "package.zip").unlink()
    store.auto_path(job, "json").unlink(); store.auto_path(job, "zip").unlink()
    press(b, CLIENT, f"ok:{job}")
    assert tg.texts(CLIENT)[-1] == APPROVED and EXPIRED not in tg.texts(CLIENT)
    assert b.jobs.get(job)["stage"] == "approved"
    assert "expired" not in [r["stage"] for r in joblog.read() if r.get("job_id") == job]
    assert any("Library page" in t for t in tg.texts(OPERATOR))
    assert library.get(job)                                  # still offered for repeats, rightly


def test_the_library_says_a_missing_entry_apart_from_an_entry_without_films(tmp_path, monkeypatch):
    """N1, the engine side: the two 404s the bot tells apart."""
    from app.core import library
    b, tg = _real_bot(tmp_path, monkeypatch)
    b.handle(design_msg("500 m"))
    job = next(iter(b.jobs.data["jobs"]))
    with pytest.raises(EngineError) as e:
        b.engine.fetch(f"/api/library/{job}/package")          # never approved: no entry
    assert e.value.status == 404 and "No such design" in str(e.value)
    b.engine.post(f"/api/jobs/{job}/stage", {"stage": "approved"})
    assert b.engine.fetch(f"/api/library/{job}/package")[:2] == b"PK"
    (library.folder(job) / "package.zip").unlink()
    with pytest.raises(EngineError) as e:
        b.engine.fetch(f"/api/library/{job}/package")
    assert e.value.status == 404 and "no production package" in str(e.value)


def test_n1_probe_late_answer_unreachable_check_then_cleanup_ends_approved(tmp_path, monkeypatch):
    """Chunnu's N1 probe: approval written, answer lost, the check finds LoomLab
    unreachable (retry), the library entry has no zip, the cache ages out; the
    next press finds the entry and finishes as approved."""
    from app.core import joblog, library, store
    from app.inbox_bot import APPROVE_RETRY, EXPIRED
    b, tg = _late_local(tmp_path, monkeypatch)
    b.handle(design_msg("500 m"))
    job = next(iter(b.jobs.data["jobs"]))
    real_has = b._engine_has
    b._engine_has = lambda job_id: ("unknown", None)          # the check cannot reach LoomLab
    press(b, CLIENT, f"ok:{job}")
    assert tg.texts(CLIENT)[-1] == APPROVE_RETRY and b.jobs.get(job)["stage"] == "sent"
    b._engine_has = real_has
    (library.folder(job) / "package.zip").unlink()
    _age_cache(store.ROOT, 72)
    store.cleanup_expired()                                    # approved in LoomLab: files go
    assert not store.auto_path(job, "json").exists()
    press(b, CLIENT, f"ok:{job}")
    assert tg.texts(CLIENT)[-1] == APPROVED and EXPIRED not in tg.texts(CLIENT)
    assert b.jobs.get(job)["stage"] == "approved"
    assert [r["stage"] for r in joblog.read() if r.get("job_id") == job and r.get("event") == "stage"] == ["sent", "approved"]


def test_orders_held_before_the_upgrade_are_marked_at_start_up(tmp_path):
    """N2: 'review' orders in orders.json (held by an older bot, never marked in
    LoomLab) are marked; sent / approved ones are not; a failure is counted."""
    class Recording(FakeEngine):
        def __init__(self):
            super().__init__()
            self.posts = []
        def post(self, path, body):
            if "dead" in path:
                raise EngineError("This job is no longer available. Run it again.", status=404)
            self.posts.append((path, body))
            return {}
    eng = Recording()
    b, tg = bot(tmp_path, eng)
    base = {"client_chat": CLIENT, "client_id": CLIENT, "client_name": "Ravi", "design": "x.png", "params": {},
            "status": "needs_review", "at": "2026-10-14 10:00"}
    held, other, sent = "a" * 32, "b" * 32, "c" * 32
    b.jobs.put(held, base | {"stage": "review"})
    b.jobs.put(other, base | {"stage": "review", "held": "no_operator"})
    b.jobs.put(sent, base | {"stage": "sent"})
    b.jobs.put("dead" + "0" * 28, base | {"stage": "review"})
    assert b.mark_held_reviews() == (2, 1)
    assert sorted(eng.posts) == [(f"/api/jobs/{held}/hold", {"why": "review", "by": "bot"}),
                                 (f"/api/jobs/{other}/hold", {"why": "no_operator", "by": "bot"})]


def test_marking_at_every_start_up_keeps_the_first_mark_and_its_clock(tmp_path, monkeypatch):
    """N2 idempotent, on the real engine: a pre-upgrade hold is marked at the first
    start, kept by cleanup, and a second start does not restart its 14-day clock."""
    from app.core import store
    b, tg = _real_bot(tmp_path, monkeypatch)
    b.handle(design_msg("500 m"))
    job = next(iter(b.jobs.data["jobs"]))
    r = json.loads(store.auto_path(job, "json").read_text()); r["stage"], r["history"] = "new", []
    store.auto_path(job, "json").write_text(json.dumps(r))     # as an older bot left a held job
    b.jobs.get(job)["stage"] = "review"; b.jobs.save()
    assert b.mark_held_reviews() == (1, 0)
    first = b.engine.get(f"/api/auto/{job}")["held"]
    r = json.loads(store.auto_path(job, "json").read_text())
    r["held"]["at"] = "2026-10-10T09:00:00"                     # marked days ago
    store.auto_path(job, "json").write_text(json.dumps(r))
    assert b.mark_held_reviews() == (1, 0)
    assert b.engine.get(f"/api/auto/{job}")["held"] == first | {"at": "2026-10-10T09:00:00"}
    _age_cache(store.ROOT, 72)
    store.cleanup_expired()
    assert store.auto_path(job, "json").exists()               # 6 days into 14: kept


def test_the_bot_marks_held_orders_when_it_starts(tmp_path, monkeypatch):
    """N2: run() does it once at start-up, when the engine is on."""
    from app import inbox_bot
    calls = []
    class Api:
        def __init__(self, token): pass
        def call(self, method, **kw): return {"username": "loomlab_test_bot"}
    monkeypatch.setattr(inbox_bot, "TelegramApi", Api)
    monkeypatch.setattr(inbox_bot.InboxBot, "mark_held_reviews", lambda self: calls.append(1) or (0, 0))
    def stop(self, *a, **k): raise KeyboardInterrupt
    monkeypatch.setattr(inbox_bot.InboxBot, "poll_once", stop)
    cfg = tmp_path / "telegram-bot.txt"
    cfg.write_text(f"TOKEN={TOKEN}\nFOLDER={tmp_path / 'inbox'}\nENGINE=http://localhost:8003\n", encoding="utf-8")
    assert inbox_bot.run(cfg) == 0 and calls == [1]
    cfg.write_text(f"TOKEN={TOKEN}\nFOLDER={tmp_path / 'inbox'}\nENGINE=off\n", encoding="utf-8")
    assert inbox_bot.run(cfg) == 0 and calls == [1]            # engine off: nothing to mark
