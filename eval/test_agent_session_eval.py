from eval.agent_session_eval import file_ranks, wilson
from eval.agent_session_recall import identifier_tokens


def test_identifier_leg_keeps_code_like_tokens_and_drops_prose():
    text = "where are KNOWN_TIERS and settings.py, PRD 00058: the setup-python pin"
    assert identifier_tokens(text) == [
        "KNOWN_TIERS",
        "settings.py",
        "PRD",
        "00058",
        "setup-python",
    ]


def test_excludes_the_question_s_own_session_from_ranking():
    paths = ["/t/abc123.jsonl", "/a.py", "/a.py", "/b.py"]
    assert file_ranks(paths, {"/b.py"}, "abc123") == 2


def test_misses_when_no_label_in_ranking():
    assert file_ranks(["/a.py"], {"/z.py"}, "none") is None


def test_wilson_lower_bound_needs_enough_samples():
    # 60% observed is not enough at n=30 (lower bound 0.42); 80% is.
    assert wilson(18, 30)[0] < 0.5 < wilson(24, 30)[0]
