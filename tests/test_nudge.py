import io
import json
import os
import shlex

import pytest

from engram import nudge
from engram.client import EmbeddingServerError
from engram.query import Pointer

FOOTER_TEXT = "Read a cited range if it is relevant; ignore it if not."


def make_pointer(rank: int, path: str, line_start: int, line_end: int, heading: str) -> Pointer:
    return Pointer(
        rank=rank,
        score=1.0 - rank / 10,
        path=path,
        line_start=line_start,
        line_end=line_end,
        heading=heading,
        corpus="code",
        repo="buvis/engram",
    )


POINTERS = [
    make_pointer(1, "docs/dev/a.md", 1, 5, "Intro"),
    make_pointer(2, "src/engram/b.py", 10, 42, "def run"),
    make_pointer(3, "notes/plan.md", 7, 9, "Plan"),
]


def expected_text(query: str, pointers: list[Pointer]) -> str:
    lines = [f'engram recall for "{query}" (prior sessions, PRDs, memory, code):']
    lines += [f"- {p.path}:{p.line_start}-{p.line_end}  ({p.heading})" for p in pointers]
    lines.append(FOOTER_TEXT)
    return "\n".join(lines)


def q(path) -> str:
    return shlex.quote(str(path))


def codex_payload(command: str, cwd) -> str:
    return json.dumps({"tool_input": {"command": command}, "cwd": str(cwd)})


class FakeSearch:
    def __init__(self, hits: list[Pointer]) -> None:
        self.hits = hits
        self.error: Exception | None = None
        self.calls: list[tuple[str, str, int]] = []

    def __call__(self, text: str, scope: str, k: int) -> list[Pointer]:
        self.calls.append((text, scope, k))
        if self.error is not None:
            raise self.error
        return list(self.hits)


class UnreadableStdin(io.StringIO):
    def read(self, *args):
        raise OSError("stdin must not be read")

    def readline(self, *args):
        raise OSError("stdin must not be read")

    def readlines(self, *args):
        raise OSError("stdin must not be read")

    def __iter__(self):
        raise OSError("stdin must not be read")


@pytest.fixture
def repos(tmp_path):
    repo = tmp_path / "repo"
    other = tmp_path / "other"
    for root in (repo, other):
        (root / ".git").mkdir(parents=True)
        (root / "src").mkdir()
    nested = repo / "vendor" / "lib"
    nested.mkdir(parents=True)
    (nested / ".git").write_text("gitdir: ../../.git/modules/lib\n")
    return repo, other


@pytest.fixture
def search(monkeypatch):
    fake = FakeSearch(POINTERS)
    monkeypatch.setattr("engram.mcp_server.search_pointers", fake)
    return fake


def run(host: str, payload: str, environ: dict[str, str] | None = None) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    code = nudge.run_nudge(host, io.StringIO(payload), stdout, stderr, environ if environ is not None else {})
    return code, stdout.getvalue(), stderr.getvalue()


def broad(template: str, repos) -> str | None:
    repo, other = repos
    command = template.format(repo=q(repo), other=q(other))
    return nudge.find_broad_search(command, str(repo))


# run_nudge: pinned behaviors


def test_nudges_for_search_outside_repo(repos, search) -> None:
    repo, other = repos
    code, out, err = run("codex", codex_payload(f"rg -l foo {q(other)}", repo))

    assert code == 0
    assert err == ""
    assert search.calls == [("foo", "portfolio", 3)]
    assert out.endswith("\n")
    assert out.count("\n") == 1
    context = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    assert context.split("\n") == [
        'engram recall for "foo" (prior sessions, PRDs, memory, code):',
        "- docs/dev/a.md:1-5  (Intro)",
        "- src/engram/b.py:10-42  (def run)",
        "- notes/plan.md:7-9  (Plan)",
        FOOTER_TEXT,
    ]


def test_passes_recall_query_built_from_pattern(repos, search) -> None:
    repo, other = repos
    payload = codex_payload(f"rg 'EmbeddingServerError|retry' {q(other)}", repo)

    code, out, err = run("plain", payload)

    assert (code, err) == (0, "")
    assert search.calls == [("EmbeddingServerError retry", "portfolio", 3)]
    assert out == expected_text("EmbeddingServerError retry", POINTERS) + "\n"


def test_stays_silent_for_search_inside_repo(repos, search) -> None:
    repo, other = repos
    command = "rg -n -g '*.py' needle src/"

    assert nudge.find_broad_search(command, str(repo)) is None
    assert run("claude", codex_payload(command, repo)) == (0, "", "")
    assert search.calls == []


