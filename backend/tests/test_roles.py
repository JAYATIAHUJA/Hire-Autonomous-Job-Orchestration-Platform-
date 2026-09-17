from app.analysis.roles import project_role


def contributors(**counts):
    return [{"login": login, "contributions": n} for login, n in counts.items()]


def test_owner_with_most_commits_is_primary_author():
    assert project_role("ana", "ana", 80, contributors(ana=80, bob=10)) == ("Primary author", 0.889)


def test_share_thresholds_for_non_owner():
    assert project_role("ana", "org", 60, contributors(ana=60, bob=40))[0] == "Lead contributor"
    assert project_role("ana", "org", 20, contributors(ana=20, bob=80))[0] == "Core contributor"
    assert project_role("ana", "org", 5, contributors(ana=5, bob=95))[0] == "Contributor"


def test_owner_with_small_share_is_not_primary_author():
    assert project_role("ana", "ana", 10, contributors(ana=10, bob=90))[0] == "Contributor"


def test_missing_contributor_stats_falls_back_to_authored_commits():
    assert project_role("ana", "ana", 7, []) == ("Primary author", 1.0)
    assert project_role("ana", "ana", 0, []) == ("Contributor", None)
