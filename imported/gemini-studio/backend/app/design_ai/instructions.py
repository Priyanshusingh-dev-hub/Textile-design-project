"""Instruction generation.

Modular by design so a future LocalLLMInstructionEngine or APIInstructionEngine
can be dropped in behind the same interface. The current, and only wired,
engine is TemplateInstructionEngine — pure string templating over the Design
DNA, with no external calls. It turns (DNA + intent + fidelity + user request
+ description + production constraints) into a human brief and a copy-ready
instruction split into PRESERVE / CHANGE / IMPROVE.
"""
import re

INTENTS = {
    'exact_recreation':    'Exact recreation',
    'premium_improvement': 'Premium improvement',
    'color_change':        'Color change',
    'new_variation':       'New variation',
    'same_style_new':      'Same style — new design',
    'print_optimization':  'Print optimization',
}

def fidelity_band(f):
    if f >= 90: return 'near recreation', 'Preserve motif arrangement, scale relationships, composition and overall visual identity as closely as possible.'
    if f >= 75: return 'very close variation', 'Preserve the composition, motif hierarchy and colour relationships; allow only light reinterpretation.'
    if f >= 50: return 'strong variation', 'Keep the motif language, density and colour character; allow moderate compositional variation.'
    if f >= 20: return 'style reference', 'Use the reference primarily for style, motif language and colour relationships while allowing substantial compositional variation.'
    return 'loose inspiration', 'Treat the reference as loose inspiration only; a substantially new composition is acceptable.'

def parse_request(text):
    """Turn the free-text request into explicit change flags. Nothing is
    invented — a flag is set only when the user's words ask for it."""
    t = (text or '').lower()
    flags = {}
    m = re.search(r'(\d+)\s+(?:\w+\s+){0,2}(?:colou?rs?|shades?|inks?|screens?)', t)
    if m: flags['target_colors'] = int(m.group(1))
    # recolour only on an explicit "change the colours" style request, not the
    # bare word "colours" (which also appears in "reduce to 5 colours")
    if any(p in t for p in ['recolor', 'recolour', 'change color', 'change colour', 'change the color', 'change the colour',
                            'new color', 'new colour', 'different color', 'different colour', 'change palette', 'new palette', 'colour change', 'color change']):
        flags['recolor'] = True
    if any(w in t for w in ['less crowded', 'crowded', 'less dense', 'reduce density', 'more space', 'spacing', 'breathing']): flags['reduce_density'] = True
    if any(w in t for w in ['more dense', 'denser', 'fill', 'busier']): flags['increase_density'] = True
    if any(w in t for w in ['premium', 'luxurious', 'refined', 'elegant', 'high-end', 'rich']): flags['premium'] = True
    if any(w in t for w in ['bigger', 'larger', 'bigger motif', 'scale up']): flags['scale_up'] = True
    if any(w in t for w in ['smaller', 'finer', 'delicate']): flags['scale_down'] = True
    if any(w in t for w in ['simplify', 'cleaner', 'clean up', 'minimal']): flags['simplify'] = True
    if any(w in t for w in ['depth', 'richer', 'rich ', '3d', 'three-dimensional', 'shading', 'shaded', 'dimensional', 'not flat', 'less flat', 'more detail', 'detailed', 'realistic']): flags['depth'] = True
    if any(w in t for w in ['flat', 'flatter', 'block print', 'block-print', 'poster']): flags['flatten'] = True
    for product in ['saree', 'sari', 'dupatta', 'kurta', 'lehenga', 'suit', 'blouse', 'border', 'scarf']:
        if product in t: flags['product'] = product
    return flags


class InstructionEngine:
    def generate(self, dna, intent, fidelity, user_request, description, target_colors=None):
        raise NotImplementedError


