import shlex

import pytest

from engram import nudge


def q(path) -> str:
    return shlex.quote(str(path))


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


def broad(template: str, repos) -> str | None:
    repo, other = repos
    command = template.format(repo=q(repo), other=q(other))
    return nudge.find_broad_search(command, str(repo))


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
        "-g",
        "--glob",
        "-t",
        "--type",
        "-T",
        "--type-not",
        "-A",
        "-B",
        "-C",
        "-m",
        "--max-count",
        "--max-depth",
        "-f",
        "--file",
        "-j",
        "--threads",
        "-M",
        "--max-columns",
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
    [
        "",
        "   ",
        "rg",
        "git",
        "find",
        "'",
        "|",
        "rg -e",
        "rg -g",
        "git log -S",
        "find -name",
        "\\",
    ],
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
        ("find src {other} -name x.md", "x.md"),
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
        ("rg foo vendor/lib/src/deep/x", "foo"),
        ("rg foo src {other}", "foo"),
        ("rg foo {other} src", "foo"),
        ("rg foo src vendor/lib", "foo"),
        ("rg foo .claude/projects", "foo"),
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


def test_judges_breadth_from_repo_subdirectory_cwd(repos) -> None:
    repo, _ = repos
    (repo / "docs").mkdir()
    cwd = str(repo / "src")

    assert nudge.find_broad_search("rg foo ../docs", cwd) is None
    assert nudge.find_broad_search("rg foo ..", cwd) is None
    assert nudge.find_broad_search("rg foo ../../other", cwd) == "foo"


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
