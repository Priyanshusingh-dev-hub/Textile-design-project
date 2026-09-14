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

        preserve, change, improve = self._buckets(dna, intent, fidelity, flags, comp, motif, n_colors, mergeable)
        textile = self._textile_rules(intent, flags)
        color_line = self._color_line(intent, flags, dna, mergeable)

        instruction = self._compose_instruction(intent, band_name, band_line, preserve, change, improve, color_line, textile, description)
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
            return 'Apply the requested new colour palette; keep colours flat, distinct and printable.'
        if intent == 'print_optimization':
            base = 'Target a small set of clean, distinct print colours (around %d).' % max(3, n - len(mergeable))
            return base + ' Avoid near-identical colours, unintended gradients and semi-transparent overlaps.'
        return 'Maintain the existing colour relationships; keep colours flat and distinct.' + (
            ' Merge visually redundant colours where possible.' if mergeable else '')

    def _textile_rules(self, intent, flags):
        rules = ['Produce a clean, seamless, tileable repeat.',
                 'Keep crisp motif boundaries suitable for colour separation.',
                 'Use flat, solid colour regions; avoid unintended gradients or semi-transparency.']
        if intent == 'print_optimization' or flags.get('target_colors'):
            rules.append('Avoid tiny isolated details that will not hold on a printing screen.')
        rules.append('Render at high resolution for production use.')
        return rules

    def _compose_instruction(self, intent, band_name, band_line, preserve, change, improve, color_line, textile, description):
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
        L.append('COLOR:')
        L.append(color_line)
        L.append('')
        L.append('TEXTILE REQUIREMENTS:')
        L += ['- ' + x for x in textile]
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