class TemplateInstructionEngine(InstructionEngine):
    def generate(self, dna, intent='premium_improvement', fidelity=85, user_request='', description='', target_colors=None):
        intent = intent if intent in INTENTS else 'premium_improvement'
        fidelity = max(0, min(100, int(fidelity)))
        flags = parse_request(user_request)
        if target_colors: flags['target_colors'] = target_colors

        comp = dna.get('composition', {})
        motif = ', '.join(dna.get('motif_family', ['unspecified']))
        n_colors = dna.get('distinct_colors', 0)
        mergeable = dna.get('mergeable_colors', [])
        band_name, band_line = fidelity_band(fidelity)

        # Depth on by default for every creative intent; only print-optimisation
        # (or an explicit "flat/block-print" request) drops it. This is the fix
        # for hollow, lifeless AI output: the artwork gets real dimensional
        # rendering while staying separable.
        want_depth = flags.get('depth', False) or (intent != 'print_optimization' and not flags.get('flatten'))

        preserve, change, improve = self._buckets(dna, intent, fidelity, flags, comp, motif, n_colors, mergeable)
        textile = self._textile_rules(intent, flags, want_depth)
        color_line = self._color_line(intent, flags, dna, mergeable)
        depth = self._depth_rules(want_depth, comp, motif)
        consistency = self._consistency_rules(comp, motif)
        avoid = self._avoid_rules(want_depth)

        instruction = self._compose_instruction(intent, band_name, band_line, preserve, change, improve,
                                                depth, color_line, textile, consistency, avoid, description)
        brief = self._compose_brief(dna, intent, fidelity, band_name, motif, n_colors, comp, user_request)
        return {
            'brief': brief,
            'instruction': instruction,
            'detected': dna.get('detected', []),
            'user_provided': dna.get('from_description', []),
        }

    def _buckets(self, dna, intent, fidelity, flags, comp, motif, n_colors, mergeable):
        density = comp.get('density', 'medium')
        preserve, change, improve = [], [], []

        # PRESERVE — scales with fidelity and intent
        keep_motif = 'the motif family (%s)' % motif if motif != 'unspecified' else 'the overall motif language'
        if intent in ('exact_recreation', 'premium_improvement', 'color_change', 'new_variation'):
            preserve += [keep_motif, 'the motif hierarchy (major, secondary and filler elements)']
        if intent in ('exact_recreation', 'premium_improvement', 'color_change') or fidelity >= 75:
            preserve += ['the overall composition and layout', 'the general repeat character']
        if fidelity >= 50:
            preserve += ['the ' + density + ' motif density', 'the overall visual character']
        if intent == 'color_change':
            preserve += ['every motif shape and its placement exactly']
        if intent == 'same_style_new':
            preserve = ['the design language and motif family (%s)' % motif if motif != 'unspecified' else 'the overall design language',
                        'the colour character and level of detail']

        # CHANGE — only what the user asked for (or the intent implies)
        if intent == 'color_change' or flags.get('recolor'):
            change.append('recolour the design to the requested new palette while keeping every shape and boundary intact')
        if flags.get('target_colors'):
            change.append('reduce to exactly %d printable colours' % flags['target_colors'])
        if flags.get('reduce_density'):
            change.append('reduce motif crowding and open up the spacing between major motifs')
        if flags.get('increase_density'):
            change.append('increase motif density and fill more of the ground')
        if flags.get('scale_up'):
            change.append('increase the scale of the primary motifs')
        if flags.get('scale_down'):
            change.append('make the motifs finer and more delicate')
        if flags.get('product'):
            change.append('re-lay the composition for a %s layout' % flags['product'])
        if intent == 'new_variation':
            change.append('introduce a fresh arrangement of the same motif family while keeping its identity')
        if intent == 'same_style_new':
            change.append('create a substantially new composition in the same style rather than reproducing the reference')

        # IMPROVE — safe refinements that don't change identity
        if intent in ('premium_improvement', 'new_variation') or flags.get('premium'):
            improve += ['refine the primary motif geometry without changing its identity',
                        'improve consistency of motif scale and spacing',
                        'clean up balance and visual rhythm']
        if flags.get('simplify'):
            improve.append('simplify fussy micro-detail that will not print cleanly')
        if mergeable and not flags.get('recolor') and intent != 'color_change':
            improve.append('merge %d near-identical colour pair(s) to reduce redundant screens' % len(mergeable))
        if comp.get('contrast') == 'low' and intent != 'exact_recreation':
            improve.append('lift contrast slightly for cleaner separation')
        if intent == 'exact_recreation':
            improve = ['only clean up scan noise and ragged edges; make no creative changes']

        # de-duplicate while preserving order
        dedup = lambda xs: list(dict.fromkeys(xs))
        return dedup(preserve), dedup(change), dedup(improve)

    def _color_line(self, intent, flags, dna, mergeable):
        n = dna.get('distinct_colors', 0)
        if flags.get('target_colors'):
            return 'Target palette: exactly %d distinct, printable spot colours.' % flags['target_colors']
        if intent == 'color_change' or flags.get('recolor'):
            return 'Apply the requested new colour palette; keep every colour distinct and cleanly separable.'
        if intent == 'print_optimization':
            base = 'Target a small set of clean, distinct print colours (around %d).' % max(3, n - len(mergeable))
            return base + ' Avoid near-identical colours, unintended gradients and semi-transparent overlaps.'
        return 'Maintain the existing colour relationships; keep every colour distinct and cleanly separable.' + (
            ' Merge visually redundant colours where possible.' if mergeable else '')

    def _textile_rules(self, intent, flags, want_depth):
        rules = ['Produce a clean, seamless, tileable repeat with motifs and stems that continue naturally across every tile edge.',
                 'Keep crisp, well-defined motif boundaries with a consistent keyline so the artwork separates cleanly into flat printable colours.']
        if want_depth:
            rules.append('Build depth with layered detail and controlled tonal steps within each colour — NOT with smooth photographic gradients — so the design stays rich yet fully separable.')
        else:
            rules.append('Use flat, solid colour regions; avoid gradients and semi-transparency.')
        if intent == 'print_optimization' or flags.get('target_colors'):
            rules.append('Avoid tiny isolated details that will not hold on a printing screen.')
        rules.append('Render at high resolution for production use.')
        return rules

    def _depth_rules(self, want_depth, comp, motif):
        """The key fix for hollow, lifeless output: tell the generator HOW to
        build dimensional richness while staying print-separable."""
        if not want_depth:
            return ['Keep motifs as clean, confident flat shapes with a strong silhouette and a crisp keyline — bold and graphic rather than shaded.']
        is_floral = any(w in motif for w in ('floral', 'botanical', 'creeper', 'paisley', 'ornamental'))
        rules = [
            'Give every motif real dimensional depth — this design must NOT look flat, hollow or empty.',
        ]
        if is_floral:
            rules += [
                'Render each flower with fully layered, overlapping petals, a defined detailed centre (stamens / seed head), and clear front-to-back layering between blooms, buds and leaves.',
                'Draw leaves with a central vein, secondary veins and serrated edges; vary their angle and curl so the foliage reads as a living creeper, not repeated stamps.',
            ]
        else:
            rules.append('Render each motif with internal structure and layered elements so it has visible form and weight, not an empty outline.')
        rules += [
            'Create tonal depth WITHIN each ink colour using 2-3 discrete shade steps (a shadow tone and a highlight tone of the same hue) or fine hand-drawn shading such as hatching or stippling — never smooth blended gradients.',
            'Use a single, consistent light direction across the entire repeat so highlights and shadows agree everywhere.',
            'Add crisp keyline outlines and small accent details (dots, veins, centres) to give the pattern a hand-drawn, engraved, printed-textile richness.',
        ]
        return rules

    def _consistency_rules(self, comp, motif=''):
        geometric = any(w in motif for w in ('geometric',)) or comp.get('symmetry') == 'symmetrical'
        rules = [
            'Draw every shape with clean, smooth, VECTOR-QUALITY edges and a uniform line weight — the crisp, redrawn look of professional pen-tool / Illustrator artwork, never jagged, wobbly, fuzzy or ragged outlines.',
            'Hold ONE coherent drawing style, line weight and level of detail across the whole pattern — every motif must look drawn by the same hand.',
            'Keep repeated elements truly identical and precisely aligned to a consistent grid/baseline, so the same motif matches perfectly everywhere it recurs.',
            'Keep motif scale relationships consistent; do not let some motifs blur, melt, distort or drift out of proportion.',
            'Distribute the motifs on a disciplined, even, truly seamless repeat with no visible seams, gaps, empty patches or torn areas.',
        ]
        if geometric:
            rules.append('For the geometric bands/borders, make every repeat unit mechanically exact and mirror-clean, like a hand-redrawn vector tile.')
        return rules

    def _avoid_rules(self, want_depth):
        rules = [
            'flat, hollow or lifeless motifs with no internal detail',
            'smudged, melted, warped or half-formed shapes',
            'jagged, wobbly, fuzzy or hand-shaky outlines (edges must be clean and vector-crisp)',
            'broken, mismatched or visibly seamed repeats',
            'inconsistent motif style, random scale jumps or areas that fall apart',
            'blurry or soft edges, and muddy blended colours that cannot be separated',
        ]
        if want_depth:
            rules.append('smooth photographic gradients (use discrete shade steps or line shading instead)')
        return rules

    def _compose_instruction(self, intent, band_name, band_line, preserve, change, improve, depth, color_line, textile, consistency, avoid, description):
        L = []
        L.append('Use the uploaded textile design as the primary visual reference (the source of truth).')
        L.append('')
        L.append('INTENT: %s (%s).' % (INTENTS[intent], band_name))
        L.append(band_line)
        if description:
            L.append('')
            L.append('REFERENCE NOTES (from the user): ' + description.strip())
        if preserve:
            L.append('')
            L.append('PRESERVE:')
            L += ['- ' + x for x in preserve]
        if change:
            L.append('')
            L.append('CHANGE:')
            L += ['- ' + x for x in change]
        if improve:
            L.append('')
            L.append('IMPROVE:')
            L += ['- ' + x for x in improve]
        L.append('')
        L.append('RENDERING & DEPTH:')
        L += ['- ' + x for x in depth]
        L.append('')
        L.append('COLOR:')
        L.append(color_line)
        L.append('')
        L.append('TEXTILE REQUIREMENTS:')
        L += ['- ' + x for x in textile]
        L.append('')
        L.append('CONSISTENCY:')
        L += ['- ' + x for x in consistency]
        L.append('')
        L.append('AVOID:')
        L += ['- ' + x for x in avoid]
        L.append('')
        if intent == 'same_style_new':
            L.append('The result should be a new design in the same visual language as the reference, not a copy of it.')
        elif intent == 'exact_recreation':
            L.append('The result should be as faithful to the reference as possible — a clean reproduction, not a reinterpretation.')
        else:
            L.append('The result should read as a professionally refined version of the reference design, not an unrelated new design.')
        return '\n'.join(L)

    def _compose_brief(self, dna, intent, fidelity, band_name, motif, n_colors, comp, user_request):
        style = dna.get('style', {})
        bg = dna.get('background', {})
        L = []
        L.append('DESIGN ANALYSIS')
        L.append('')
        L.append('Style: ' + (style.get('category', 'unspecified') + (' · ' + style.get('sub_style') if style.get('sub_style') not in ('unspecified', None) else '')))
        L.append('Motif family: ' + motif)
        L.append('Density: ' + comp.get('density', '—'))
        L.append('Composition: ' + comp.get('symmetry', '—') + ', ' + comp.get('negative_space', '—') + ' negative space')
        L.append('Contrast: ' + comp.get('contrast', '—') + ' · Detail: ' + comp.get('detail', '—'))
        L.append('Palette: %d distinct colours (background %s)' % (n_colors, bg.get('hex', '—')))
        L.append('Visual character: ' + dna.get('visual_character', '—'))
        L.append('')
        L.append('DIRECTION')
        L.append('Intent: %s (fidelity %d%% — %s).' % (INTENTS[intent], fidelity, band_name))
        if user_request.strip():
            L.append('User request: ' + user_request.strip())
        notes = dna.get('production_notes', [])
        if notes:
            L.append('')
            L.append('PRODUCTION NOTES')
            L += ['- ' + n for n in notes]
        return '\n'.join(L)


_ENGINE = TemplateInstructionEngine()

def generate(dna, intent='premium_improvement', fidelity=85, user_request='', description='', target_colors=None):
    return _ENGINE.generate(dna, intent, fidelity, user_request, description, target_colors)
