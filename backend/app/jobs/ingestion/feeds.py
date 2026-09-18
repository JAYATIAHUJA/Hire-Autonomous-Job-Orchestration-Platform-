"""Public job feed ingestor and regional Indian tech hiring fixtures.

Provides ingestion adapters for public career feeds alongside realistic
off-campus job fixtures tailored to Tier-3 engineering graduates navigating
the Indian tech placement ecosystem (Bengaluru, Hyderabad, Pune, NCR, Remote).
"""

from datetime import datetime, timezone, timedelta
from typing import Any, Optional
import httpx


INDIAN_TECH_FIXTURES: list[dict[str, Any]] = [
    {
        "source_id": "blr_swig_001",
        "company_name": "Swiggy Engineering",
        "company_domain": "swiggy.com",
        "external_layoff_flag": False,
        "title": "Backend Software Engineer (Order Routing)",
        "location": "Bengaluru, KA (Hybrid)",
        "salary_range": "₹1,200,000 - ₹1,800,000 INR",
        "posting_age_days": 8,
        "repost_count": 0,
        "experience_level": "Fresher / Entry-Level (0-2 yrs)",
        "primary_skills": ["Python", "FastAPI", "PostgreSQL", "Redis", "Kafka", "Docker"],
        "raw_description": (
            "Swiggy is hiring a Backend Software Engineer for our core Logistics & Routing team in Bengaluru. "
            "You will build high-throughput microservices handling 25,000+ RPS during peak hunger hours. "
            "Responsibilities: Design RESTful and gRPC APIs using Python (FastAPI/Go), optimize SQL queries "
            "in PostgreSQL, implement distributed caching with Redis, and integrate event streams using Apache Kafka. "
            "Requirements: Strong computer science fundamentals, hands-on experience with Python or Go, "
            "understanding of relational databases, and Docker containerization. "
            "Compensation: ₹12 LPA to ₹18 LPA CTC plus ESOPs."
        ),
    },
    {
        "source_id": "hyd_zepto_002",
        "company_name": "Zepto",
        "company_domain": "zeptonow.com",
        "external_layoff_flag": False,
        "title": "Junior Full Stack Engineer",
        "location": "Hyderabad, TS (In-Office)",
        "salary_range": "₹900,000 - ₹1,400,000 INR",
        "posting_age_days": 14,
        "repost_count": 0,
        "experience_level": "Entry-Level / Fresher",
        "primary_skills": ["React", "TypeScript", "Node.js", "MongoDB", "Tailwind CSS"],
        "raw_description": (
            "Join Zepto's Dark Store Operations engineering squad in HITEC City, Hyderabad. "
            "We are looking for an energetic Junior Full Stack Developer to build internal tools and warehouse apps. "
            "Tech Stack: TypeScript, React 18, Node.js/Express, and MongoDB. "
            "Key Tasks: Develop interactive warehouse picking dashboards, optimize barcode scanner event listeners, "
            "and write automated unit tests using Jest. "
            "Qualifications: Bachelor's degree in CS/IT (2024-2026 batch welcome), demonstrable GitHub projects, "
            "knowledge of asynchronous JavaScript and CSS layout models."
        ),
    },
    {
        "source_id": "pune_cred_003",
        "company_name": "CRED",
        "company_domain": "cred.club",
        "external_layoff_flag": False,
        "title": "Mobile App Developer (Android/React Native)",
        "location": "Bengaluru, KA (Hybrid)",
        "salary_range": "₹1,500,000 - ₹2,200,000 INR",
        "posting_age_days": 5,
        "repost_count": 0,
        "experience_level": "Entry-Level (1-2 yrs)",
        "primary_skills": ["Kotlin", "React Native", "TypeScript", "Jetpack Compose"],
        "raw_description": (
            "CRED is seeking product-focused engineers who obsess over micro-interactions and 60 FPS fluid UI. "
            "Role: Build next-generation financial management flows on Android using Kotlin and React Native. "
            "You will write modular components, maintain offline storage SQLite synchronization, and integrate biometrics. "
            "Requirements: Proven ability in Kotlin/Android or React Native, deep appreciation for design systems, "
            "and experience profiling mobile memory leaks. CTC: ₹15-22 Lakhs INR."
        ),
    },
    {
        "source_id": "ncr_inno_004",
        "company_name": "InnoSoft Digital",
        "company_domain": "innosoft-sample.in",
        "external_layoff_flag": False,
        "title": "Software Development Engineer - I",
        "location": "Noida / Gurugram, NCR",
        "salary_range": None,  # Missing salary transparency
        "posting_age_days": 38,
        "repost_count": 1,
        "experience_level": "Entry-Level",
        "primary_skills": ["Java", "Spring Boot", "MySQL"],
        "raw_description": (
            "InnoSoft is looking for an SDE 1 for enterprise consulting projects in Gurgaon. "
            "Candidate will work on backend Java Spring Boot web applications and database integrations. "
            "Requirements: Basic knowledge of OOP concepts, Core Java, Spring framework, and SQL queries. "
            "Candidates should have good communication skills and aptitude for learning. Salary as per industry standards."
        ),
    },
    {
        "source_id": "ghost_corp_005",
        "company_name": "Apex Global Edtech Solutions",
        "company_domain": "apex-edtech-layoff.com",
        "external_layoff_flag": True,  # Undergoing mass layoffs / freeze
        "title": "Rockstar Full Stack Developer (Urgent)",
        "location": "Remote (India)",
        "salary_range": None,  # No compensation
        "posting_age_days": 82,  # Over 60 days
        "repost_count": 4,  # Reposted 4 times without updates
        "experience_level": "Any",
        "primary_skills": ["Full Stack", "Problem Solving"],
        "raw_description": (
            "We are seeking a high-energy rockstar ninja developer who can wear multiple hats in a dynamic, "
            "fast-paced, high-octane startup environment! You will handle various ad-hoc engineering tasks, "
            "interface with diverse cross-functional stakeholders, drive continuous synergies, and take ownership of "
            "everything end-to-end. Must be a self-starter with a passion for excellence and willingness to hustle. "
            "Competitive compensation for the right candidate."
        ),
    },
    {
        "source_id": "ghost_harvest_006",
        "company_name": "TalentPool Staffing Network",
        "company_domain": "talentpool-harvest.io",
        "external_layoff_flag": False,
        "title": "Graduate Trainee Engineer - Continuous Pipeline",
        "location": "Multiple Locations, India",
        "salary_range": None,
        "posting_age_days": 110,  # 110 days old!
        "repost_count": 7,  # Periodic talent harvesting
        "experience_level": "Fresher",
        "primary_skills": ["General Engineering", "C++", "Java"],
        "raw_description": (
            "Continuous recruitment pipeline for upcoming enterprise client requirements. "
            "Submit your CV to be considered for ongoing and future placement drives. "
            "Selected candidates will undergo training and deployment based on client project approvals. "
            "Candidate should possess positive attitude, good communication, and basic engineering graduation."
        ),
    },
]


