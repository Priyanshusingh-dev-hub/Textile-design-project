"""LoomLab as tools for an AI operator (Model Context Protocol, over stdio).

Claude Desktop, Claude Code or any MCP client starts this and can then run the
mill's desk: take a design from the inbox, run it through auto mode, LOOK at
the proof (it comes back as an image), re-run it with another ink count or
size, price it, mark the job on the dashboard and save the production zip.
The AI decides; the engine does every pixel, on this PC, exactly as the app
does (it calls the same running engine as the app and the Telegram bot, so
the job dashboard shows everything it does).

    python -m app.mcp_server            the server (an MCP client starts it)
    python -m app.mcp_server --setup    what to paste into Claude Desktop /
                                        Claude Code on this PC
    python -m app.mcp_server --install-desktop   add it to Claude Desktop's
                                        settings (setup-claude-windows.bat)

Settings (environment): LOOMLAB_ENGINE (default http://localhost:8003),
LOOMLAB_INBOX (default: the Designs-Inbox folder the Telegram bot fills).

Standard library only, like the bot: JSON-RPC 2.0, one message per line on
stdin/stdout. Nothing but protocol messages may go to stdout; notes go to stderr.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

if __package__ in (None, ''):          # run as a file path (some MCP clients do)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = 'app'

from .bot_orders import Engine, EngineError, recoloured  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PROTOCOLS = ('2025-06-18', '2025-03-26', '2024-11-05')
DESIGN_TYPES = {'.png', '.jpg', '.jpeg', '.webp', '.tif', '.tiff', '.psd', '.bmp'}
STAGES = ('new', 'reviewed', 'sent', 'approved', 'rejected', 'changed')
PROOF_SIDE = 1200          # enough to judge a proof; small enough for a model's context

INSTRUCTIONS = """LoomLab is a screen-printing mill's colour-separation engine on this PC.
A design goes in; screens (one film per ink), a colour proof, a job sheet and a
price come out. You are the operator: decide, check, and hand exceptions to a person.

Typical round:
1. list_inbox (or a file path you were given) -> separate_design on the file.
2. Look at the proof image against the original (get_job with_original=true).
   Status auto_ok: the engine found nothing to worry about. needs_review: read
   each warning; a re-run often fixes it (another ink count, a print width the
   file has resolution for). Photo-like shading cannot be printed with flat
   inks: say so, do not force it.
3. mark_job: 'reviewed' when you checked it, 'rejected' with a note when it
   should not be printed, and leave anything you are unsure about as 'new' so
   a person sees it on the dashboard.
