from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable


class RuleVersionTracker:
    """Store source-scoped rule history and audit current rules for staleness/conflicts."""

    def __init__(self, connection: sqlite3.Connection, stale_after_days: int = 365) -> None:
        if stale_after_days < 0:
            raise ValueError("stale_after_days must be zero or greater")
        self.connection = connection
        self.connection.row_factory = sqlite3.Row
        self.stale_after_days = stale_after_days

    def record_rules(
        self,
        scheme_id: str,
        rules: Iterable[dict[str, Any]],
        source_url: str,
        source_name: str | None = None,
        source_updated_at: str | date | datetime | None = None,
        observed_at: str | date | datetime | None = None,
        complete_snapshot: bool = False,
    ) -> list[dict[str, Any]]:
        if not scheme_id or not str(scheme_id).strip():
            raise ValueError("scheme_id is required")
        if not source_url or not str(source_url).strip():
            raise ValueError("source_url is required to retain rule provenance")

        observed = self._timestamp(observed_at)
        source_updated = self._timestamp(source_updated_at) if source_updated_at is not None else None
        recorded = []
        seen_rule_keys: set[str] = set()

        with self.connection:
            for rule in rules:
                normalized = self._normalize_rule(rule)
                rule_key = normalized["rule_key"]
                if rule_key in seen_rule_keys:
                    raise ValueError(f"Duplicate rule key in source snapshot: {rule_key}")
                seen_rule_keys.add(rule_key)
                current = self.connection.execute(
                    """
                    SELECT * FROM scholarship_rule_versions
                    WHERE scheme_id = ? AND rule_key = ? AND source_url = ? AND is_current = 1
                    """,
                    (scheme_id, rule_key, source_url),
                ).fetchone()

                if current and current["content_hash"] == normalized["content_hash"]:
                    self.connection.execute(
                        """
                        UPDATE scholarship_rule_versions
                        SET source_name = COALESCE(?, source_name),
                            source_updated_at = COALESCE(?, source_updated_at),
                            last_seen_at = ?
                        WHERE id = ?
                        """,
                        (source_name, source_updated, observed, current["id"]),
                    )
                    row = self.connection.execute(
                        "SELECT * FROM scholarship_rule_versions WHERE id = ?", (current["id"],)
                    ).fetchone()
                    recorded.append(dict(row))
                    continue

                if current:
                    self.connection.execute(
                        "UPDATE scholarship_rule_versions SET is_current = 0 WHERE id = ?",
                        (current["id"],),
                    )
                version = self.connection.execute(
                    """
                    SELECT COALESCE(MAX(version), 0) + 1 AS next_version
                    FROM scholarship_rule_versions
                    WHERE scheme_id = ? AND rule_key = ? AND source_url = ?
                    """,
                    (scheme_id, rule_key, source_url),
                ).fetchone()["next_version"]
                cursor = self.connection.execute(
                    """
                    INSERT INTO scholarship_rule_versions (
                        scheme_id, rule_key, source_url, source_name, version,
                        field, operator, value_json, description, required,
                        condition_hash, content_hash, source_updated_at,
                        first_seen_at, last_seen_at, is_current
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                    """,
                    (
                        scheme_id,
                        rule_key,
                        source_url,
                        source_name,
                        version,
                        normalized["field"],
                        normalized["operator"],
                        normalized["value_json"],
                        normalized["description"],
                        normalized["required"],
                        normalized["condition_hash"],
                        normalized["content_hash"],
                        source_updated,
                        observed,
                        observed,
                    ),
                )
                row = self.connection.execute(
                    "SELECT * FROM scholarship_rule_versions WHERE id = ?", (cursor.lastrowid,)
                ).fetchone()
                recorded.append(dict(row))

            if complete_snapshot:
                current_rows = self.connection.execute(
                    """
                    SELECT id, rule_key FROM scholarship_rule_versions
                    WHERE scheme_id = ? AND source_url = ? AND is_current = 1
                    """,
                    (scheme_id, source_url),
                ).fetchall()
                for row in current_rows:
                    if row["rule_key"] not in seen_rule_keys:
                        self.connection.execute(
                            """
                            UPDATE scholarship_rule_versions
                            SET is_current = 0, withdrawn_at = ?, last_seen_at = ?
                            WHERE id = ?
                            """,
                            (observed, observed, row["id"]),
                        )
        return recorded

    def get_history(self, scheme_id: str, rule_key: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM scholarship_rule_versions WHERE scheme_id = ?"
        params: list[Any] = [scheme_id]
        if rule_key is not None:
            sql += " AND rule_key = ?"
            params.append(rule_key)
        sql += " ORDER BY rule_key, source_url, version"
        return [self._public_rule(dict(row)) for row in self.connection.execute(sql, params).fetchall()]

    def audit(
        self,
        scheme_id: str | None = None,
        as_of: str | date | datetime | None = None,
    ) -> dict[str, Any]:
        audited_at = self._timestamp(as_of)
        audited_datetime = datetime.fromisoformat(audited_at)
        sql = "SELECT * FROM scholarship_rule_versions WHERE is_current = 1"
        params: list[Any] = []
        if scheme_id is not None:
            sql += " AND scheme_id = ?"
            params.append(scheme_id)
        sql += " ORDER BY scheme_id, rule_key, source_url"
        rows = [dict(row) for row in self.connection.execute(sql, params).fetchall()]

        grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[(row["scheme_id"], row["rule_key"])].append(row)

        conflicts = []
        outdated = []
        for (current_scheme, rule_key), versions in grouped.items():
            condition_hashes = {item["condition_hash"] for item in versions}
            if len(condition_hashes) > 1:
                conflicts.append({
                    "scheme_id": current_scheme,
                    "rule_key": rule_key,
                    "status": "conflict",
                    "versions": [self._public_rule(item) for item in versions],
                })
            for item in versions:
                date_value = item["source_updated_at"] or item["last_seen_at"]
                date_basis = "source_updated_at" if item["source_updated_at"] else "last_seen_at"
                date_datetime = datetime.fromisoformat(date_value)
                age_days = (audited_datetime - date_datetime).days
                if age_days > self.stale_after_days:
                    outdated.append({
                        **self._public_rule(item),
                        "status": "outdated",
                        "age_days": age_days,
                        "stale_after_days": self.stale_after_days,
                        "date_basis": date_basis,
                    })

        return {
            "scheme_id": scheme_id,
            "audited_at": audited_at,
            "stale_after_days": self.stale_after_days,
            "current_rule_count": len(rows),
            "conflict_count": len(conflicts),
            "outdated_count": len(outdated),
            "conflicts": conflicts,
            "outdated": outdated,
        }

    def _normalize_rule(self, rule: dict[str, Any]) -> dict[str, Any]:
        field = rule.get("field") or rule.get("attribute")
        if not field:
            raise ValueError("Each tracked rule must include a field")
        operator = str(rule.get("operator", "eq"))
        rule_key = str(rule.get("id") or rule.get("rule_id") or field)
        value_json = json.dumps(rule.get("value"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        required = bool(rule.get("required", True))
        description = str(rule.get("description", ""))
        condition_json = json.dumps(
            {"field": field, "operator": operator, "value": rule.get("value"), "required": required},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        content_json = json.dumps(
            {"condition": condition_json, "description": description},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return {
            "rule_key": rule_key,
            "field": str(field),
            "operator": operator,
            "value_json": value_json,
            "description": description,
            "required": int(required),
            "condition_hash": self._hash(condition_json),
            "content_hash": self._hash(content_json),
        }

    def _public_rule(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "scheme_id": row["scheme_id"],
            "rule_key": row["rule_key"],
            "field": row["field"],
            "operator": row["operator"],
            "value": json.loads(row["value_json"]),
            "description": row["description"],
            "required": bool(row["required"]),
            "source_url": row["source_url"],
            "source_name": row["source_name"],
            "version": row["version"],
            "source_updated_at": row["source_updated_at"],
            "first_seen_at": row["first_seen_at"],
            "last_seen_at": row["last_seen_at"],
            "is_current": bool(row["is_current"]),
            "withdrawn_at": row["withdrawn_at"],
        }

    def _timestamp(self, value: str | date | datetime | None) -> str:
        if value is None:
            parsed = datetime.now(timezone.utc)
        elif isinstance(value, datetime):
            parsed = value
        elif isinstance(value, date):
            parsed = datetime.combine(value, datetime.min.time())
        else:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()

    def _hash(self, value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()
