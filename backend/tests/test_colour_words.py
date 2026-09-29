"""Colours as clients write them, for the bot's colourway preview."""
import pytest

from app import colour_words as C

INKS = ['#E1D2BB', '#68563C', '#D0406E', '#2E4A2A']      # beige, brown, rani pink, bottle green


@pytest.mark.parametrize('text,hx', [
    ('neela', '#1F5FBF'), ('Navy Blue', '#1B2A4A'), ('#1b2a4a', '#1B2A4A'), ('1B2A4A', '#1B2A4A'),
    ('mehroon kar do', '#7A1F2B'), ('dark green', '#0F4A2A'), ('sky blue', '#86C7EA'),
    ('kuch sundar', None), ('', None),
])
def test_a_colour_is_read_from_hinglish_english_or_its_code(text, hx):
    assert C.lookup(text) == hx


def test_light_and_dark_shift_a_colour_the_list_does_not_name():
    assert C.lookup('halka neela') not in (None, C.lookup('neela'))
    assert C.distance(C.lookup('gehra peela'), '#000000') < C.distance(C.lookup('peela'), '#000000')


@pytest.mark.parametrize('text,changes,cloth,unread', [
    ('pink ko neela', {2: '#1F5FBF'}, None, []),
    ('1 navy, kapda kala', {0: '#1B2A4A'}, '#141414', []),
    ('3 = #1b2a4a aur 2 wala cream', {2: '#1B2A4A', 1: '#F2E8CF'}, None, []),
    ('hara ki jagah sarson', {3: '#D1A11A'}, None, []),
    ('9 navy', {}, None, ['9 navy']),                          # there is no ink 9
    ('purple ko cream', {}, None, ['purple ko cream']),          # nothing purple in the design
])
def test_a_request_names_inks_by_number_or_by_their_colour(text, changes, cloth, unread):
    assert C.parse(text, INKS) == (changes, cloth, unread)


def test_inks_are_named_for_the_client_and_bas_cancels():
    assert [C.name_of(h) for h in INKS] == ['beige', 'brown', 'rani pink', 'bottle green']
    assert C.is_cancel('Bas') and C.is_cancel('rehne do') and not C.is_cancel('1 navy')