4. quote_job for a price, save_package for the production zip.
Never claim a job is fine without looking at its proof. A wrong screen wastes
screen, ink and cloth."""


def _schema(props: dict, required=()) -> dict:
    return {'type': 'object', 'properties': props, 'required': list(required), 'additionalProperties': False}


_JOB = {'type': 'string', 'description': 'Job id (from separate_design or list_jobs).'}
_SETTINGS = {
    'colors': {'type': 'integer', 'minimum': 1, 'maximum': 20,
               'description': 'Number of inks (screens). Leave out to use the count the engine suggests.'},
    'width_in': {'type': 'number', 'exclusiveMinimum': 0, 'maximum': 200,
                 'description': 'Print width in inches. Leave out to print at the file\'s own size.'},
    'fabric': {'type': 'string', 'pattern': '^#[0-9A-Fa-f]{6}$', 'description': 'Cloth colour, e.g. #FFFFFF.'},
    'underbase': {'type': 'boolean', 'description': 'Add a white under-base screen (for dark cloth).'},
    'trap_px': {'type': 'integer', 'minimum': 0, 'maximum': 3,
                'description': 'Trap: lighter inks spread under darker ones on the films, 0-3 px. Usually 0.'},
    'meters': {'type': 'number', 'exclusiveMinimum': 0, 'description': 'Meters to print: also prices the run.'},
    'client': {'type': 'string', 'maxLength': 60, 'description': 'Client name, for the job list and quote.'},
}

_INKS = {'type': 'array', 'items': {'type': 'string', 'pattern': '^#[0-9A-Fa-f]{6}$'},
         'description': 'One #RRGGBB colour per ink, in the order get_job lists the inks.'}

TOOLS = [
    {'name': 'separate_design',
     'description': 'Run a design file through LoomLab auto mode: choose inks, reduce, separate into one '
                    'screen per ink and build the production package. Returns the status (auto_ok or '
                    'needs_review), every warning, the inks, the match with the original and the proof image.',
     'inputSchema': _schema({'file': {'type': 'string', 'description': 'Full path of the design file on this PC.'},
                             **_SETTINGS}, ['file'])},
    {'name': 'rerun_job',
     'description': 'Run a job\'s design again with other settings (ink count, print width, cloth...). '
                    'Makes a new job; the old one stays on the dashboard.',
     'inputSchema': _schema({'job_id': _JOB, **_SETTINGS}, ['job_id'])},
    {'name': 'get_job',
     'description': 'One job: status, warnings, inks, print size, quote, where it stands, and its proof image '
                    '(optionally the original design next to it, to compare).',
     'inputSchema': _schema({'job_id': _JOB,
                             'with_proof': {'type': 'boolean', 'description': 'Include the proof image (default true).'},
                             'with_original': {'type': 'boolean', 'description': 'Also include the original design.'}},
                            ['job_id'])},
    {'name': 'list_jobs',
     'description': 'Jobs on the dashboard, newest first. waiting = held by auto mode and not dealt with yet.',
     'inputSchema': _schema({'show': {'type': 'string', 'enum': ['waiting', 'open', 'all'],
                                      'description': 'Which jobs (default waiting).'},
                             'limit': {'type': 'integer', 'minimum': 1, 'maximum': 200}})},
    {'name': 'mark_job',
     'description': 'Record where a job stands on the dashboard: reviewed (checked), sent, approved, '
                    'rejected or changed, with a short note saying why.',
     'inputSchema': _schema({'job_id': _JOB, 'stage': {'type': 'string', 'enum': list(STAGES)},
                             'note': {'type': 'string', 'maxLength': 300}}, ['job_id', 'stage'])},
    {'name': 'quote_job',
     'description': 'Price a print run of a job from the mill\'s rate card: ink by weight from each screen\'s '
                    'coverage, screens, printing, cloth, margin and GST. Returns the figures and the quote image.',
     'inputSchema': _schema({'job_id': _JOB, 'meters': _SETTINGS['meters'], 'client': _SETTINGS['client']},
                            ['job_id', 'meters'])},
    {'name': 'preview_colourway',
     'description': 'Show a job\'s design printed with other inks on the SAME screens (a colourway): give one '
                    'colour per ink, in the order get_job lists the inks. Returns the proof image. Nothing is saved.',
     'inputSchema': _schema({'job_id': _JOB, 'inks': _INKS, 'fabric': _SETTINGS['fabric']}, ['job_id', 'inks'])},
    {'name': 'make_colourway_job',
     'description': 'Make a colourway a job of its own: the SAME screens printed in other inks (one per ink, in the '
                    'order get_job lists them), with its own package, proof and quote, ready to mark like any job. '
                    'A colour close to one of the mill\'s shelf inks becomes that ink. On dark cloth a white '
                    'under-base is added. Preview it first with preview_colourway.',
     'inputSchema': _schema({'job_id': _JOB, 'inks': _INKS, 'fabric': _SETTINGS['fabric'],
                             'meters': _SETTINGS['meters']}, ['job_id', 'inks'])},
    {'name': 'save_package',
     'description': 'Save a job\'s production package (films, plates, proof, job sheet) as a zip into a folder. '
                    'With colourways, the zip also gets a proof and a job sheet for each (same screens, other inks).',
     'inputSchema': _schema({'job_id': _JOB, 'folder': {'type': 'string', 'description': 'Folder on this PC.'},
                             'colourways': {'type': 'array', 'maxItems': 8, 'items': _schema(
                                 {'name': {'type': 'string', 'minLength': 1, 'maxLength': 40},
                                  'inks': _INKS, 'fabric': _SETTINGS['fabric']}, ['name', 'inks'])}},
                            ['job_id', 'folder'])},
    {'name': 'find_design',
     'description': 'Search the design library: every approved job, kept for good (the job list forgets after '
                    '48 h). Use it for a repeat order ("the same design, 500 m more"): it gives the library id.',
     'inputSchema': _schema({'query': {'type': 'string', 'description': 'Part of the design or client name.'},
                             'with_proofs': {'type': 'boolean', 'description': 'Include each match\'s proof (max 4).'}})},
    {'name': 'repeat_quote',
     'description': 'Price a repeat order of a library design: the screens already exist, so none are charged. '
                    'Returns the figures and the quote image.',
     'inputSchema': _schema({'library_id': {'type': 'string', 'pattern': '^[0-9a-f]{32}$'},
                             'meters': _SETTINGS['meters'], 'client': _SETTINGS['client']}, ['library_id', 'meters'])},
    {'name': 'job_stats',
     'description': 'The mill\'s numbers from the job log (kept for good): designs in the last N days, how many '
                    'needed nobody, approved/stopped, quoted value, and the time saved at the mill\'s own estimates.',
     'inputSchema': _schema({'days': {'type': 'integer', 'minimum': 1, 'maximum': 366,
                                      'description': 'How many days back (default 30).'}})},
    {'name': 'client_summary',
     'description': 'Each client\'s business from the job log: designs sent, approved, stopped and waiting, '
                    'approved meters, repeat orders and the money they brought in (approved + repeats, as quoted); '
                    'the biggest first. Give part of a name for one client.',
     'inputSchema': _schema({'client': {'type': 'string', 'maxLength': 60, 'description': 'Part of the client name.'},
                             'days': {'type': 'integer', 'minimum': 1, 'maximum': 3660,
                                      'description': 'How many days back (default 90).'}})},
    {'name': 'list_inbox',
     'description': 'Design files that arrived in the inbox folder (the Telegram bot saves there), newest '
                    'first, with the job already made from each one, if any.',
     'inputSchema': _schema({'folder': {'type': 'string', 'description': 'Another folder to look in.'},
                             'limit': {'type': 'integer', 'minimum': 1, 'maximum': 200}})},
]


class ToolError(Exception):
    """A tool could not do its job: shown to the model as the tool's result."""


