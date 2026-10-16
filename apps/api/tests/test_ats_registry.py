"""ATS registry: candidate parsing, slugs, India detection, probing and loading.

No network: probes run against httpx.MockTransport and the fixture payloads in
tests/fixtures/ats/, which mirror the real board API shapes.
"""

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.jobs import models as job_models
from app.jobs.ats_registry import (
    Candidate,
    HostRateLimiter,
    ResponseCache,
    extract_openings,
    is_india_location,
    load_registry,
    merge_entries,
    name_from_slug,
    name_matches,
    parse_boards,
    parse_candidates,
    probe_board,
    probe_candidate,
    slug_variants,
    summarize_board,
)

FIXTURES = Path(__file__).parent / "fixtures" / "ats"
NOW = "2026-10-16T12:00:00+00:00"


def _fixture(ats: str):
    return json.loads((FIXTURES / f"{ats}.json").read_text(encoding="utf-8"))


# --- candidates and slugs ----------------------------------------------------


def test_candidates_skip_comments_and_duplicates_and_keep_extra_slugs():
    text = "# header\n\nRazorpay\nCRED|dreamplug, cred-club\n  razorpay  \nOla|olacabs,ola-electric\n"
    assert parse_candidates(text) == [
        Candidate("Razorpay"),
        Candidate("CRED", ("dreamplug", "cred-club")),
        Candidate("Ola", ("olacabs", "ola-electric")),
    ]


def test_the_real_candidates_file_parses():
    path = Path(__file__).resolve().parents[3] / "data" / "ats-registry" / "candidates.txt"
    candidates = parse_candidates(path.read_text(encoding="utf-8"))
    assert len(candidates) > 600
    assert all(c.name and "|" not in c.name for c in candidates)


@pytest.mark.parametrize(
    "name, extras, expected_first",
    [
        ("Razorpay", (), ["razorpay"]),
        ("Physics Wallah", (), ["physicswallah", "physics-wallah"]),
        ("Druva Inc", (), ["druvainc", "druva-inc", "druva"]),
        ("Sarvam AI", ("sarvam",), ["sarvam", "sarvamai", "sarvam-ai"]),
        ("Tata 1mg", (), ["tata1mg", "tata-1mg"]),
        ("M&T Labs", (), ["mandtlabs", "m-and-t-labs", "mandt", "m-and-t"]),
    ],
)
def test_slug_variants_put_the_likeliest_first(name, extras, expected_first):
    slugs = slug_variants(name, extras)
    assert slugs[: len(expected_first)] == expected_first
    assert len(slugs) == len(set(slugs)) <= 5


@pytest.mark.parametrize(
    "location, india",
    [
        ("Bengaluru, Karnataka, India", True),
        ("Bangalore", True),
        ("Remote - India", True),
        ("Gurgaon", True),
        ("New Delhi", True),
        ("Navi Mumbai (Hybrid)", True),
        ("Indianapolis, Indiana", False),
        ("Remote (US)", False),
        ("Pune Street, Singapore", True),  # place names win; the review step catches oddities
        ("", False),
        (None, False),
    ],
)
def test_india_locations_are_whole_word_matches(location, india):
    assert is_india_location(location) is india


@pytest.mark.parametrize(
    "candidate, board, expected",
    [
        ("Rubrik", "Rubrik", True),
        ("Postman", "Postman Inc.", True),
        ("Ola", "Ola Electric", True),
        ("Sarvam AI", "Sarvam", True),
        ("Swiggy", "Acme Robotics", False),
        ("Zepto", None, None),
    ],
)
def test_board_company_name_check(candidate, board, expected):
    assert name_matches(candidate, board) is expected


# --- reading board payloads ----------------------------------------------------


