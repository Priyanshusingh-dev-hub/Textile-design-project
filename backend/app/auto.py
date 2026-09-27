"""Auto mode's judgement: which warnings a finished job raised, and whether it
can go to the press without anyone looking (auto_ok) or needs an operator
(needs_review).

The engines do the colour work; this only reads what they measured against
thresholds the mill sets in `auto-config.json` (or the file AUTO_CONFIG
names). The file is read on every job, so a change needs no restart.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

CONFIG_PATH = Path(os.environ.get('AUTO_CONFIG') or Path(__file__).resolve().parents[1] / 'auto-config.json')

DEFAULTS = {
    # all-pixel match (%) below which a job needs a look
    'min_accuracy': 85.0,
    # the best match any ink count reaches (%): below it the design is
    # continuous-tone, which flat inks cannot print (the app's own warning uses 80)
    'photographic_ceiling': 80.0,
    # more screens than this is a costly job someone should agree to
    'max_inks': 12,
    # dots smaller than this (mm across, at the print size) won't hold on the mesh
    'tiny_dot_mm': 0.2,
    # ... a problem once they are more than this % of the printed area
    'max_tiny_dot_share': 0.5,
    # clean those dots in the package (give them to the ink around them); 0 = off
    'clean_dots_mm': 0.0,
    # enlarged prints: fewer source pixels per inch than this and fine detail
    # (outlines, filigree) comes out coarse
    'min_source_ppi': 100.0,
    # the warnings that stop a job; the others are reported but pass
    'blocking': ['photographic', 'low_match', 'soft_edges', 'tiny_dots',
                 'similar_inks', 'many_inks', 'low_resolution'],
}


# One line per warning code, for reports and lists (the full message says more).
TITLES = {
    'photographic': 'photo-like shading (flat inks print it as bands)',
    'low_match': 'match with the original too low',
    'soft_edges': 'soft, feathered edges',
    'tiny_dots': 'dots too small for the mesh',
    'similar_inks': 'two inks almost the same',
    'many_inks': 'more screens than the limit',
    'low_resolution': 'file too small for the print size',
    'grainy_source': 'grainy file, texture cleanup applied',
    'seamless_repeat': 'seamless repeat',
    'small_inks': 'inks under 2% could be dropped',
}


def load_config(path: Path | None = None) -> dict:
    """DEFAULTS overlaid with the config file. A missing file means the
    defaults; a broken one is an error the operator must see, not a silent
    fallback that would pass jobs on thresholds nobody chose."""
    path = path or CONFIG_PATH
    cfg = dict(DEFAULTS)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding='utf-8-sig'))
        except ValueError as e:
            raise ValueError(f'{path.name} is not valid JSON: {e}') from None
        unknown = set(data) - set(DEFAULTS) - {'_comment'}
        if unknown:
            raise ValueError(f'{path.name}: unknown setting(s) {", ".join(sorted(unknown))}')
        cfg.update({k: v for k, v in data.items() if k != '_comment'})
    return cfg


def review(facts: dict, cfg: dict) -> tuple[list[dict], str]:
    """(warnings, status) for one job's measured `facts`.

    facts: accuracy, ceiling (best match on the ink-count curve), inks,
    soft_edge (px), soft_edge_limit (px), dot_share (% of printed pixels in
    dots under tiny_dot_mm, or None if not measured), similar (near-duplicate
    ink pairs), source_ppi (None at the design's own size), grain level
    (cleanup applied), repeat (axes that carry design across the edge),
    small (inks under 2% that could go)."""
    blocking = set(cfg['blocking'])
    warnings = []

    def warn(code, message, **data):
        warnings.append({'code': code, 'blocking': code in blocking, 'message': message} | data)

    if facts['ceiling'] < cfg['photographic_ceiling']:
        warn('photographic', f"Smooth, photographic shading: even the most inks tried reach only "
             f"{facts['ceiling']:.0f}%. Flat spot colours print it as bands; it needs halftones.",
             ceiling=facts['ceiling'])
    if facts['accuracy'] < cfg['min_accuracy']:
        warn('low_match', f"{facts['accuracy']}% match with the original (the limit is "
             f"{cfg['min_accuracy']:g}%). Check the proof before making screens.", accuracy=facts['accuracy'])
    if facts['soft_edge'] > facts['soft_edge_limit']:
        warn('soft_edges', f"Soft, feathered edges about {facts['soft_edge']:.0f}px wide: a flat ink "
             "prints them as a hard edge at the halfway point.", width_px=facts['soft_edge'])
    if facts['dot_share'] is not None and facts['dot_share'] > cfg['max_tiny_dot_share']:
        warn('tiny_dots', f"{facts['dot_share']:.1f}% of the printed area is dots under "
             f"{cfg['tiny_dot_mm']:g} mm, too small for the mesh to hold.", share=facts['dot_share'])
    if facts['similar']:
        p = facts['similar'][0]
        warn('similar_inks', f"Inks {p['keep']} and {p['drop']} look almost the same (dE {p['delta_e']}): "
             f"merging them saves a screen for a match of {p['accuracy']}%.", pairs=facts['similar'])
    if facts['inks'] > cfg['max_inks']:
        warn('many_inks', f"{facts['inks']} screens, more than the {cfg['max_inks']} set as the limit.")
    if facts['source_ppi'] is not None and facts['source_ppi'] < cfg['min_source_ppi']:
        warn('low_resolution', f"Enlarged to only {facts['source_ppi']:.0f} source pixels per inch: fine "
             "outlines and filigree come out coarse. A larger original prints better.",
             source_ppi=round(facts['source_ppi'], 1))
    if facts['grain']:
        warn('grainy_source', 'The file is grainy (a scan or a photo of cloth); texture cleanup was applied.')
    if facts['repeat']:
        warn('seamless_repeat', f"Seamless repeat ({' and '.join(facts['repeat'])}): processed wrapped "
             'round, so the join stays invisible.')
    if facts['small']:
        warn('small_inks', f"{len(facts['small'])} ink(s) cover under 2% and could be dropped to save "
             'screens with little visible change.', inks=facts['small'])
    status = 'needs_review' if any(w['blocking'] for w in warnings) else 'auto_ok'
    return warnings, status