def _text(s: str) -> dict:
    return {'type': 'text', 'text': s}


def _image(data: bytes) -> dict:
    return {'type': 'image', 'data': base64.b64encode(data).decode(), 'mimeType': 'image/png'}


def _rate(q):
    """Says so when a regular client's own rates (Settings) priced the quote."""
    return f" - {q['client_rate']}'s own rates" if q.get('client_rate') else ''


def _money(v, cur):
    from .bot_orders import _money as fmt
    return fmt(v, cur or '')


def describe(report: dict) -> str:
    """A job in plain words, for the model to reason about."""
    p = report['print']
    lines = [f"Job {report['job_id']}  {report.get('name') or ''}".rstrip(),
             f"Status: {report['status']}   stage: {report.get('stage') or 'new'}"
             + (f"   (a colourway of job {report['colourway_of']})" if report.get('colourway_of') else ''),
             f"Match with the original: {report['accuracy']}% (mean dE2000 {report.get('delta_e')})",
             f"Print: {p['width_in']:g} x {p['height_in']:g} in at {p['dpi']} DPI ({p['width_px']} x {p['height_px']} px)",
             f"Inks ({len(report['inks'])}, suggested {report.get('suggested_inks')}): "
             + ', '.join(f"{i['name']} {i['hex']} {i['coverage']}%" for i in report['inks'])]
    if report.get('underbase'):
        lines.append('White under-base screen: yes')
    warnings = report.get('warnings') or []
    if warnings:
        lines.append('Warnings:')
        lines += [f"- {'STOPS THE JOB' if w['blocking'] else 'note'} [{w['code']}] {w['message']}" for w in warnings]
    else:
        lines.append('Warnings: none')
    q = report.get('quote')
    if q:
        lines.append(f"Quote {q.get('quote_no', '')}: {_money(q['total'], q.get('currency'))} for {q['meters']:g} m "
                     f"({_money(q['per_meter'], q.get('currency'))} per meter)")
    hist = report.get('history') or []
    if hist:
        h = hist[-1]
        lines.append(f"Last change: {h.get('stage')} by {h.get('by') or '?'} {h.get('at', '')} {h.get('note') or ''}".rstrip())
    return '\n'.join(lines)


