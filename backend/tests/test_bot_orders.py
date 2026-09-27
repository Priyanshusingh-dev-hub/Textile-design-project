"""The bot's order desk: proof and quote back to the client, Approve / Change,
operator review — driven through a fake Telegram and a fake engine."""
import io
import json
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.bot_orders import EngineError, multipart, parse_request, summary
from app.inbox_bot import APPROVED, ASK_CHANGE, CHANGE_TO_TEAM, ENGINE_DOWN, HELD, REJECTED, InboxBot, Settings

TOKEN = "123456789:AAH" + "x" * 32
WHEN = int(datetime(2026, 9, 27, 11, 0, 0).timestamp())
CLIENT, OPERATOR = 42, 7


class FakeTelegram:
    def __init__(self):
        self.calls = []      # (method, params)
        self.files = []      # (method, chat_id, caption)

    def call(self, method, wait=30, **params):
        self.calls.append((method, params))
        if method == "getFile":
            return {"file_path": "documents/design.png"}
        return {}

    def download(self, file_path):
        return b"PNG-DESIGN"

    def send_file(self, method, field, filename, data, ctype, **params):
        self.files.append((method, params["chat_id"], params.get("caption", ""), filename))
        return {}

    def texts(self, chat):
        return [p["text"] for m, p in self.calls if m == "sendMessage" and p["chat_id"] == chat]

    def buttons(self, chat):
        return [b["callback_data"] for m, p in self.calls if m == "sendMessage" and p["chat_id"] == chat
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

    def stage(self, job_id, stage, by=""):
        self.stages.append((job_id, stage))

    def fetch(self, path):
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
    assert tg.buttons(CLIENT) == [f"ok:{job}", f"chg:{job}"]
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
    assert tg.buttons(CLIENT) == [f"ok:{job}", f"chg:{job}"]


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
    assert tg.buttons(CLIENT) == [f"ok:{eng.last['job_id']}", f"chg:{eng.last['job_id']}"]
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
    assert any("auto mode me nahi" in t for t in tg.texts(OPERATOR))


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
