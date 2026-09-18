"""Adaptive job extraction and self-healing scraper using Scrapling and DOM fingerprinting.

Stores multidimensional fingerprints (attributes, tag density, DOM depth, text features)
in a local SQLite database (dom_fingerprints.db). When site updates cause 'selector rot',
the auto_match engine computes mathematical similarity against stored fingerprints to
recover the target nodes without manual selector fixes.
"""

import json
import math
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Any, Optional

from bs4 import BeautifulSoup


@dataclass
class DOMFingerprint:
    tag: str
    depth: int
    tag_density: float
    attributes: dict[str, Any]
    text_pattern: str
    sample_text_length: int

    def to_json(self) -> str:
        return json.dumps({
            "tag": self.tag,
            "depth": self.depth,
            "tag_density": round(self.tag_density, 3),
            "attributes": self.attributes,
            "text_pattern": self.text_pattern,
            "sample_text_length": self.sample_text_length,
        })

    @classmethod
    def from_json(cls, data: str) -> "DOMFingerprint":
        d = json.loads(data)
        return cls(
            tag=d.get("tag", ""),
            depth=d.get("depth", 0),
            tag_density=d.get("tag_density", 0.0),
            attributes=d.get("attributes", {}),
            text_pattern=d.get("text_pattern", ""),
            sample_text_length=d.get("sample_text_length", 0),
        )