def test_uses_payload_cwd_to_judge_breadth(repos, search) -> None:
    repo, other = repos
    command = f"rg needle {q(repo / 'src')}"

    assert run("plain", codex_payload(command, repo)) == (0, "", "")
    assert search.calls == []

    code, out, err = run("plain", codex_payload(command, other))
    assert (code, err) == (0, "")
    assert out == expected_text("needle", POINTERS) + "\n"
    assert search.calls == [("needle", "portfolio", 3)]


def test_drops_hits_named_in_pack_file(repos, search, tmp_path) -> None:
    repo, other = repos
    payload = codex_payload(f"rg foo {q(other)}", repo)
    pack = tmp_path / "pack.md"
    # "plan.md" alone is not the full hit path "notes/plan.md", so that hit stays.
    pack.write_text("# Pack\n- docs/dev/a.md:1-5\n- see plan.md\n")

    code, out, err = run("plain", payload, {"ENGRAM_PACK_FILE": str(pack)})
    assert (code, err) == (0, "")
    assert out == expected_text("foo", [POINTERS[1], POINTERS[2]]) + "\n"

    pack.write_text("notes/plan.md src/engram/b.py docs/dev/a.md")
    assert run("plain", payload, {"ENGRAM_PACK_FILE": str(pack)}) == (0, "", "")

    missing = tmp_path / "missing.md"
    code, out, err = run("plain", payload, {"ENGRAM_PACK_FILE": str(missing)})
    assert (code, err) == (0, "")
    assert out == expected_text("foo", POINTERS) + "\n"


def test_stays_silent_when_nudge_is_off(search) -> None:
    stdout, stderr = io.StringIO(), io.StringIO()

    code = nudge.run_nudge("claude", UnreadableStdin(), stdout, stderr, {"ENGRAM_NUDGE": "off"})

    assert code == 0
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == ""
    assert search.calls == []


@pytest.mark.parametrize("flag", ["on", "OFF", "", "0"])
def test_runs_unless_nudge_is_exactly_off(repos, search, flag) -> None:
    repo, other = repos
    code, out, err = run("plain", codex_payload(f"rg foo {q(other)}", repo), {"ENGRAM_NUDGE": flag})

    assert (code, err) == (0, "")
    assert out == expected_text("foo", POINTERS) + "\n"


@pytest.mark.parametrize(
    "error", [EmbeddingServerError("embedding unavailable"), RuntimeError("store locked")]
)
def test_exits_zero_when_query_fails(repos, search, error) -> None:
    repo, other = repos
    search.error = error

    code, out, err = run("claude", codex_payload(f"rg foo {q(other)}", repo))

    assert code == 0
    assert out == ""
    lines = err.splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("engram nudge: query failed:")
    assert search.calls == [("foo", "portfolio", 3)]


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        json.dumps({"tool_input": {"cmd": "rg foo /x"}, "cwd": "/"}),
        json.dumps({"tool_input": {"command": "   "}, "cwd": "/"}),
    ],
)
def test_reports_unreadable_payload_on_stderr(search, raw) -> None:
    code, out, err = run("claude", raw)

    assert code == 0
    assert out == ""
    lines = err.splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("engram nudge: unreadable hook payload:")
    assert search.calls == []


@pytest.mark.parametrize("pattern", ["ab", "'a|bc'", "'x.y(z)'"])
def test_skips_search_when_recall_query_is_empty(repos, search, pattern) -> None:
    repo, other = repos

    assert run("plain", codex_payload(f"rg {pattern} {q(other)}", repo)) == (0, "", "")
    assert search.calls == []


def test_stays_silent_when_search_finds_nothing(repos, search) -> None:
    repo, other = repos
    search.hits = []

    assert run("codex", codex_payload(f"rg foo {q(other)}", repo)) == (0, "", "")
    assert search.calls == [("foo", "portfolio", 3)]


def test_reports_unexpected_error_on_stderr_and_exits_zero(repos, search) -> None:
    repo, other = repos

    code, out, err = run("bogus", codex_payload(f"rg foo {q(other)}", repo))

    assert code == 0
    assert out == ""
    assert len(err.splitlines()) == 1


def test_treats_git_log_pickaxe_as_broad_end_to_end(repos, search) -> None:
    repo, _ = repos
    code, out, err = run("plain", codex_payload("git log -S retry_budget", repo))

    assert (code, err) == (0, "")
    assert out == expected_text("retry_budget", POINTERS) + "\n"


