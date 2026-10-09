export type WorkflowStatus =
  | "created"
  | "validating"
  | "waiting_for_input"
  | "evaluating"
  | "completed"
  | "review_required"
  | "failed";

export interface Provenance {
  provenance_id: string;
  source_type: string;
  source_ref: string | null;
  source_uri: string | null;
  method: string;
  access_status: string;
  content_hash: string | null;
  excerpt: string | null;
  created_at: string;
}

export interface Evidence {
  evidence_id: string;
  claim_id: string | null;
  dimension: string | null;
  status: string;
  content: Record<string, unknown> | string;
  provenance_refs: string[];
  confidence: string;
  source_reliability: string;
  supports_claim: boolean;
  notes: string | null;
}

export interface DimensionEvaluation {
  dimension: string;
  applicability: string;
  resolution: string;
  raw_value: string | null;
  exclusion_reason: string | null;
  evidence_refs: string[];
  requirement_refs: string[];
  provenance_refs: string[];
  rationale: string;
}

export interface DimensionScore {
  dimension: string;
  resolution: string;
  weight: string;
  raw_value: string | null;
  normalized_value: string | null;
  weighted_contribution: string;
  evidence_refs: string[];
}

export type GateStatus = "PASS" | "FAIL" | "NOT_APPLICABLE";

export interface PolicyGate {
  gate_id: string;
  name: string;
  status: GateStatus;
  requirement_refs: string[];
  evidence_refs: string[];
  rationale: string;
  configuration_ref: string;
}

export interface ScreeningReport {
  screening_id: string;
  workflow_status: WorkflowStatus;
  classification: {
    jd_type: string;
    rationale: string;
    provenance_refs: string[];
  } | null;
  claims: Array<Record<string, unknown>>;
  evidence: Evidence[];
  provenances: Provenance[];
  keyword_matches: Array<Record<string, unknown>>;
  deterministic_semantic_matches: Array<Record<string, unknown>>;
  llm_semantic_proposals: Array<Record<string, unknown>>;
  evaluation: {
    screening_id: string;
    dimensions: DimensionEvaluation[];
    contradiction_refs: string[];
    deterministic: boolean;
  } | null;
  score: {
    screening_id: string;
    score: string | null;
    applicable_weight_total: string;
    dimensions: DimensionScore[];
    audit: Array<Record<string, unknown>>;
  } | null;
  policy: {
    screening_id: string;
    gates: PolicyGate[];
    review_requests: Array<Record<string, unknown>>;
    workflow_status: WorkflowStatus;
    suitability_eligible: boolean;
    confidence_level: string;
    configuration_ref: string;
  } | null;
  review_requests: Array<Record<string, unknown>>;
  explanation: {
    summary: string;
    dimensions: Array<Record<string, unknown>>;
    generated_by: string;
  } | null;
}

export interface ScreeningAPIResponse {
  report: ScreeningReport;
  interruption: {
    screening_id: string;
    current_node: string;
    required_inputs_missing: string[];
    revision: number;
  } | null;
}
