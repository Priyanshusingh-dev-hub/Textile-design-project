"""The truth benchmark (app/truth_bench.py): degrading is repeatable, and the
app's Reduce beats the generic quantizers against a known truth."""
import numpy as np

from app import truth_bench as tb


def test_degrading_is_repeatable_and_really_degrades():
    _, truth = next(tb.truths(200))
    a, b = tb.degrade(truth, 'mild'), tb.degrade(truth, 'mild')
    assert (a == b).all()
    assert len(np.unique(a.reshape(-1, 3), axis=0)) > 200 * len(np.unique(truth.reshape(-1, 3), axis=0)) // 100
    assert (tb.degrade(truth, 'heavy') != truth).any(-1).mean() > 0.9


def test_agreement_and_edge_share_on_known_cases():
    t = np.zeros((20, 20, 3), np.uint8)
    t[:, 10:] = (200, 50, 50)
    assert tb.agreement(t, t) == 100.0
    assert tb.edge_share(t) == 5.0                          # one column of 20 touches the seam: 20 of 400 px


def test_the_apps_reduce_beats_generic_quantizers_against_the_truth():
    ours = tb.score(tb.engine, ('mild',), 260, verbose=False)
    pil = tb.score(tb.pillow_mediancut, ('mild',), 260, verbose=False)
    assert ours['truth_match'] > pil['truth_match'] + 3
    assert ours['agreement'] > pil['agreement']
    assert ours['extra_edge'] < pil['extra_edge']