class LoomLabTools:
    def __init__(self, engine: Engine, inbox: Path):
        self.engine = engine
        self.inbox = inbox

    # -- helpers -----------------------------------------------------------
    def _proof(self, image_id: str) -> bytes:
        return self.engine.fetch(f'/api/image/{image_id}?max_side={PROOF_SIDE}')

    @staticmethod
    def _settings(args: dict) -> dict:
        out = {k: args[k] for k in ('colors', 'width_in', 'fabric', 'underbase', 'trap_px', 'meters', 'client')
               if args.get(k) is not None}
        if out.get('fabric'):
            out['fabric'] = out['fabric'].upper()
        return out

    def _run(self, image_id: str, name: str, args: dict) -> list:
        report = self.engine.post('/api/auto', {'image_id': image_id, 'name': name[:120], **self._settings(args)})
        return [_text(describe(report) + '\n\nThe proof (every screen stacked on the cloth) follows. '
                      'Compare it with the original before marking the job.'),
                _image(self._proof(report['reduced_id']))]

    # -- tools -------------------------------------------------------------
    def separate_design(self, args):
        path = Path(args['file']).expanduser()
        if not path.is_file():
            raise ToolError(f'No file at {path}.')
        if path.suffix.lower() not in DESIGN_TYPES:
            raise ToolError(f'{path.name} is not a design file LoomLab reads ({", ".join(sorted(DESIGN_TYPES))}).')
        up = self.engine.upload(path.read_bytes(), path.name)
        if up.get('layers'):
            raise ToolError(f'{path.name} is a PSD already separated into {len(up["layers"])} screens by a bureau; '
                            'open it in the LoomLab app and export it as it is.')
        return self._run(up['image_id'], path.name, args)

    def rerun_job(self, args):
        old = self.engine.get(f"/api/auto/{args['job_id']}")
        exists = self.engine.post('/api/image/exists', {'ids': [old['source_id']]})
        if old['source_id'] in exists.get('missing', []):
            raise ToolError('The design of this job has been cleared from the engine (it keeps images 48 h). '
                            'Run separate_design on the file again.')
        # everything the job was made with stays, unless asked otherwise: a
        # re-run for another ink count must not quietly change cloth or size
        st = old.get('settings') or {}
        keep = {'client': old.get('client') or None, 'underbase': old.get('underbase'),
                'fabric': st.get('fabric'), 'width_in': st.get('width_in'), 'trap_px': st.get('trap_px'),
                'meters': (old.get('quote') or {}).get('meters')}
        return self._run(old['source_id'], old.get('name') or '',
                         {**keep, **{k: v for k, v in args.items() if k != 'job_id'}})

    def get_job(self, args):
        report = self.engine.get(f"/api/auto/{args['job_id']}")
        out = [_text(describe(report))]
        if args.get('with_original'):
            out += [_text('Original design:'), _image(self._proof(report['source_id']))]
        if args.get('with_proof', True):
            out += [_text('Proof:'), _image(self._proof(report['reduced_id']))]
        return out

    def list_jobs(self, args):
        show, limit = args.get('show') or 'waiting', args.get('limit') or 30
        query = '?status=needs_review&stage=new&limit=' if show == 'waiting' else '?limit='
        r = self.engine.get(f'/api/jobs{query}{1000 if show == "open" else limit}')
        jobs = [j for j in r['jobs'] if show != 'open' or j['stage'] not in ('approved', 'rejected')][:limit]
        if not jobs:
            return [_text('No jobs waiting for a person.' if show == 'waiting' else 'No jobs.')]
        rows = [f"{j['job_id']}  {j['created_at']}  {j['status']:<12} {j['stage']:<9} "
                f"{j['inks']} inks  {j['accuracy']}%  {j.get('name') or ''}"
                + (f"  [{', '.join(w['code'] for w in j['warnings'])}]" if j.get('warnings') else '')
                for j in jobs]
        head = f"{len(jobs)} of {r['total']} job(s); {r.get('attention', 0)} waiting for a person."
        return [_text(head + '\n' + '\n'.join(rows))]

    def mark_job(self, args):
        r = self.engine.post(f"/api/jobs/{args['job_id']}/stage",
                             {'stage': args['stage'], 'by': 'AI operator', 'note': (args.get('note') or '')[:300]})
        return [_text(f"Job {args['job_id']} is now '{r.get('stage', args['stage'])}'.")]

    def quote_job(self, args):
        q = self.engine.post('/api/quote', {'job_id': args['job_id'], 'meters': args['meters'],
                                            'client': (args.get('client') or '')[:60]})
        lines = [f"Quote {q['quote_no']}: {_money(q['total'], q.get('currency'))} for {q['meters']:g} m "
                 f"({_money(q['per_meter'], q.get('currency'))} per meter)" + _rate(q)]
        for label, amount in (q.get('lines') or {}).items():
            lines.append(f"- {label}: {_money(amount, q.get('currency'))}")
        if q.get('gst'):
            lines.append(f"- GST {q.get('gst_percent'):g}%: {_money(q['gst'], q.get('currency'))}")
        lines.append(f"Ink: {q.get('ink_kg')} kg over {q.get('area_sqm')} m2, {q.get('screens')} screens")
        return [_text('\n'.join(lines)), _image(self.engine.fetch(q['image_url']))]

    @staticmethod
    def _screens(report: dict, inks: list, fabric=None) -> list:
        """The job's screens wearing `inks` (one per ink, in the report's order)."""
        layers = report.get('layers') or []
        if len(inks) != len(layers):
            raise ToolError(f'This job has {len(layers)} inks; give exactly {len(layers)} colours, in the order '
                            'get_job lists them.')
        return recoloured(report, inks)

    def preview_colourway(self, args):
        report = self.engine.get(f"/api/auto/{args['job_id']}")
        fabric = (args.get('fabric') or (report.get('settings') or {}).get('fabric') or '#FFFFFF').upper()
        pv = self.engine.post('/api/separation/preview', {'layers': self._screens(report, args['inks']),
                                                          'fabric': fabric, 'max_side': PROOF_SIDE})
        return [_text(f"Job {report['job_id']} with inks {', '.join(c.upper() for c in args['inks'])} on {fabric} "
                      '(same screens):'), _image(self.engine.fetch(pv['url'] + f'?max_side={PROOF_SIDE}'))]

    def make_colourway_job(self, args):
        body = {'colours': [c.upper() for c in args['inks']]}
        body |= {k: args[k] for k in ('fabric', 'meters') if args.get(k)}
        report = self.engine.post(f"/api/auto/{args['job_id']}/colourway", body)
        shelf = report.get('shelf_inks') or []
        return [_text(describe(report) + f"\n\nA colourway of job {args['job_id']}: the same screens."
                      + (f" Shelf inks used: {', '.join(shelf)}." if shelf else '')
                      + ' The proof follows.'), _image(self._proof(report['reduced_id']))]

    def _package_with(self, report: dict, colourways: list) -> bytes:
        st = report.get('settings') or {}
        p = report['print']
        body = {'layers': [{'id': l['id'], 'color': l['color'], 'name': l['name']} for l in report['layers']],
                'dpi': p['dpi'], 'width_in': p['width_px'] / p['dpi'],     # the same pixels as the job's films
                'fabric': st.get('fabric', '#FFFFFF'), 'underbase': bool(report.get('underbase')),
                'trap_px': 0, 'vector': bool(st.get('vector')), 'min_dot_mm': st.get('min_dot_mm') or 0,
                'colourways': [{'name': cw['name'], 'fabric': (cw.get('fabric') or None),
                                'inks': self._screens(report, cw['inks'])} for cw in colourways]}
        if st.get('trap_px'):
            raise ToolError('This job\'s films carry a trap, which is made for one set of inks; run it again '
                            'without trap to add colourways.')
        return self.engine._open(urllib.request.Request(
            self.engine.base + '/api/export/package', data=json.dumps(body).encode(),
            headers={'Content-Type': 'application/json'}))

    def save_package(self, args):
        folder = Path(args['folder']).expanduser()
        if not folder.is_dir():
            raise ToolError(f'No folder at {folder}.')
        report = self.engine.get(f"/api/auto/{args['job_id']}")
        data = (self._package_with(report, args['colourways']) if args.get('colourways')
                else self.engine.fetch(report['package_url']))
        stem = Path(report.get('name') or 'design').stem or 'design'
        path = folder / f"{stem}-{args['job_id'][:8]}-screens.zip"
        n = 2
        while path.exists():                       # never overwrite a package already saved
            path = folder / f"{stem}-{args['job_id'][:8]}-screens-{n}.zip"
            n += 1
        tmp = path.with_name(path.name + '.part')
        tmp.write_bytes(data)
        tmp.replace(path)
        return [_text(f'Saved {path} ({len(data) / 1024 / 1024:.1f} MB).')]

    def find_design(self, args):
        r = self.engine.get('/api/library?limit=20&q=' + urllib.parse.quote(args.get('query') or ''))
        if not r['designs']:
            return [_text('No approved design matches.' if args.get('query') else 'The library is empty: designs '
                          'are kept when a job is marked approved.')]
        rows = [f"{d['id']}  {d['kept_at'][:10]}  {d['name'] or '?'}  client {d['client'] or '-'}  "
                f"{len(d['inks'])} screens  {d['print']['width_in']:g} x {d['print']['height_in']:g} in"
                + (f"  last run {d['last_meters']:g} m" if d.get('last_meters') else '') for d in r['designs']]
        out = [_text(f"{r['total']} match(es), newest first:\n" + '\n'.join(rows))]
        if args.get('with_proofs'):
            for d in r['designs'][:4]:
                if d.get('has_proof'):
                    out += [_text(d['name'] or d['id']), _image(self.engine.fetch(f"/api/library/{d['id']}/proof"))]
        return out

    def repeat_quote(self, args):
        q = self.engine.post('/api/quote', {'library_id': args['library_id'], 'meters': args['meters'],
                                            'client': (args.get('client') or '')[:60]})
        text = (f"Repeat order, quote {q['quote_no']}: {_money(q['total'], q.get('currency'))} for {q['meters']:g} m "
                f"({_money(q['per_meter'], q.get('currency'))} per meter) - no new screens." + _rate(q))
        return [_text(text), _image(self.engine.fetch(q['image_url']))]

    def job_stats(self, args):
        s = self.engine.get(f"/api/stats?days={args.get('days') or 30}")
        if not s.get('designs', s['jobs']):
            return [_text(f"No auto jobs in the last {s['days']} days.")]
        cur = s.get('currency')
        e = s['estimate']
        lines = [f"Last {s['days']} days: {s['designs']} designs ({s['jobs']} runs), {s['auto_ok']} needed nobody "
                 f"({s['auto_ok_percent']}%), "
                 f"{s['needs_review']} held for a person.",
                 'Where they stand: ' + ', '.join(f'{k} {v}' for k, v in sorted(s['stages'].items())),
                 f"Engine time per run: {s['avg_seconds']} s on average."]
        if s['quoted']:
            lines.append(f"Quoted: {_money(s['quoted'], cur)} for {s['meters']:,} m.")
        lines.append(f"Time saved (estimate: {e['manual_minutes_per_design']:g} min by hand, "
                     f"{e['review_minutes_per_design']:g} min to check a held one): about {s['hours_saved']} h, "
                     f"{_money(s['money_saved'], cur)} at {_money(e['staff_cost_per_hour'], cur)}/h.")
        return [_text('\n'.join(lines))]

    def client_summary(self, args):
        q = urllib.parse.urlencode({'days': args.get('days') or 90, 'client': (args.get('client') or '')[:60]})
        r = self.engine.get(f'/api/clients?{q}')
        cur = r.get('currency')
        if not r['clients']:
            return [_text(f"No client orders in the last {r['days']} days"
                          + (f" matching '{args['client']}'." if args.get('client') else '.'))]
        lines = [f"Last {r['days']} days, biggest first:"]
        for c in r['clients'][:40]:
            lines.append(f"- {c['client']}{' (own rates)' if c['own_rates'] else ''}: {c['designs']} designs, "
                         f"{c['approved']} approved ({c['approved_meters']:,} m), {c['rejected']} stopped, "
                         f"{c['waiting']} waiting; {c['repeat_orders']} repeat orders ({c['repeat_meters']:,} m); "
                         f"business {_money(c['business'], cur)}; last {c['last'][:10]}")
        return [_text('\n'.join(lines))]

    def list_inbox(self, args):
        folder = Path(args['folder']).expanduser() if args.get('folder') else self.inbox
        if not folder.is_dir():
            raise ToolError(f'No inbox folder at {folder}. Pass folder=... or set LOOMLAB_INBOX.')
        files = sorted((p for p in folder.rglob('*') if p.is_file() and p.suffix.lower() in DESIGN_TYPES),
                       key=lambda p: p.stat().st_mtime, reverse=True)[:args.get('limit') or 30]
        if not files:
            return [_text(f'No design files in {folder}.')]
        try:
            jobs = self.engine.get('/api/jobs?limit=1000')['jobs']
        except EngineError:
            jobs = []
        made = {}
        for j in reversed(jobs):                   # newest job per file name wins
            made[j.get('name') or ''] = j
        rows = []
        for p in files:
            j = made.get(p.name)
            when = datetime.fromtimestamp(p.stat().st_mtime).strftime('%Y-%m-%d %H:%M')
            rows.append(f"{when}  {p}" + (f"  -> job {j['job_id']} {j['status']} {j['stage']}" if j else '  (no job yet)'))
        return [_text(f'{len(files)} design file(s) in {folder}, newest first:\n' + '\n'.join(rows))]

    def call(self, name: str, args: dict) -> list:
        if name not in {t['name'] for t in TOOLS}:
            raise ToolError(f'Unknown tool {name}.')
        return getattr(self, name)(args or {})


