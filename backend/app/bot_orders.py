"""The Telegram bot's order desk: a saved design goes to LoomLab's auto mode,
and the proof and quote come back to the client with Approve / Change.

    design in -> auto mode -> auto_ok      -> client: proof + quote + buttons
                           -> needs_review -> operator first (send / reject)
    Approve -> the production zip is saved and goes to the operator
    Change  -> "6 inks, 30 inch, 800 m" -> a new proof; anything else -> operator

Standard library only, like the inbox. Talks to the LoomLab engine over
HTTP (the same engine the app uses, normally on this PC).
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path


class EngineError(Exception):
    """LoomLab could not do the job. `down` = it is not running at all."""

    def __init__(self, message: str, down: bool = False):
        super().__init__(message)
        self.down = down


def multipart(fields: dict, files: list) -> tuple[bytes, str]:
    """(body, content type) for a multipart/form-data POST.
    fields: {name: value}; files: [(field, filename, bytes, content type)]."""
    boundary = uuid.uuid4().hex
    out = bytearray()
    for name, value in fields.items():
        if value is None:
            continue
        out += (f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
                f'{value}\r\n').encode()
    for name, filename, data, ctype in files:
        safe = filename.replace('"', "'").replace("\r", " ").replace("\n", " ")
        out += (f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; '
                f'filename="{safe}"\r\nContent-Type: {ctype}\r\n\r\n').encode()
        out += data + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return bytes(out), f"multipart/form-data; boundary={boundary}"


_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
          ".tif": "image/tiff", ".tiff": "image/tiff", ".psd": "image/vnd.adobe.photoshop",
          ".bmp": "image/bmp"}


class Engine:
    """The LoomLab engine's auto mode, over HTTP."""

    def __init__(self, base: str, timeout: float = 600):
        self.base = base.rstrip("/")
        self.timeout = timeout

    def _open(self, req):
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as err:
            try:
                detail = json.load(err).get("detail")
            except ValueError:
                detail = err.reason
            if isinstance(detail, list):   # a validation error: its messages
                detail = "; ".join(str(d.get("msg", d)) for d in detail)
            raise EngineError(str(detail)) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as err:
            raise EngineError(f"LoomLab engine not reachable at {self.base} ({err})", down=True) from None

    def auto(self, data: bytes, filename: str, params: dict) -> dict:
        ctype = _TYPES.get(Path(filename).suffix.lower(), "image/png")
        body, content_type = multipart({k: v for k, v in params.items() if v is not None},
                                       [("file", filename, data, ctype)])
        req = urllib.request.Request(f"{self.base}/api/auto/upload", data=body,
                                     headers={"Content-Type": content_type})
        return json.loads(self._open(req))

    def fetch(self, path: str) -> bytes:
        return self._open(urllib.request.Request(self.base + path))

    def stage(self, job_id: str, stage: str, by: str = "") -> None:
        """Tell the job dashboard where an order stands."""
        body = json.dumps({"stage": stage, "by": by[:60]}).encode()
        self._open(urllib.request.Request(f"{self.base}/api/jobs/{job_id}/stage", data=body,
                                          headers={"Content-Type": "application/json"}))


# "6 inks", "6 colours", "6 rang" / "30 inch", '30"', "30 in" / "500 m", "1,500 meter",
# "1,50,000 mtr". A number is read whole: never the tail of a longer one ("120
# colours" is not 20) and with its thousands commas ("1,500 m" is not 500).
_NUM = r"(?<![\d,.])(\d{1,3}(?:,\d{2,3})+|\d+)(?:\.(\d+))?"
_COLORS = re.compile(_NUM + r"\s*(?:inks?|colou?rs?|rang|screens?)\b", re.I)
_WIDTH = re.compile(_NUM + r"\s*(?:inch(?:es)?|in\b|\")", re.I)
_METERS = re.compile(_NUM + r"\s*(?:m\b|mtrs?\b|meters?\b|metres?\b|mt\b)", re.I)


def _number(m) -> float:
    whole = m.group(1).replace(",", "")
    return float(whole + ("." + m.group(2) if m.group(2) else ""))


def parse_request(text: str) -> dict:
    """The job settings a client wrote in plain words, e.g. '500 m, 30 inch,
    6 inks'. Only what was written; everything else is left to defaults."""
    out = {}
    if (m := _COLORS.search(text or "")) and not m.group(2):
        n = int(_number(m))
        if 1 <= n <= 20:
            out["colors"] = n
    if m := _WIDTH.search(text or ""):
        w = _number(m)
        if 0 < w <= 200:
            out["width_in"] = w
    if m := _METERS.search(text or ""):
        mt = _number(m)
        if 0 < mt <= 1_000_000:
            out["meters"] = mt
    return out


class Jobs:
    """Every order the bot handles, kept in a JSON file so a restart forgets
    nothing: which client, which design, its settings and where it stands
    (review -> sent -> approved | rejected)."""

    def __init__(self, path: Path):
        self.path = path
        try:
            self.data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.data = {}
        self.data.setdefault("jobs", {})
        self.data.setdefault("awaiting_change", {})

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".part")
        tmp.write_text(json.dumps(self.data, indent=1, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def get(self, job_id: str) -> dict | None:
        return self.data["jobs"].get(job_id)

    def put(self, job_id: str, job: dict) -> None:
        self.data["jobs"][job_id] = job
        self.save()

    def await_change(self, chat_id: int, job_id: str | None) -> None:
        if job_id:
            self.data["awaiting_change"][str(chat_id)] = job_id
        else:
            self.data["awaiting_change"].pop(str(chat_id), None)
        self.save()

    def awaiting(self, chat_id: int) -> str | None:
        return self.data["awaiting_change"].get(str(chat_id))


WARN_WORDS = {
    "photographic": "photo jaisi shading hai, flat inks se bands dikhenge",
    "low_match": "original se match kam hai",
    "soft_edges": "kinare dhundhle (feathered) hain",
    "tiny_dots": "bahut chhoti bindiyan hain jo screen par nahi tikengi",
    "similar_inks": "do inks lagbhag ek jaise hain",
    "many_inks": "screens bahut zyada hain",
    "low_resolution": "file itni badi print ke liye chhoti hai, patli lines mote dikhenge",
}


def summary(report: dict, for_operator: bool = False) -> str:
    """The proof's caption: what will print, and (for the operator) why a
    job was held."""
    p = report["print"]
    lines = [f"🎨 {len(report['inks'])} screens · match {report['accuracy']}%",
             f"📐 {p['width_in']:g} × {p['height_in']:g} inch · {p['dpi']} DPI"]
    q = report.get("quote")
    if q:
        lines.append(f"💰 {q['meters']:g} m: {_money(q['total'], q['currency'])} "
                     f"({_money(q['per_meter'], q['currency'])}/m)")
    held = [w for w in report["warnings"] if w["blocking"]]
    if for_operator and held:
        lines.append("\n⚠️ Rukne ki wajah:")
        lines += [f"• {WARN_WORDS.get(w['code'], w['code'])}: {w['message']}" for w in held]
    return "\n".join(lines)


def _money(value, currency="₹"):
    n = int(round(value))
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:]); head = head[:-2]
        s = ",".join(([head] if head else []) + groups) + "," + tail
    return f"{'-' if n < 0 else ''}{currency}{s}"