# read_hook_event


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        ({"tool_input": {"command": "rg foo /a"}, "cwd": "/work/one"}, ("rg foo /a", "/work/one")),
        ({"tool_input": {"command": "git log -S x"}, "cwd": "/w/two"}, ("git log -S x", "/w/two")),
        (
            {"tool_input": {"command": "rg a"}, "toolArgs": {"command": "rg b"}, "cwd": "/c"},
            ("rg a", "/c"),
        ),
        ({"tool_input": None, "toolArgs": {"command": "rg b"}, "cwd": "/c"}, ("rg b", "/c")),
    ],
)
def test_reads_command_and_cwd_from_tool_input(event, expected) -> None:
    assert nudge.read_hook_event(json.dumps(event)) == expected


def test_accepts_copilot_tool_args_as_object_and_string(repos, search) -> None:
    repo, other = repos
    as_object = {"toolArgs": {"command": "rg alpha /x"}, "cwd": "/w/a"}
    as_string = {"toolArgs": json.dumps({"command": "grep -r beta /y"}), "cwd": "/w/b"}

    assert nudge.read_hook_event(json.dumps(as_object)) == ("rg alpha /x", "/w/a")
    assert nudge.read_hook_event(json.dumps(as_string)) == ("grep -r beta /y", "/w/b")

    payload = json.dumps({"toolArgs": json.dumps({"command": f"rg foo {q(other)}"}), "cwd": str(repo)})
    code, out, err = run("copilot", payload)
    assert (code, err) == (0, "")
    assert json.loads(out) == {"additionalContext": expected_text("foo", POINTERS)}


@pytest.mark.parametrize("cwd", [None, "", 5])
def test_falls_back_to_process_cwd(tmp_path, monkeypatch, cwd) -> None:
    monkeypatch.chdir(tmp_path)
    event: dict = {"tool_input": {"command": "rg foo"}}
    if cwd is not None:
        event["cwd"] = cwd

    assert nudge.read_hook_event(json.dumps(event)) == ("rg foo", os.getcwd())


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "not json",
        "[]",
        json.dumps({}),
        json.dumps({"cwd": "/a"}),
        json.dumps({"tool_input": "not json"}),
        json.dumps({"tool_input": "[1, 2]"}),
        json.dumps({"tool_input": ["rg foo"]}),
        json.dumps({"tool_input": {}}),
        json.dumps({"tool_input": {"command": ""}}),
        json.dumps({"tool_input": {"command": " \n\t"}}),
        json.dumps({"tool_input": {"command": 5}}),
        json.dumps({"toolArgs": json.dumps({"command": None})}),
    ],
)
def test_rejects_malformed_hook_payload(raw) -> None:
    with pytest.raises(ValueError):
        nudge.read_hook_event(raw)


# find_broad_search: grep family


@pytest.mark.parametrize(
    "template",
    [
        "rg -n -g '*.py' needle {other}",
        "rg --glob '*.md' needle {other}",
        "rg --glob=*.md needle {other}",
        "rg -g*.py needle {other}",
        "rg -g needle.py haystack {other}",
    ],
)
def test_skips_value_of_glob_flag(repos, template) -> None:
    expected = "haystack" if "haystack" in template else "needle"
    assert broad(template, repos) == expected


@pytest.mark.parametrize(
    "flag",
    [
        "-g", "--glob", "-t", "--type", "-T", "--type-not", "-A", "-B", "-C", "-m",
        "--max-count", "--max-depth", "-f", "--file", "-j", "--threads", "-M", "--max-columns",
    ],
)
def test_skips_value_of_each_value_flag(repos, flag) -> None:
    assert broad(f"rg {flag} valx needle {{other}}", repos) == "needle"


@pytest.mark.parametrize(
    ("template", "expected"),
    [
        ("rg needle {other}", "needle"),
        ("rg -i haystack {other}", "haystack"),
        ("rg --ignore-case needle {other}", "needle"),
        ("grep -rn needle {other}", "needle"),
        ("egrep 'a|bcd' {other}", "a|bcd"),
        ("fgrep needle {other}", "needle"),
        ("/usr/bin/grep needle {other}", "needle"),
        ("rg -e foo {other}", "foo"),
        ("rg --regexp bar {other}", "bar"),
        ("rg --regexp=baz {other}", "baz"),
        ("rg -equx {other}", "qux"),
        ("grep -e first -e second {other}", "first"),
        ("rg -e foo {other} src", "foo"),
        ("rg -- -dash {other}", "-dash"),
        ("rg -n -- --flagish {other}", "--flagish"),
        ("rg -e foo src", None),
        ("rg needle", None),
        ("rg -e foo", None),
        ("rgx needle {other}", None),
        ("xgrep needle {other}", None),
        ("grepper needle {other}", None),
        ("ls needle {other}", None),
    ],
)
def test_extracts_pattern_from_grep_family(repos, template, expected) -> None:
    assert broad(template, repos) == expected