class Server:
    """The MCP conversation: initialize, list the tools, call them."""

    def __init__(self, tools: LoomLabTools):
        self.tools = tools

    def handle(self, msg: dict) -> dict | None:
        mid, method = msg.get('id'), msg.get('method')
        if mid is None:                              # a notification: nothing to answer
            return None
        try:
            result = self._dispatch(method, msg.get('params') or {})
        except _RpcError as e:
            return {'jsonrpc': '2.0', 'id': mid, 'error': {'code': e.code, 'message': str(e)}}
        return {'jsonrpc': '2.0', 'id': mid, 'result': result}

    def _dispatch(self, method, params):
        if method == 'initialize':
            asked = params.get('protocolVersion')
            return {'protocolVersion': asked if asked in PROTOCOLS else PROTOCOLS[0],
                    'capabilities': {'tools': {}},
                    'serverInfo': {'name': 'loomlab', 'version': '1.0'},
                    'instructions': INSTRUCTIONS}
        if method == 'ping':
            return {}
        if method == 'tools/list':
            return {'tools': TOOLS}
        if method == 'tools/call':
            name = params.get('name')
            if name not in {t['name'] for t in TOOLS}:
                raise _RpcError(-32602, f'Unknown tool: {name}')
            try:
                return {'content': self.tools.call(name, params.get('arguments') or {}), 'isError': False}
            except (ToolError, EngineError) as e:
                down = getattr(e, 'down', False)
                text = ('The LoomLab engine is not running on this PC. Start it (run-windows.bat) and try again.'
                        if down else str(e))
                return {'content': [_text(text)], 'isError': True}
            except Exception as e:     # a bad argument must not take the whole server down
                return {'content': [_text(f'{type(e).__name__}: {e}')], 'isError': True}
        raise _RpcError(-32601, f'Method not found: {method}')


