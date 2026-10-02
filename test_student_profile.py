from scholarship_pipeline import (
    HybridEligibilityPipeline,
    StudentProfileService,
    UnifiedScholarshipIndexer,
)


def test_profile_service_normalizes_and_persists_profile(tmp_path):
    store_path = tmp_path / "student-profile.json"
    service = StudentProfileService(store_path)

    saved = service.save({
        "domicile": "Maharashtra",
        "course": "College degree",
        "category": "Scheduled Caste (SC)",
        "annual_income": "180000",
        "marks": "82.5",
        "gender": "Woman / girl",
        "documents": ["income", "income", "unsure"],
    })

    reloaded = StudentProfileService(store_path).get_profile()
    assert reloaded == saved
    assert reloaded["state"] == "Maharashtra"
    assert reloaded["course_level"] == "College degree"
    assert reloaded["category"] == "SC"
    assert reloaded["annual_income"] == 180000
    assert reloaded["marks"] == 82.5
    assert reloaded["gender"] == "female"
    assert reloaded["documents"] == ["income"]

    updated = service.update({"domicile": "Gujarat"})
    assert updated["state"] == "Gujarat"
    assert updated["annual_income"] == 180000


def test_saved_profile_is_reused_for_multiple_scheme_evaluations(tmp_path):
    service = StudentProfileService(tmp_path / "student-profile.json")
    profile = service.save({
        "state": "Maharashtra",
        "category": "SC",
        "annual_income": 180000,
        "marks": 82,
    })
    indexer = UnifiedScholarshipIndexer(str(tmp_path / "scholarships.db"))
    try:
        pipeline = HybridEligibilityPipeline(indexer)
        results = service.evaluate_schemes(pipeline, [
            {
                "id": "income-scheme",
                "title": "Income scholarship",
                "rules": [{"id": "income-limit", "field": "annual_income", "operator": "lte", "value": 200000}],
            },
            {
                "id": "marks-scheme",
                "title": "Merit scholarship",
                "rules": [{"id": "marks-minimum", "field": "marks", "operator": "gte", "value": 75}],
            },
        ])
    finally:
        indexer.close()

    assert len(results) == 2
    assert all(item["result"]["status"] == "evaluated" for item in results)
    assert all(item["result"]["evaluation"]["eligible"] for item in results)
    assert profile["state"] == service.get_profile()["state"]
