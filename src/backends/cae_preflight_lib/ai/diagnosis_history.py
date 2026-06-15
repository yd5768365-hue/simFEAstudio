from __future__ import annotations

import logging
import os
import json
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class IssueHistoryStats:
    hits: int = 0
    avg_score: float = 0.0
    conflict_rate: float = 0.0


@dataclass(frozen=True)
class IssueObservation:
    issue_key: str
    category: str
    evidence_score: float
    source_trust: float
    support_count: int
    has_conflict: bool


@dataclass(frozen=True)
class SimilarIssueStats:
    issue_key: str
    hits: int
    avg_score: float
    conflict_rate: float
    similarity: float


SIMILARITY_STOPWORDS = {
    "with",
    "from",
    "that",
    "this",
    "were",
    "have",
    "has",
    "been",
    "into",
    "while",
    "where",
    "when",
    "there",
    "cannot",
    "could",
    "would",
    "should",
    "error",
    "warning",
    "issue",
    "detected",
    "possible",
    "check",
    "model",
    "results",
    "likely",
}


def _tokenize_issue_key(text: str) -> set[str]:
    tokens = set()
    for token in re.split(r"\W+", text.lower()):
        tok = token.strip()
        if len(tok) < 3:
            continue
        if tok.isdigit():
            continue
        if tok in SIMILARITY_STOPWORDS:
            continue
        tokens.add(tok)
    return tokens


def _calculate_similarity(left: str, right: str) -> float:
    left_tokens = _tokenize_issue_key(left)
    right_tokens = _tokenize_issue_key(right)
    if not left_tokens or not right_tokens:
        return 0.0

    common = len(left_tokens & right_tokens)
    if common <= 0:
        return 0.0

    # Blend asymmetric and Jaccard-like overlap for stable matching.
    coverage = common / max(len(left_tokens), 1)
    jaccard = common / max(len(left_tokens | right_tokens), 1)
    return max(0.0, min(1.0, 0.65 * coverage + 0.35 * jaccard))


