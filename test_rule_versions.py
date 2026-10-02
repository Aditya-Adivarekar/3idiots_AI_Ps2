from scholarship_pipeline import RuleVersionTracker, UnifiedScholarshipIndexer


def test_rule_tracker_versions_source_changes_and_flags_conflicts_and_stale_sources(tmp_path):
    indexer = UnifiedScholarshipIndexer(str(tmp_path / "rules.db"))
    try:
        tracker = RuleVersionTracker(indexer.conn, stale_after_days=365)
        rule_v1 = {
            "id": "income-cap",
            "field": "annual_income",
            "operator": "lte",
            "value": 200000,
            "description": "Annual family income must not exceed Rs. 2 lakh.",
        }
        first = tracker.record_rules(
            "scheme-1",
            [rule_v1],
            source_url="https://scholarships.gov.in/scheme-a",
            source_name="National Scholarship Portal",
            source_updated_at="2024-01-10",
            observed_at="2024-01-12",
        )[0]
        assert first["version"] == 1

        rule_v2 = {**rule_v1, "value": 250000, "description": "Income cap is Rs. 2.5 lakh."}
        second = tracker.record_rules(
            "scheme-1",
            [rule_v2],
            source_url="https://scholarships.gov.in/scheme-a",
            source_name="National Scholarship Portal",
            source_updated_at="2025-01-10",
            observed_at="2025-01-12",
        )[0]
        assert second["version"] == 2

        unchanged = tracker.record_rules(
            "scheme-1",
            [rule_v2],
            source_url="https://scholarships.gov.in/scheme-a",
            source_name="National Scholarship Portal",
            source_updated_at="2025-01-10",
            observed_at="2025-02-01",
        )[0]
        assert unchanged["version"] == 2
        assert len(tracker.get_history("scheme-1", "income-cap")) == 2

        tracker.record_rules(
            "scheme-1",
            [{**rule_v2, "value": 300000}],
            source_url="https://state.gov.in/scholarships/scheme-a",
            source_name="State Scholarship Portal",
            source_updated_at="2026-09-20",
            observed_at="2026-09-21",
        )

        audit = tracker.audit(as_of="2026-10-02T00:00:00+00:00")
        assert len(audit["conflicts"]) == 1
        conflict = audit["conflicts"][0]
        assert conflict["scheme_id"] == "scheme-1"
        assert conflict["rule_key"] == "income-cap"
        assert {item["value"] for item in conflict["versions"]} == {250000, 300000}
        assert len(audit["outdated"]) == 1
        assert audit["outdated"][0]["source_url"] == "https://scholarships.gov.in/scheme-a"
        assert audit["outdated"][0]["version"] == 2
    finally:
        indexer.close()


def test_complete_source_snapshot_marks_removed_rules_withdrawn(tmp_path):
    indexer = UnifiedScholarshipIndexer(str(tmp_path / "withdrawn.db"))
    try:
        tracker = RuleVersionTracker(indexer.conn)
        source_url = "https://scholarships.gov.in/scheme-b"
        tracker.record_rules(
            "scheme-2",
            [
                {"id": "income-cap", "field": "annual_income", "operator": "lte", "value": 200000},
                {"id": "domicile", "field": "state", "operator": "eq", "value": "Maharashtra"},
            ],
            source_url=source_url,
            observed_at="2026-09-01",
        )

        tracker.record_rules(
            "scheme-2",
            [{"id": "income-cap", "field": "annual_income", "operator": "lte", "value": 200000}],
            source_url=source_url,
            observed_at="2026-09-02",
            complete_snapshot=True,
        )

        history = tracker.get_history("scheme-2", "domicile")
        assert len(history) == 1
        assert history[0]["is_current"] is False
        assert history[0]["withdrawn_at"] == "2026-09-02T00:00:00+00:00"
    finally:
        indexer.close()
