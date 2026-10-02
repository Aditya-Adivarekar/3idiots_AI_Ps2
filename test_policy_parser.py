from scholarship_pipeline import PolicyRuleParser


def test_parse_policy_text_extracts_standardized_rules():
    policy_text = (
        "Applicant must be a resident of Maharashtra or Karnataka. "
        "Annual family income should be less than ₹2.5 lakh. "
        "Minimum 75% marks in Class 12 are required."
    )

    parsed = PolicyRuleParser().parse_policy_text(policy_text)

    assert parsed["rules"]
    assert any(rule["field"] == "state" and rule["operator"] == "in" for rule in parsed["rules"])
    assert any(rule["field"] == "annual_income" and rule["operator"] == "lte" for rule in parsed["rules"])
    assert any(rule["field"] == "marks" and rule["operator"] == "gte" for rule in parsed["rules"])
    assert all("id" in rule and "value" in rule for rule in parsed["rules"])