class DiagnosisHistoryStore:
    """Lightweight issue-observation store used for history consistency checks."""

    def __init__(self, db_path: Optional[Path] = None):
        raw_path = str(db_path).strip() if db_path is not None else ""
        if not raw_path:
            raw_path = (os.getenv("CAE_DIAG_HISTORY_DB_PATH") or "").strip()

        self.db_path: Optional[Path] = Path(raw_path) if raw_path else None
        self.jsonl_path: Optional[Path] = None
        self.mode = "disabled"
        self.enabled = self.db_path is not None
        if not self.enabled:
            return

        try:
            assert self.db_path is not None
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._init_database()
            self.mode = "sqlite"
        except Exception as exc:
            log.warning(
                "Failed to initialize diagnosis history DB %s: %s; falling back to JSONL store",
                self.db_path,
                exc,
            )
            self._init_json_fallback()

    def _connect(self) -> sqlite3.Connection:
        if self.db_path is None:
            raise RuntimeError("diagnosis history store is disabled")
        return sqlite3.connect(str(self.db_path))

    def _init_database(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS issue_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    observed_at TEXT NOT NULL,
                    issue_key TEXT NOT NULL,
                    category TEXT NOT NULL,
                    evidence_score REAL NOT NULL,
                    source_trust REAL NOT NULL,
                    support_count INTEGER NOT NULL,
                    has_conflict INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_issue_observations_key_cat
                ON issue_observations (issue_key, category)
                """
            )

    def _init_json_fallback(self) -> None:
        if self.db_path is None:
            self.enabled = False
            return
        self.jsonl_path = self.db_path.with_suffix(f"{self.db_path.suffix}.jsonl")
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.jsonl_path.exists():
            self.jsonl_path.write_text("", encoding="utf-8")
        self.mode = "jsonl"
        self.enabled = True

    def get_stats(self, *, issue_key: str, category: str) -> IssueHistoryStats:
        if not self.enabled:
            return IssueHistoryStats()

        if self.mode == "sqlite":
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT
                        COUNT(*) AS hits,
                        AVG(evidence_score) AS avg_score,
                        AVG(has_conflict) AS conflict_rate
                    FROM issue_observations
                    WHERE issue_key = ? AND category = ?
                    """,
                    (issue_key, category),
                ).fetchone()

            if not row:
                return IssueHistoryStats()

            hits = int(row[0] or 0)
            avg_score = float(row[1] or 0.0)
            conflict_rate = float(row[2] or 0.0)
            return IssueHistoryStats(hits=hits, avg_score=avg_score, conflict_rate=conflict_rate)

        if self.mode == "jsonl" and self.jsonl_path is not None:
            hits = 0
            score_sum = 0.0
            conflict_sum = 0.0
            try:
                for line in self.jsonl_path.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    item = json.loads(line)
                    if item.get("issue_key") != issue_key or item.get("category") != category:
                        continue
                    hits += 1
                    score_sum += float(item.get("evidence_score", 0.0) or 0.0)
                    conflict_sum += 1.0 if bool(item.get("has_conflict")) else 0.0
            except Exception as exc:
                log.warning("Failed to read diagnosis history JSONL %s: %s", self.jsonl_path, exc)
                return IssueHistoryStats()
            if hits <= 0:
                return IssueHistoryStats()
            return IssueHistoryStats(
                hits=hits,
                avg_score=score_sum / hits,
                conflict_rate=conflict_sum / hits,
            )

        return IssueHistoryStats()

    def _iter_grouped_stats(self, *, category: str):
        if not self.enabled:
            return

        if self.mode == "sqlite":
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT
                        issue_key,
                        COUNT(*) AS hits,
                        AVG(evidence_score) AS avg_score,
                        AVG(has_conflict) AS conflict_rate
                    FROM issue_observations
                    WHERE category = ?
                    GROUP BY issue_key
                    """,
                    (category,),
                ).fetchall()
            for row in rows:
                yield (
                    str(row[0] or ""),
                    int(row[1] or 0),
                    float(row[2] or 0.0),
                    float(row[3] or 0.0),
                )
            return

        if self.mode == "jsonl" and self.jsonl_path is not None:
            grouped: dict[str, dict[str, float]] = defaultdict(
                lambda: {"hits": 0.0, "score_sum": 0.0, "conflict_sum": 0.0}
            )
            try:
                for line in self.jsonl_path.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    item = json.loads(line)
                    if item.get("category") != category:
                        continue
                    key = str(item.get("issue_key") or "")
                    if not key:
                        continue
                    bucket = grouped[key]
                    bucket["hits"] += 1.0
                    bucket["score_sum"] += float(item.get("evidence_score", 0.0) or 0.0)
                    bucket["conflict_sum"] += 1.0 if bool(item.get("has_conflict")) else 0.0
            except Exception as exc:
                log.warning("Failed to read diagnosis history JSONL %s: %s", self.jsonl_path, exc)
                return

            for key, bucket in grouped.items():
                hits = int(bucket["hits"])
                if hits <= 0:
                    continue
                yield (
                    key,
                    hits,
                    float(bucket["score_sum"]) / hits,
                    float(bucket["conflict_sum"]) / hits,
                )

    def get_similar_stats(
        self,
        *,
        issue_key: str,
        category: str,
        limit: int = 3,
        min_similarity: float = 0.45,
    ) -> list[SimilarIssueStats]:
        if not self.enabled or limit <= 0:
            return []

        candidates: list[SimilarIssueStats] = []
        for key, hits, avg_score, conflict_rate in self._iter_grouped_stats(category=category):
            if not key or key == issue_key or hits <= 0:
                continue
            similarity = _calculate_similarity(issue_key, key)
            if similarity < min_similarity:
                continue
            candidates.append(
                SimilarIssueStats(
                    issue_key=key,
                    hits=hits,
                    avg_score=avg_score,
                    conflict_rate=conflict_rate,
                    similarity=similarity,
                )
            )

        candidates.sort(
            key=lambda item: (
                -item.similarity,
                -item.hits,
                -item.avg_score,
                item.conflict_rate,
            )
        )
        return candidates[:limit]

    def record_observations(self, observations: Iterable[IssueObservation]) -> None:
        if not self.enabled:
            return

        now = datetime.now(timezone.utc).isoformat()
        rows = [
            (
                now,
                item.issue_key,
                item.category,
                float(item.evidence_score),
                float(item.source_trust),
                int(item.support_count),
                1 if item.has_conflict else 0,
            )
            for item in observations
        ]
        if not rows:
            return

        if self.mode == "sqlite":
            with self._connect() as conn:
                conn.executemany(
                    """
                    INSERT INTO issue_observations (
                        observed_at,
                        issue_key,
                        category,
                        evidence_score,
                        source_trust,
                        support_count,
                        has_conflict
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
            return

        if self.mode == "jsonl" and self.jsonl_path is not None:
            payload_rows = []
            for row in rows:
                payload_rows.append(
                    json.dumps(
                        {
                            "observed_at": row[0],
                            "issue_key": row[1],
                            "category": row[2],
                            "evidence_score": row[3],
                            "source_trust": row[4],
                            "support_count": row[5],
                            "has_conflict": bool(row[6]),
                        },
                        ensure_ascii=False,
                    )
                )
            with self.jsonl_path.open("a", encoding="utf-8") as fp:
                for payload in payload_rows:
                    fp.write(payload + "\n")