# find_broad_search: tokenizing


@pytest.mark.parametrize(
    ("template", "expected"),
    [
        ("rg foo {other} | head -5", "foo"),
        ("rg foo src | rg bar {other}", None),
        ("rg foo src || rg bar {other}", None),
        ("rg foo src && rg bar {other}", None),
        ("rg foo src & rg bar {other}", None),
        ("rg foo src; rg bar {other}", None),
        ("rg foo src > {other}/hits.txt", None),
        ("rg foo src >| {other}/hits.txt", None),
        ("rg foo src &> {other}/hits.txt", None),
        ("rg foo src 2> {other}/err.txt", None),
        ("rg foo src <<< {other}", None),
        ("rg foo {other} 2>/dev/null", "foo"),
        ("rg foo src\nrg bar {other}", None),
        ("rg foo {other}\nls", "foo"),
        ("rg issue#12 {other}", "issue#12"),
        ("rg 'foo {other}", None),
        ('rg "foo {other}', None),
        ("find {other} \\( -name '*.md' \\)", "*.md"),
    ],
)
def test_reads_only_the_first_command(repos, template, expected) -> None:
    assert broad(template, repos) == expected


@pytest.mark.parametrize(
    "command",
    ["", "   ", "rg", "git", "find", "'", "|", "rg -e", "rg -g", "git log -S", "find -name", "\\"],
)
def test_returns_none_for_incomplete_commands(repos, command) -> None:
    repo, _ = repos
    assert nudge.find_broad_search(command, str(repo)) is None


def test_tolerates_overlong_path_token(repos) -> None:
    repo, _ = repos
    assert nudge.find_broad_search("rg foo /" + "a" * 5000, str(repo)) == "foo"


# find_broad_search: find and git


@pytest.mark.parametrize(
    ("template", "expected"),
    [
        ("find {other} -name '*.md'", "*.md"),
        ("find {other} -iname 'README*'", "README*"),
        ("find -L {other} -type f -name plan.md", "plan.md"),
        ("find -H -P {other} -name x.py", "x.py"),
        ("find {other} -name a.md -o -name b.md", "a.md"),
        ("find {other} ! -path '*/.git/*' -name keep.md", "keep.md"),
        ("find src -name '*.py'", None),
        ("find . -name '*.py'", None),
        ("find {other} -type f", None),
        ("find {other} -path '*.md'", None),
        ("find -name '*.md'", None),
    ],
)
def test_extracts_name_pattern_from_find(repos, template, expected) -> None:
    assert broad(template, repos) == expected


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git log -S foo", "foo"),
        ("git log -Sfoo", "foo"),
        ("git log --grep=foo", "foo"),
        ("git log --grep bar", "bar"),
        ("git log -G 'ba+r'", "ba+r"),
        ("git log -Gbaz", "baz"),
        ("git log --oneline -S qux -- src", "qux"),
        ("/usr/bin/git log -S foo", "foo"),
    ],
)
def test_treats_git_log_pickaxe_as_broad(repos, command, expected) -> None:
    repo, _ = repos
    assert nudge.find_broad_search(command, str(repo)) == expected


@pytest.mark.parametrize(
    "command",
    [
        "git log --oneline",
        "git log -s",
        "git show -S foo",
        "git diff -S foo",
        "git logs -S foo",
        "git status && git log -S foo",
        "gitx log -S foo",
    ],
)
def test_ignores_git_without_log_pickaxe(repos, command) -> None:
    repo, _ = repos
    assert nudge.find_broad_search(command, str(repo)) is None


# find_broad_search: breadth


@pytest.mark.parametrize(
    ("template", "expected"),
    [
        ("rg foo src", None),
        ("rg foo {repo}/src", None),
        ("rg foo .", None),
        ("rg foo src {repo}/docs", None),
        ("rg foo vendor", None),
        ("rg foo {other}", "foo"),
        ("rg foo ../other", "foo"),
        ("rg foo src/../../other", "foo"),
        ("rg foo {repo}-old", "foo"),
        ("rg foo vendor/lib/src", "foo"),
        ("rg foo src {other}", "foo"),
        ("rg foo {other} src", "foo"),
        ("rg foo src vendor/lib", "foo"),
        ("rg foo .claude/projects/-Users-x", "foo"),
        ("rg foo {repo}/.claude/projects/abc/s.jsonl", "foo"),
        ("rg foo .claude/projects-old/x", None),
        ("rg foo .claude/rules", None),
        ("rg foo claude/projects/x", None),
    ],
)
def test_judges_breadth_from_repo_cwd(repos, template, expected) -> None:
    assert broad(template, repos) == expected