class _RpcError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def serve(server: Server, stdin=None, stdout=None) -> None:
    """One JSON-RPC message per line in, one answer per line out."""
    stdin = stdin or sys.stdin.buffer
    stdout = stdout or sys.stdout.buffer
    for raw in stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except ValueError:
            reply = {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'Parse error'}}
        else:
            reply = server.handle(msg) if isinstance(msg, dict) else {
                'jsonrpc': '2.0', 'id': None, 'error': {'code': -32600, 'message': 'Invalid request'}}
        if reply is not None:
            stdout.write(json.dumps(reply, ensure_ascii=False).encode('utf-8') + b'\n')
            stdout.flush()


def setup_text() -> str:
    """What to paste into Claude Desktop / Claude Code on this PC."""
    py = Path(sys.executable)
    script = Path(__file__).resolve()
    desktop = {'mcpServers': {'loomlab': {'command': str(py), 'args': [str(script)]}}}
    where = (r'%APPDATA%\Claude\claude_desktop_config.json' if os.name == 'nt'
             else '~/Library/Application Support/Claude/claude_desktop_config.json (Mac)')
    return ('LoomLab MCP server\n'
            '==================\n'
            'The LoomLab engine must be running (run-windows.bat) while Claude uses it.\n\n'
            f'Claude Desktop: Settings > Developer > Edit Config, or open {where},\n'
            'and put this in it (merge with what is there), then restart Claude Desktop:\n\n'
            + json.dumps(desktop, indent=2) + '\n\n'
            'Claude Code (in a terminal):\n\n'
            f'  claude mcp add loomlab -- "{py}" "{script}"\n\n'
            'Then ask, for example: "LoomLab inbox me naye designs dekho, sab chalao, '
            'aur jo theek na ho wo mujhe batao."\n')


