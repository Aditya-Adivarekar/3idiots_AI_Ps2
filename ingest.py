from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, List
from urllib.parse import urlparse
from urllib.request import url2pathname

import requests
from pypdf import PdfReader


@dataclass
class ScholarshipRecord:
    id: str
    title: str
    organization: str
    source_id: str
    source_type: str
    url: str
    description: str
    eligibility: str
    amount: str
    category: str
    state: str
    course_level: str
    gender: str
    income_band: str
    deadline: str
    document_hash: str
    raw_text: str
    fetched_at: str
    is_active: int = 1


class UnifiedScholarshipIndexer:
    def __init__(self, db_path: str = "scholarships.db") -> None:
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        schema_path = Path(__file__).with_name("schema.sql")
        sql = schema_path.read_text(encoding="utf-8")
        self.conn.executescript(sql)
        self.conn.commit()

    def upsert_source(self, source: dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO data_sources(id, name, source_type, url, jurisdiction, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                source_type = excluded.source_type,
                url = excluded.url,
                jurisdiction = excluded.jurisdiction,
                metadata = excluded.metadata
            """,
            (
                source["id"],
                source["name"],
                source["source_type"],
                source.get("url"),
                source.get("jurisdiction"),
                json.dumps(source.get("metadata", {}), ensure_ascii=False),
            ),
        )
        self.conn.commit()

    def _hash_text(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _fetch_text_from_url(self, url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme == "file":
            file_path = parsed.path
            if os.name == "nt" and file_path.startswith("/") and len(file_path) >= 3 and file_path[2] == ":":
                file_path = file_path[1:]
            local_path = Path(url2pathname(file_path))
            if not local_path.exists():
                raise FileNotFoundError(f"Source file not found: {local_path}")
            if local_path.suffix.lower() == ".pdf":
                return self._extract_pdf_text(local_path)
            return local_path.read_text(encoding="utf-8", errors="ignore")

        response = requests.get(url, timeout=20)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "").lower()
        if "application/pdf" in content_type or url.lower().endswith(".pdf"):
            return self._extract_pdf_bytes(response.content)
        return response.text

    def _extract_pdf_bytes(self, raw_bytes: bytes) -> str:
        try:
            from io import BytesIO

            reader = PdfReader(BytesIO(raw_bytes))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception:
            return ""

    def _extract_pdf_text(self, path: Path) -> str:
        try:
            reader = PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception:
            return ""

    def _normalize_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", text or "").strip()

    def _extract_field(self, text: str, patterns: Iterable[str]) -> str:
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                return match.group(1).strip() if match.lastindex else match.group(0).strip()
        return ""

    def _parse_record(self, source: dict[str, Any], source_text: str) -> ScholarshipRecord:
        cleaned = self._normalize_text(source_text)
        title = self._extract_field(cleaned, [r"(?:title|scholarship)\s*[:\-]?\s*(.+?)(?:\.|\n|\b(?:eligibility|amount|last date|deadline)\b)", r"([A-Z][A-Za-z0-9 &/()\-]{20,})"]) or "Untitled scholarship"
        description = cleaned[:500]
        eligibility = self._extract_field(cleaned, [r"eligibility[:\-]?\s*(.+?)(?:\.\s*(?:amount|benefit|deadline)|$)", r"who can apply[:\-]?\s*(.+)"])
        amount = self._extract_field(cleaned, [r"amount[:\-]?\s*(₹?\d[\d,\s.]*[\sA-Za-z]*)", r"benefit[:\-]?\s*(₹?\d[\d,\s.]*[\sA-Za-z]*)"]) or "Not specified"
        category = self._extract_field(cleaned, [r"category[:\-]?\s*(SC|ST|OBC|General|Minority|EWS|Women|Disabled)", r"(SC|ST|OBC|General|Minority|EWS|Women|Disabled)"]) or "Any"
        state = self._extract_field(cleaned, [r"state[:\-]?\s*([A-Za-z ]+)", r"domicile[:\-]?\s*([A-Za-z ]+)"]) or source.get("jurisdiction", "")
        course_level = self._extract_field(cleaned, [r"course[:\-]?\s*(\w+(?:\s*\w+)*)", r"student[:\-]?\s*(\w+(?:\s*\w+)*)"]) or "Any"
        gender = self._extract_field(cleaned, [r"gender[:\-]?\s*(female|male|women|men|girl|boy|any)", r"(female|male|women|men|girl|boy|any)"]) or "Any"
        income_band = self._extract_field(cleaned, [r"income[:\-]?\s*(₹?\d[\d,\s.]*\s*(?:lakh|lac|crore|yearly|annum))", r"family income[:\-]?\s*(₹?\d[\d,\s.]*\s*(?:lakh|lac|crore|yearly|annum))"]) or "Not specified"
        deadline = self._extract_field(cleaned, [r"deadline[:\-]?\s*([A-Za-z0-9,\- ]{5,})", r"last date[:\-]?\s*([A-Za-z0-9,\- ]{5,})"]) or "Not specified"

        record_id = f"{source['id']}:{self._hash_text(title + cleaned)[:12]}"
        fetched_at = datetime.now(timezone.utc).isoformat()

        return ScholarshipRecord(
            id=record_id,
            title=title,
            organization=source.get("name", "Unknown organization"),
            source_id=source["id"],
            source_type=source["source_type"],
            url=source.get("url", ""),
            description=description,
            eligibility=eligibility or "Not specified",
            amount=amount,
            category=category,
            state=state,
            course_level=course_level,
            gender=gender,
            income_band=income_band,
            deadline=deadline,
            document_hash=self._hash_text(cleaned),
            raw_text=cleaned,
            fetched_at=fetched_at,
            is_active=1,
        )

    def ingest_source(self, source: dict[str, Any]) -> List[ScholarshipRecord]:
        self.upsert_source(source)
        text = self._fetch_text_from_url(source["url"])
        record = self._parse_record(source, text)
        self.insert_record(record)
        return [record]

    def insert_record(self, record: ScholarshipRecord) -> None:
        self.conn.execute(
            """
            INSERT INTO scholarships (
                id, title, organization, source_id, source_type, url, description,
                eligibility, amount, category, state, course_level, gender,
                income_band, deadline, document_hash, raw_text, fetched_at, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                organization = excluded.organization,
                source_id = excluded.source_id,
                source_type = excluded.source_type,
                url = excluded.url,
                description = excluded.description,
                eligibility = excluded.eligibility,
                amount = excluded.amount,
                category = excluded.category,
                state = excluded.state,
                course_level = excluded.course_level,
                gender = excluded.gender,
                income_band = excluded.income_band,
                deadline = excluded.deadline,
                document_hash = excluded.document_hash,
                raw_text = excluded.raw_text,
                fetched_at = excluded.fetched_at,
                is_active = excluded.is_active
            """,
            (
                record.id,
                record.title,
                record.organization,
                record.source_id,
                record.source_type,
                record.url,
                record.description,
                record.eligibility,
                record.amount,
                record.category,
                record.state,
                record.course_level,
                record.gender,
                record.income_band,
                record.deadline,
                record.document_hash,
                record.raw_text,
                record.fetched_at,
                record.is_active,
            ),
        )
        self.conn.commit()

    def search(self, query: str, filters: dict[str, Any] | None = None) -> List[dict[str, Any]]:
        filters = filters or {}
        search_term = query.strip()
        clauses = []
        params: List[Any] = []

        base_sql = "SELECT s.* FROM scholarships s"
        if search_term:
            base_sql += " JOIN scholarships_fts ON scholarships_fts.rowid = s.rowid WHERE scholarships_fts MATCH ?"
            params.append(search_term)

        if filters.get("state"):
            clauses.append("s.state = ?")
            params.append(filters["state"])

        if filters.get("category"):
            clauses.append("s.category = ?")
            params.append(filters["category"])

        if filters.get("source_type"):
            clauses.append("s.source_type = ?")
            params.append(filters["source_type"])

        if clauses:
            glue = " AND " if search_term else " WHERE "
            base_sql += f"{glue}{' AND '.join(clauses)}"

        base_sql += " ORDER BY s.fetched_at DESC LIMIT 20"

        rows = self.conn.execute(base_sql, params).fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        self.conn.close()


def _load_sources(config_path: str) -> List[dict[str, Any]]:
    with open(config_path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest scholarship data from portal, college, and PDF sources into SQLite.")
    parser.add_argument("--db", default="scholarship_pipeline/data/scholarships.db", help="Path to SQLite database.")
    parser.add_argument("--sources", default="scholarship_pipeline/sample_sources.json", help="JSON list of source definitions.")
    parser.add_argument("--search", default="", help="Optional keyword to search after ingesting.")
    args = parser.parse_args()

    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    indexer = UnifiedScholarshipIndexer(str(db_path))
    try:
        for source in _load_sources(args.sources):
            indexer.ingest_source(source)

        if args.search:
            results = indexer.search(args.search)
            for row in results:
                print(f"{row['title']} | {row['source_type']} | {row['state']} | {row['amount']}")
            print(f"\nFound {len(results)} matching scholarship records.")
    finally:
        indexer.close()


if __name__ == "__main__":
    main()