def test_greenhouse_openings_and_summary():
    payload = _fixture("greenhouse")
    openings = extract_openings("greenhouse", payload)
    assert [o.india for o in openings] == [True, False, False, True]
    entry = summarize_board(Candidate("Rubrik"), "greenhouse", "rubrik", payload, NOW)
    assert (entry.india_openings, entry.total_openings, entry.remote_openings) == (2, 4, 1)
    assert entry.sample_locations == ["Bengaluru, India", "Remote - India"]
    assert entry.board_company_name == "Rubrik" and entry.name_verified is True
    assert entry.sample_job_url == "https://boards.greenhouse.io/rubrik/jobs/101"


def test_lever_uses_country_code_and_all_locations():
    openings = extract_openings("lever", _fixture("lever"))
    assert [o.india for o in openings] == [True, False, True]
    assert openings[1].remote is True
    assert openings[2].locations == ["hyderabad", "pune"]


def test_ashby_uses_secondary_locations_and_skips_unlisted_jobs():
    openings = extract_openings("ashby", _fixture("ashby"))
    assert [o.title for o in openings] == ["ML Engineer", "Research Scientist", "Designer"]
    assert [o.india for o in openings] == [True, True, False]
    entry = summarize_board(Candidate("Sarvam AI"), "ashby", "sarvam", _fixture("ashby"), NOW)
    assert entry.name_verified is None  # Ashby doesn't report a company name


# --- probing --------------------------------------------------------------------