@pytest.mark.parametrize(
    ("template", "expected"),
    [
        ("rg foo notes", None),
        ("rg foo .", None),
        ("rg foo {scratch}/notes", None),
        ("rg foo ..", "foo"),
        ("rg foo {tmp}/elsewhere", "foo"),
        ("rg foo {scratch}-two", "foo"),
        ("rg foo notes/../../elsewhere", "foo"),
        ("rg foo inner/src", "foo"),
        ("rg foo notes inner", "foo"),
    ],
)
def test_judges_breadth_from_cwd_outside_repo(tmp_path, template, expected) -> None:
    scratch = tmp_path / "scratch"
    (scratch / "notes").mkdir(parents=True)
    (scratch / "inner" / ".git").mkdir(parents=True)
    command = template.format(scratch=q(scratch), tmp=q(tmp_path))

    assert nudge.find_broad_search(command, str(scratch)) == expected


def test_expands_home_and_variables_in_paths(repos, monkeypatch) -> None:
    repo, other = repos
    monkeypatch.setenv("HOME", str(other))
    monkeypatch.setenv("ENGRAM_TEST_TARGET", str(other))
    assert nudge.find_broad_search("rg foo ~/src", str(repo)) == "foo"
    assert nudge.find_broad_search("rg foo $ENGRAM_TEST_TARGET/src", str(repo)) == "foo"

    monkeypatch.setenv("HOME", str(repo))
    monkeypatch.setenv("ENGRAM_TEST_TARGET", str(repo))
    assert nudge.find_broad_search("rg foo ~/src", str(repo)) is None
    assert nudge.find_broad_search("rg foo $ENGRAM_TEST_TARGET/src", str(repo)) is None


# build_recall_query


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ("foo.bar(x)", "foo bar"),
        ("ab|cd", ""),
        ("", ""),
        ("abc", "abc"),
        ("EmbeddingServerError|retry", "EmbeddingServerError retry"),
        ("my_func-name", "my_func-name"),
        ("issue#12", "issue"),
        ("  spaced   out  ", "spaced out"),
        ("\\bfoo\\s+bar\\b", "bfoo bar"),
    ],
)
def test_builds_recall_query_from_long_words(pattern, expected) -> None:
    assert nudge.build_recall_query(pattern) == expected


# format_nudge

TWO_HIT_TEXT = (
    'engram recall for "foo bar" (prior sessions, PRDs, memory, code):\n'
    "- docs/dev/a.md:1-5  (Intro)\n"
    "- src/engram/b.py:10-42  (def run)\n"
    "Read a cited range if it is relevant; ignore it if not."
)


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        (
            "claude",
            json.dumps(
                {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": TWO_HIT_TEXT}}
            ),
        ),
        (
            "codex",
            json.dumps(
                {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": TWO_HIT_TEXT}}
            ),
        ),
        ("copilot", json.dumps({"additionalContext": TWO_HIT_TEXT})),
        ("plain", TWO_HIT_TEXT),
    ],
)
def test_emits_each_host_format(host, expected) -> None:
    assert nudge.format_nudge(host, "foo bar", POINTERS[:2]) == expected


def test_formats_other_query_and_empty_pointer_list() -> None:
    assert nudge.format_nudge("plain", "retry", [POINTERS[2]]) == (
        'engram recall for "retry" (prior sessions, PRDs, memory, code):\n'
        "- notes/plan.md:7-9  (Plan)\n"
        "Read a cited range if it is relevant; ignore it if not."
    )
    assert nudge.format_nudge("plain", "retry", []) == (
        'engram recall for "retry" (prior sessions, PRDs, memory, code):\n'
        "\n"
        "Read a cited range if it is relevant; ignore it if not."
    )


@pytest.mark.parametrize("host", ["bogus", "", "Claude", "claude-code"])
def test_rejects_unknown_host(host) -> None:
    assert nudge.HOSTS == ("claude", "codex", "copilot", "plain")
    with pytest.raises(ValueError):
        nudge.format_nudge(host, "foo", POINTERS)
