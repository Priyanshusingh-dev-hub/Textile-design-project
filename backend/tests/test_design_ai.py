import numpy as np
import pytest
from PIL import Image
from app.design_ai import analyzer, instructions
from app.design_ai.instructions import parse_request, fidelity_band, TemplateInstructionEngine, INTENTS

def _floral(size=200):
    from PIL import ImageDraw
    im = Image.new('RGB', (size, size), '#F4E8CC'); d = ImageDraw.Draw(im)
    for y in range(0, size, 60):
        for x in range(0, size, 60):
            d.ellipse((x+8, y+8, x+40, y+40), fill='#C95368')
            d.ellipse((x+18, y+18, x+30, y+30), fill='#D9A43E')
    return im

def _two_color():
    a = np.zeros((40, 40, 3), dtype=np.uint8); a[:, :20] = (200, 30, 30); a[:, 20:] = (240, 230, 210)
    return Image.fromarray(a)

# ---------- analyzer ----------
def test_dna_has_core_sections():
    dna = analyzer.build_dna(_floral())
    for key in ['style', 'motif_family', 'composition', 'colors', 'background', 'distinct_colors', 'visual_character', 'production_notes']:
        assert key in dna

def test_dna_motif_is_unspecified_without_description():
    dna = analyzer.build_dna(_floral())
    assert dna['motif_family'] == ['unspecified']
    assert dna['motif_family_source'] == 'unspecified'

def test_dna_motif_from_description():
    dna = analyzer.build_dna(_floral(), 'traditional mughal floral with paisley buta')
    assert 'floral' in dna['motif_family'] or 'paisley' in dna['motif_family']
    assert dna['style']['sub_style'] == 'Mughal-inspired'

def test_dna_detects_two_distinct_colors():
    dna = analyzer.build_dna(_two_color())
    assert dna['distinct_colors'] == 2

def test_dna_flags_near_identical_colors():
    a = np.zeros((40, 40, 3), dtype=np.uint8)
    a[:, :14] = (200, 30, 30); a[:, 14:28] = (204, 34, 34); a[:, 28:] = (30, 30, 200)  # first two nearly identical
    dna = analyzer.build_dna(Image.fromarray(a))
    assert len(dna['mergeable_colors']) >= 1

def test_dna_grayscale_image():
    g = Image.new('L', (60, 60), 128).convert('RGB')
    dna = analyzer.build_dna(g)
    assert dna['distinct_colors'] >= 1

def test_dna_transparent_png():
    im = Image.new('RGBA', (60, 60), (200, 30, 30, 0))
    dna = analyzer.build_dna(im)
    assert 'colors' in dna

def test_dna_tiny_image():
    dna = analyzer.build_dna(Image.new('RGB', (3, 3), '#A83E48'))
    assert dna['distinct_colors'] >= 1

# ---------- request parsing ----------
def test_parse_target_colors():
    assert parse_request('reduce to 5 colors')['target_colors'] == 5

def test_parse_reduce_to_n_does_not_trigger_recolor():
    f = parse_request('reduce to 5 colors')
    assert 'recolor' not in f

def test_parse_explicit_recolor():
    assert parse_request('keep everything same but change the colours')['recolor'] is True

def test_parse_density_and_product():
    f = parse_request('make it less crowded and lay it out for a saree')
    assert f.get('reduce_density') and f.get('product') == 'saree'

# ---------- fidelity ----------
@pytest.mark.parametrize('f,expected', [(95, 'near recreation'), (80, 'very close variation'), (50, 'strong variation'), (20, 'style reference')])
def test_fidelity_bands(f, expected):
    assert fidelity_band(f)[0] == expected

def test_high_fidelity_preserves_more_than_low():
    dna = analyzer.build_dna(_floral(), 'floral')
    hi = instructions.generate(dna, 'premium_improvement', 95)['instruction']
    lo = instructions.generate(dna, 'same_style_new', 20)['instruction']
    assert 'as closely as possible' in hi
    assert 'loose inspiration' in lo or 'substantial' in lo

# ---------- intents ----------
@pytest.mark.parametrize('intent', list(INTENTS.keys()))
def test_every_intent_generates_nonempty(intent):
    dna = analyzer.build_dna(_floral(), 'floral')
    out = instructions.generate(dna, intent, 70, 'make flowers premium')
    assert 'PRESERVE:' in out['instruction'] or intent == 'same_style_new'
    assert len(out['instruction']) > 100
    assert 'DESIGN ANALYSIS' in out['brief']

def test_color_change_preserves_shapes():
    dna = analyzer.build_dna(_floral(), 'floral')
    out = instructions.generate(dna, 'color_change', 90, 'change the colours to blue tones')
    assert 'placement exactly' in out['instruction'] or 'boundary intact' in out['instruction']

def test_print_optimization_mentions_print_constraints():
    dna = analyzer.build_dna(_floral(), 'floral')
    out = instructions.generate(dna, 'print_optimization', 60, '')
    assert 'gradients' in out['instruction'].lower()

def test_target_colors_in_request_reflected():
    dna = analyzer.build_dna(_floral(), 'floral')
    out = instructions.generate(dna, 'premium_improvement', 80, 'reduce it to 5 print colors')
    assert 'exactly 5' in out['instruction']

def test_instructions_are_specific_not_generic():
    dna = analyzer.build_dna(_floral(), 'floral')
    out = instructions.generate(dna, 'premium_improvement', 85, 'make flowers more premium')
    assert 'beautiful' not in out['instruction'].lower()
    assert 'PRESERVE:' in out['instruction'] and 'TEXTILE REQUIREMENTS:' in out['instruction']

def test_missing_description_and_request_still_works():
    dna = analyzer.build_dna(_floral())
    out = instructions.generate(dna, 'premium_improvement', 85, '')
    assert len(out['instruction']) > 100

def test_depth_section_present_for_creative_intents():
    dna = analyzer.build_dna(_floral(), 'floral')
    out = instructions.generate(dna, 'premium_improvement', 85, '')
    ins = out['instruction']
    assert 'RENDERING & DEPTH:' in ins
    assert 'must NOT look flat, hollow or empty' in ins
    assert 'CONSISTENCY:' in ins and 'AVOID:' in ins
    assert 'hollow' in ins.lower()

def test_depth_gives_dimensional_directives_for_floral():
    dna = analyzer.build_dna(_floral(), 'floral botanical')
    ins = instructions.generate(dna, 'premium_improvement', 85, '')['instruction']
    assert 'overlapping petals' in ins
    assert 'vein' in ins.lower()

def test_print_optimization_stays_flat_and_graphic():
    dna = analyzer.build_dna(_floral(), 'floral')
    ins = instructions.generate(dna, 'print_optimization', 60, '')['instruction']
    assert 'flat shapes' in ins or 'flat, solid colour regions' in ins
    assert 'must NOT look flat' not in ins

def test_explicit_flatten_request_drops_depth():
    dna = analyzer.build_dna(_floral(), 'floral')
    ins = instructions.generate(dna, 'premium_improvement', 85, 'make it a flat block-print look')['instruction']
    assert 'bold and graphic' in ins

def test_depth_avoids_smooth_gradients_not_all_depth():
    dna = analyzer.build_dna(_floral(), 'floral')
    ins = instructions.generate(dna, 'premium_improvement', 85, '')['instruction']
    assert 'discrete shade steps' in ins
    assert 'photographic gradients' in ins