class FingerprintDatabase:
    """Manages persistent multidimensional node fingerprints in SQLite."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            db_path = os.path.join(backend_dir, "dom_fingerprints.db")
        self.db_path = db_path
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS node_fingerprints (
                    source TEXT NOT NULL,
                    target_field TEXT NOT NULL,
                    last_known_selector TEXT NOT NULL,
                    fingerprint_json TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (source, target_field)
                )
            """)
            conn.commit()

    def save_fingerprint(self, source: str, target_field: str, selector: str, fp: DOMFingerprint) -> None:
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO node_fingerprints (source, target_field, last_known_selector, fingerprint_json, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(source, target_field) DO UPDATE SET
                    last_known_selector = excluded.last_known_selector,
                    fingerprint_json = excluded.fingerprint_json,
                    updated_at = CURRENT_TIMESTAMP
            """, (source, target_field, selector, fp.to_json()))
            conn.commit()

    def get_fingerprint(self, source: str, target_field: str) -> Optional[tuple[str, DOMFingerprint]]:
        with self._get_conn() as conn:
            row = conn.execute("""
                SELECT last_known_selector, fingerprint_json
                FROM node_fingerprints
                WHERE source = ? AND target_field = ?
            """, (source, target_field)).fetchone()
            if row:
                return row["last_known_selector"], DOMFingerprint.from_json(row["fingerprint_json"])
        return None


class AdaptiveScraper:
    """Adaptive parser with self-healing DOM relocation."""

    def __init__(self, fp_db: Optional[FingerprintDatabase] = None):
        self.db = fp_db or FingerprintDatabase()

    @staticmethod
    def _compute_depth(element) -> int:
        depth = 0
        cur = element.parent
        while cur is not None and cur.name != "[document]":
            depth += 1
            cur = cur.parent
        return depth

    @staticmethod
    def _compute_tag_density(element) -> float:
        text_len = len(element.get_text(strip=True))
        children_count = len(element.find_all(True))
        if text_len == 0:
            return 0.0
        return min(children_count / max(text_len / 50.0, 1.0), 10.0)

    @classmethod
    def create_fingerprint(cls, element) -> DOMFingerprint:
        attrs = {
            k: v if isinstance(v, (str, int, float)) else " ".join(v)
            for k, v in element.attrs.items()
            if k in {"class", "id", "role", "data-testid", "data-qa", "itemprop"}
        }
        text = element.get_text(strip=True)
        # Extract general alphanumeric structural pattern
        pattern = re.sub(r"\d+", "<NUM>", text[:60])
        return DOMFingerprint(
            tag=element.name,
            depth=cls._compute_depth(element),
            tag_density=cls._compute_tag_density(element),
            attributes=attrs,
            text_pattern=pattern,
            sample_text_length=len(text),
        )

    @staticmethod
    def calculate_similarity(candidate_fp: DOMFingerprint, stored_fp: DOMFingerprint) -> float:
        """Calculate mathematical similarity confidence [0.0 - 1.0] across multiple dimensions."""
        score = 0.0
        # 1. Tag match (30% weight)
        if candidate_fp.tag == stored_fp.tag:
            score += 0.30
        elif candidate_fp.tag in {"div", "section", "article", "p", "span"} and stored_fp.tag in {"div", "section", "article", "p", "span"}:
            score += 0.15

        # 2. Depth similarity (15% weight)
        depth_diff = abs(candidate_fp.depth - stored_fp.depth)
        score += 0.15 * math.exp(-depth_diff / 3.0)

        # 3. Attributes overlap (25% weight)
        cand_classes = set(str(candidate_fp.attributes.get("class", "")).split())
        stored_classes = set(str(stored_fp.attributes.get("class", "")).split())
        if cand_classes and stored_classes:
            jaccard = len(cand_classes & stored_classes) / len(cand_classes | stored_classes)
            score += 0.25 * jaccard
        elif candidate_fp.attributes.get("data-testid") == stored_fp.attributes.get("data-testid") and stored_fp.attributes.get("data-testid"):
            score += 0.25
        elif not stored_classes:
            score += 0.10

        # 4. Text length & structure similarity (30% weight)
        target_len = stored_fp.sample_text_length
        cand_len = candidate_fp.sample_text_length
        if target_len > 0 and cand_len > 0:
            len_ratio = min(cand_len, target_len) / max(cand_len, target_len)
            score += 0.20 * len_ratio
        elif target_len == 0 and cand_len == 0:
            score += 0.20

        # Tag density similarity (10% bonus / normalization)
        density_diff = abs(candidate_fp.tag_density - stored_fp.tag_density)
        score += 0.10 * math.exp(-density_diff / 2.0)

        return min(score, 1.0)

    def extract_with_self_healing(
        self,
        html_content: str,
        source: str,
        target_field: str,
        fallback_selector: str,
    ) -> tuple[Optional[str], float, bool]:
        """Extracts text for target field.
        
        Returns:
            (extracted_text, confidence, was_healed)
        """
        soup = BeautifulSoup(html_content, "html.parser")
        stored = self.db.get_fingerprint(source, target_field)

        selector_to_try = stored[0] if stored else fallback_selector

        # 1. Try standard CSS selector
        try:
            elem = soup.select_one(selector_to_try)
        except Exception:
            elem = None

        if elem and elem.get_text(strip=True):
            # Selector works! Refresh fingerprint
            fp = self.create_fingerprint(elem)
            self.db.save_fingerprint(source, target_field, selector_to_try, fp)
            return elem.get_text(strip=True), 1.0, False

        # 2. Selector broke (Selector Rot) -> Run Auto-Match Self-Healing
        if not stored:
            return None, 0.0, False

        stored_selector, stored_fp = stored
        best_elem = None
        best_score = 0.0

        # Search candidates matching same or generic tag
        candidates = soup.find_all(stored_fp.tag) or soup.find_all(["div", "section", "article", "p", "span", "h1", "h2", "h3"])
        for candidate in candidates:
            cand_fp = self.create_fingerprint(candidate)
            score = self.calculate_similarity(cand_fp, stored_fp)
            if score > best_score:
                best_score = score
                best_elem = candidate

        if best_elem and best_score >= 0.70:
            # Self-healing succeeded! Re-generate a simple selector and update DB
            new_selector = self._generate_selector(best_elem)
            new_fp = self.create_fingerprint(best_elem)
            self.db.save_fingerprint(source, target_field, new_selector, new_fp)
            return best_elem.get_text(strip=True), round(best_score, 3), True

        return None, round(best_score, 3), False

    @staticmethod
    def _generate_selector(elem) -> str:
        if elem.get("id"):
            return f"#{elem['id']}"
        classes = elem.get("class")
        if classes:
            c = ".".join(classes if isinstance(classes, list) else str(classes).split())
            return f"{elem.name}.{c}"
        return elem.name