def desktop_config_path() -> Path:
    """Where Claude Desktop keeps its settings on this PC."""
    if os.name == 'nt':
        return Path(os.environ.get('APPDATA') or Path.home() / 'AppData' / 'Roaming') / 'Claude' / 'claude_desktop_config.json'
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / 'Claude' / 'claude_desktop_config.json'
    return Path.home() / '.config' / 'Claude' / 'claude_desktop_config.json'


def install_desktop(path: Path | None = None) -> str:
    """Add LoomLab to Claude Desktop's settings, keeping everything else in
    them (and a copy of the old file next to it). Asked for by the owner
    (setup-claude-windows.bat), never done on its own."""
    path = path or desktop_config_path()
    config = {}
    if path.exists():
        raw = path.read_text(encoding='utf-8-sig')
        try:
            config = json.loads(raw) if raw.strip() else {}
        except ValueError:
            raise SystemExit(f'{path} is not valid JSON, so it was left alone. Fix or delete it, then run this again.')
        if not isinstance(config, dict):
            raise SystemExit(f'{path} is not a Claude Desktop settings file, so it was left alone.')
        path.with_name(path.name + '.bak').write_text(raw, encoding='utf-8')
    servers = config.setdefault('mcpServers', {})
    if not isinstance(servers, dict):
        raise SystemExit(f'{path}: mcpServers is not a list of servers, so it was left alone.')
    servers['loomlab'] = {'command': str(Path(sys.executable)), 'args': [str(Path(__file__).resolve())]}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.part')
    tmp.write_text(json.dumps(config, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    tmp.replace(path)
    return str(path)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if '--setup' in argv:
        print(setup_text())
        return 0
    if '--install-desktop' in argv:
        where = install_desktop()
        print(f'LoomLab Claude Desktop me jud gaya: {where}\n'
              'Claude Desktop band karke dobara kholo. LoomLab (run-windows.bat) bhi chalu rehna chahiye.')
        return 0
    engine = Engine(os.environ.get('LOOMLAB_ENGINE') or 'http://localhost:8003', timeout=900)
    inbox = Path(os.environ.get('LOOMLAB_INBOX') or ROOT / 'Designs-Inbox')
    print(f'LoomLab MCP server: engine {engine.base}, inbox {inbox}', file=sys.stderr)
    try:
        serve(Server(LoomLabTools(engine, inbox)))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
