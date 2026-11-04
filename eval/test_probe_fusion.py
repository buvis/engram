from types import SimpleNamespace

from eval.probe_fusion import fuse


def _hit(i):
    return SimpleNamespace(chunk_id=i, chunk=SimpleNamespace(path=str(i), line_start=1))


def test_equal_scores_keep_first_leg_first():
    lexical, dense = [_hit(1)], [_hit(2)]
    assert [h.chunk_id for h in fuse([(lexical, 1.0), (dense, 1.0)])] == [1, 2]
    assert [h.chunk_id for h in fuse([(dense, 1.0), (lexical, 1.0)])] == [2, 1]


def test_agreement_outranks_single_leg_hits():
    a, b = [_hit(1), _hit(2)], [_hit(2), _hit(3)]
    assert fuse([(a, 1.0), (b, 1.0)])[0].chunk_id == 2


def test_weight_changes_order():
    lexical, dense = [_hit(1)], [_hit(2)]
    assert fuse([(lexical, 1.0), (dense, 2.0)])[0].chunk_id == 2
