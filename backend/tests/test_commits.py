import pytest

from app.analysis.commits import classify_commit, is_bulk


@pytest.mark.parametrize(
    "message, categories, adds, dels, expected",
    [
        ("feat(auth): add JWT refresh", ["source"], 120, 4, "feature"),
        ("fix: handle empty cart", ["source"], 5, 2, "fix"),
        ("refactor!: split payment module", ["source"], 80, 90, "refactor"),
        ("docs: explain setup", ["docs"], 30, 0, "docs"),
        ("Update README", ["docs"], 3, 1, "docs"),
        ("Add tests for parser", ["test"], 60, 0, "test"),
        ("Update workflow", ["ci"], 10, 2, "ci/infra"),
        ("Bump deps", ["manifest"], 4, 4, "chore"),
        ("Fixed crash when list is empty", ["source", "test"], 12, 3, "fix"),
        ("Rename helpers and clean up", ["source"], 40, 42, "refactor"),
        ("Implement search page", ["source"], 200, 10, "feature"),
        ("wip", ["source"], 10, 50, "refactor"),
        ("wip", ["source"], 50, 10, "feature"),
        ("twk", ["source"], 92, 91, "refactor"),
    ],
)
def test_classify_commit(message, categories, adds, dels, expected):
    assert classify_commit(message, categories, adds, dels) == expected


def test_bulk_detection():
    assert is_bulk(files_touched=150, meaningful_lines=900)
    assert is_bulk(files_touched=3, meaningful_lines=12_000)
    assert not is_bulk(files_touched=12, meaningful_lines=800)
