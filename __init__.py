"""Scholarship ingestion, matching, and policy parsing package."""

from .ingest import UnifiedScholarshipIndexer
from .hybrid import HybridEligibilityPipeline, OfficialClauseRetriever
from .application_guidance import ApplicationGuidanceService
from .document_readiness import DocumentReadinessChecker
from .document_intelligence import DocumentIntelligenceService
from .dataset_engine import DatasetEligibilityEngine
from .matcher import profile_to_rule_matching
from .policy_parser import PolicyRuleParser, extract_policy_rules, parse_policy_text
from .preconditions import validate_profile_preconditions
from .qwen import DEFAULT_QWEN_MODEL, QwenInferenceService
from .rule_versions import RuleVersionTracker
from .student_profile import (
	STUDENT_PROFILE_SCHEMA,
	StudentProfile,
	StudentProfileService,
	StudentProfileStore,
	normalize_student_profile,
)

__all__ = [
	"UnifiedScholarshipIndexer",
	"PolicyRuleParser",
	"HybridEligibilityPipeline",
	"OfficialClauseRetriever",
	"DocumentReadinessChecker",
	"DocumentIntelligenceService",
	"DatasetEligibilityEngine",
	"extract_policy_rules",
	"parse_policy_text",
	"profile_to_rule_matching",
	"validate_profile_preconditions",
	"RuleVersionTracker",
	"DEFAULT_QWEN_MODEL",
	"QwenInferenceService",
	"ApplicationGuidanceService",
	"STUDENT_PROFILE_SCHEMA",
	"StudentProfile",
	"StudentProfileService",
	"StudentProfileStore",
	"normalize_student_profile",
]
