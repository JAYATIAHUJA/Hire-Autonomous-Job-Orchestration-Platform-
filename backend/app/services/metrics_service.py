from collections import Counter


def compute_aggregate_metrics(repo_data: list[dict]) -> dict:
    months = Counter(date[:7] for r in repo_data for date in r["commit_dates"])
    return {
        "total_repos": len(repo_data),
        "total_commits": sum(r["commit_count"] for r in repo_data),
        "total_additions": sum(r["additions"] for r in repo_data),
        "total_deletions": sum(r["deletions"] for r in repo_data),
        "total_prs": sum(r["pr_count"] for r in repo_data),
        "languages": sorted({lang for r in repo_data for lang in r["languages"]}),
        "timeline": [{"month": m, "commits": c} for m, c in sorted(months.items())],
    }