async def fetch_public_feed_jobs(limit: int = 20) -> list[dict[str, Any]]:
    """Fetch job postings from live public feeds with automatic fallback to regional fixtures."""
    jobs: list[dict[str, Any]] = list(INDIAN_TECH_FIXTURES)

    # Attempt fetching additional listings from RemoteOK public API
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.get("https://remoteok.com/api", headers={"User-Agent": "Hire-Unplug/1.0"})
            if resp.status_code == 200:
                data = resp.json()
                # First element is legal disclaimer
                for item in data[1:]:
                    if isinstance(item, dict) and item.get("position"):
                        jobs.append({
                            "source_id": f"remoteok_{item.get('id', '')}",
                            "company_name": item.get("company", "Remote Co"),
                            # A shared placeholder domain would make unrelated employers
                            # look identical to the recruiter-reply matcher, so leave it unset.
                            "company_domain": (item["company_slug"] + ".com") if item.get("company_slug") else None,
                            "external_layoff_flag": False,
                            "title": item.get("position", "Software Engineer"),
                            "location": item.get("location") or "Remote",
                            "salary_range": (
                                f"${item['salary_min']:,} - ${item['salary_max']:,} USD"
                                if item.get("salary_min") and item.get("salary_max")
                                else None
                            ),
                            "posting_age_days": 10,
                            "repost_count": 0,
                            "experience_level": "Entry-Level / Mid",
                            "primary_skills": item.get("tags", [])[:5],
                            "raw_description": item.get("description", item.get("position", "")),
                        })
                        if len(jobs) >= limit:
                            break
    except Exception:
        # Gracefully handle network outage/offline test environments
        pass

    return jobs[:limit]