def _transport(routes: dict[str, httpx.Response], calls: list[str]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        for needle, response in routes.items():
            if needle in str(request.url):
                return response
        return httpx.Response(404, json={"status": 404})

    return httpx.MockTransport(handler)


def _probe(candidate, routes, cache_dir=None):
    calls: list[str] = []

    async def go():
        async with httpx.AsyncClient(transport=_transport(routes, calls)) as client:
            return await probe_candidate(
                client, candidate, limiter=HostRateLimiter(0), cache=ResponseCache(cache_dir), now=NOW
            )

    return asyncio.run(go()), calls


def test_probe_finds_a_board_on_the_second_ats_and_stops():
    result, calls = _probe(
        Candidate("CRED", ("dreamplug",)),
        {"api.lever.co/v0/postings/cred?": httpx.Response(200, json=_fixture("lever"))},
    )
    assert result.entry is not None
    assert (result.entry.ats, result.entry.board_token, result.entry.india_openings) == ("lever", "cred", 2)
    assert not any("ashbyhq" in url for url in calls)  # stopped once India openings were found


def test_probe_skips_a_greenhouse_board_owned_by_another_company():
    other = {"jobs": [{"title": "x", "company_name": "Acme Robotics", "location": {"name": "Bengaluru"}}]}
    result, _ = _probe(
        Candidate("Swiggy"),
        {
            "boards/swiggy/jobs": httpx.Response(200, json=other),
            "job-board/swiggy": httpx.Response(200, json=_fixture("ashby")),
        },
    )
    assert result.entry.ats == "ashby"


def test_probe_records_boards_without_india_openings():
    us_only = {"jobs": [{"title": "x", "company_name": "Linear", "location": {"name": "San Francisco"}}]}
    result, _ = _probe(Candidate("Linear"), {"boards/linear/jobs": httpx.Response(200, json=us_only)})
    assert result.entry is None
    assert [(b.ats, b.total_openings) for b in result.boards_without_india] == [("greenhouse", 1)]


def test_probe_retries_rate_limits_then_succeeds():
    attempts = {"n": 0}
    calls: list[str] = []

    def handler(request):
        calls.append(str(request.url))
        if "boards/rubrik/jobs" in str(request.url):
            attempts["n"] += 1
            if attempts["n"] == 1:
                return httpx.Response(429, headers={"retry-after": "0"})
            return httpx.Response(200, json=_fixture("greenhouse"))
        return httpx.Response(404)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await probe_candidate(
                client, Candidate("Rubrik"), limiter=HostRateLimiter(0), cache=ResponseCache(None), now=NOW
            )

    result = asyncio.run(go())
    assert attempts["n"] == 2
    assert result.entry.india_openings == 2 and result.errors == 0


def test_cached_responses_make_a_rerun_free(tmp_path):
    routes = {"api.lever.co/v0/postings/cred?": httpx.Response(200, json=_fixture("lever"))}
    first, calls_first = _probe(Candidate("CRED"), routes, cache_dir=tmp_path)
    second, calls_second = _probe(Candidate("CRED"), routes, cache_dir=tmp_path)
    assert calls_first and not calls_second
    assert first.entry == second.entry


# --- loading ----------------------------------------------------------------------


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _entry(name, ats, token):
    return {"name": name, "ats": ats, "board_token": token, "probed_at": NOW, "domain": None}


def test_loader_creates_updates_and_is_idempotent(db):
    db.add(job_models.Company(name="Rubrik", domain="rubrik.com"))
    db.commit()

    entries = [_entry("rubrik", "greenhouse", "rubrik"), _entry("CRED", "lever", "cred")]
    assert load_registry(db, entries) == {"created": 1, "updated": 1}
    assert load_registry(db, entries) == {"created": 0, "updated": 2}

    companies = {c.name: c for c in db.query(job_models.Company).all()}
    assert set(companies) == {"Rubrik", "CRED"}
    assert (companies["Rubrik"].ats_vendor, companies["Rubrik"].ats_board_token) == ("greenhouse", "rubrik")
    assert companies["Rubrik"].domain == "rubrik.com"
    assert companies["CRED"].ats_checked_at is not None


# --- discovered boards ------------------------------------------------------------


def test_discovered_boards_parse_and_dedupe():
    text = "# header\ngreenhouse:Rubrik\nlever:cred\ngreenhouse:rubrik\nworkday:acme\nnot-a-line\n"
    assert parse_boards(text) == [("greenhouse", "rubrik"), ("lever", "cred")]


def test_names_from_slugs():
    assert name_from_slug("hevodata") == "Hevodata"
    assert name_from_slug("acme-robotics") == "Acme Robotics"


def _probe_board(ats, slug, routes):
    async def go():
        async with httpx.AsyncClient(transport=_transport(routes, [])) as client:
            return await probe_board(client, ats, slug, limiter=HostRateLimiter(0), cache=ResponseCache(None), now=NOW)

    return asyncio.run(go())


def test_a_discovered_greenhouse_board_takes_its_name_from_the_board():
    result = _probe_board("greenhouse", "rubrikinc", {"boards/rubrikinc/jobs": httpx.Response(200, json=_fixture("greenhouse"))})
    assert (result.entry.name, result.entry.source, result.entry.name_verified) == ("Rubrik", "crawl", None)
    assert result.entry.india_openings == 2


def test_a_discovered_board_without_india_or_gone_is_not_a_hit():
    us_only = {"jobs": [{"title": "x", "company_name": "Linear", "location": {"name": "Paris"}}]}
    kept = _probe_board("greenhouse", "linear", {"boards/linear/jobs": httpx.Response(200, json=us_only)})
    gone = _probe_board("ashby", "closedco", {})
    assert kept.entry is None and len(kept.boards_without_india) == 1
    assert gone.entry is None and not gone.boards_without_india and gone.errors == 0


def test_name_guesses_win_when_both_sources_find_the_same_board():
    by_name = summarize_board(Candidate("CRED"), "lever", "cred", _fixture("lever"), NOW)
    by_crawl = summarize_board(Candidate("Cred"), "lever", "cred", _fixture("lever"), NOW)
    by_crawl.source = "crawl"
    other = summarize_board(Candidate("Sarvam"), "ashby", "sarvam", _fixture("ashby"), NOW)
    merged = merge_entries([by_name], [by_crawl, other])
    assert [(e.name, e.source) for e in merged] == [("CRED", "candidates"), ("Sarvam", "candidates")]


def test_invisible_characters_are_stripped_from_board_names():
    payload = {"jobs": [{"title": "x", "company_name": "‎Acme​ Robotics﻿ ", "location": {"name": "Pune"}}]}
    entry = summarize_board(Candidate("Acme Robotics"), "greenhouse", "acme", payload, NOW)
    assert entry.board_company_name == "Acme Robotics" and entry.name_verified is True
