import pytest

from engram.corpora import read_repos_csv


# --- parses gita's repos.csv row format: repo_path, name, ...trailing empties ---


def test_parses_repo_path_and_name_columns_in_file_order(tmp_path):
    repos_csv = tmp_path / "repos.csv"
    repos_csv.write_text(
        "/repos/alpha,alpha,,\n"
        "/repos/beta,beta,,\n"
    )

    result = read_repos_csv(repos_csv)

    assert result == [("/repos/alpha", "alpha"), ("/repos/beta", "beta")]


# --- rows with fewer than 2 fields (blank lines, single-column rows) are skipped ---


def test_rows_with_fewer_than_two_fields_are_skipped_without_raising(tmp_path):
    repos_csv = tmp_path / "repos.csv"
    repos_csv.write_text(
        "\n"
        "/repos/alpha,alpha,,\n"
        "just-one-field\n"
        "\n"
    )

    result = read_repos_csv(repos_csv)

    assert result == [("/repos/alpha", "alpha")]


def test_empty_csv_file_returns_empty_list(tmp_path):
    repos_csv = tmp_path / "repos.csv"
    repos_csv.write_text("")

    assert read_repos_csv(repos_csv) == []


# --- missing repos.csv fails loud with the gita registration hint ---


def test_missing_csv_raises_filenotfounderror_with_gita_registration_message(tmp_path):
    repos_csv = tmp_path / "does-not-exist.csv"

    with pytest.raises(FileNotFoundError, match="not found; register repos with gita first"):
        read_repos_csv(repos_csv)
