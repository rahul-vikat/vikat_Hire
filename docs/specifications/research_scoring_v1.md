# Research Scoring Rubric v1

**Version:** `1.0.0` (target version; not frozen)  
**Status:** `PROPOSED / REQUIRES APPROVAL`  
**Scope:** Display-only company and college research  
**Implementation status:** Blocked pending approval of the decisions identified below

## 1. Purpose and authority

This document records the approved scoring boundaries and identifies the
dimension-specific decisions that remain unspecified. It is not an executable
rubric. No score mapping, threshold, weighting, or conflict-resolution rule is
authorized by this document unless explicitly marked **APPROVED**.

Research results are informational/display-only. They must not affect candidate
evaluation, the VerifyHire 2.2.0 score, policy, gates, eligibility, seniority,
or a hiring decision. Deterministic code is authoritative for any future
research scoring. LLMs cannot assign, select, adjust, or approve scores.

SearXNG is used only by collection. Entity validation, dimension relevance,
evidence assembly, and any future scoring/ranking are deterministic and have no
network access. Configuration remains separate from scoring logic. Every future
result must retain its evidence, decision, and provenance references.

## 2. Repository baseline

The repository currently defines the nine research dimensions, fixed query
templates, configured lexical relevance terms, entity identity validation,
audited filtering outcomes, provenance, and assembled evidence. Assembly keeps
explicit empty dimension groups and retains rejected/ambiguous observations for
audit.

The repository does **not** currently define research scoring contracts, a
research scoring configuration, dimension score mappings, a research overall
rank formula, or a research scoring evaluator. The relevance vocabulary is a
discovery/filtering rule only; it is not a scoring rubric. The existing
`scoring_2_2_0.py` is the candidate-scoring configuration and is outside this
research specification.

The current research observation contract contains SearXNG result title, URL,
content, query, entity/dimension context, and provenance. It does not define a
structured fact schema for financial metrics, placement statistics, ranking
editions, certification status, or other score inputs. A future implementation
must not silently turn unstructured text or a relevance-term match into a
scoreable fact.

## 3. Approved v1 rules

The following top-level rules are **APPROVED**:

1. A scored dimension uses the inclusive numeric range `0–100`.
2. A dimension supports `SCORED`, `INSUFFICIENT_EVIDENCE`, `CONFLICTED`, and
   `NOT_APPLICABLE`. `NOT_APPLICABLE` is reserved for future applicability
   cases and is not expected for the current fixed dimensions.
3. Absence of evidence is not score `0`. Zero is permitted only when an
   approved mapping explicitly assigns zero to qualifying evidence.
4. An overall rank is emitted only when every applicable dimension is
   `SCORED`; otherwise `overall_rank = None`. Partial overall ranks are
   prohibited.
5. No source-quality weighting, universal recency weighting, cross-system
   ranking normalization, LLM scoring authority, or search-result-count bonus
   is permitted.
6. No research result may flow into candidate scoring, policy, eligibility,
   seniority, or hiring decisions.

These rules do **not** determine any dimension’s fact-to-score mapping or the
overall aggregation formula.

## 4. Common evidence and result requirements

### 4.1 Evidence boundary

Only evidence that passed the existing entity validation and dimension
relevance stages may be considered by a future scoring evaluator. Passing those
stages makes an observation eligible for consideration; it does not establish a
fact, its truth, its importance, or a score.

Rejected and ambiguous observations remain auditable but cannot support a
numeric score. Query membership, result count, URL, title alone, and configured
relevance terms alone are not score inputs.

### 4.2 Future score result shape

The future contract must represent, at minimum:

```text
dimension
state: SCORED | INSUFFICIENT_EVIDENCE | CONFLICTED | NOT_APPLICABLE
score: Decimal/integer in [0, 100] when SCORED; otherwise None
rationale
accepted evidence/result references
provenance references
rubric/configuration version
```

The exact contract name and whether fact extraction is a separate contract are
not selected here. The implementation must use existing contracts where
appropriate and add only the minimum missing contract once the rubric is
approved.

### 4.3 General handling that is approved

- Missing or unscoreable evidence must not be replaced with zero.
- Evidence without an approved mapping is retained for display/audit and does
  not yield a score.
- Repeated search observations are not independent facts merely because they
  appear more than once.
- No bonus may be assigned solely for the number of results or sources.
- No universal recency weighting is applied. Evidence expiry, validity windows,
  or dimension-specific recency requirements are not defined by the approved
  rules and remain unspecified.
- The evaluator must be deterministic, pure, and reproducible for identical
  evidence and the same rubric version.

### 4.4 Unspecified common rules

The following remain **UNSPECIFIED — REQUIRES APPROVAL**:

- what constitutes a normalized/identical underlying fact across results;
- what qualifies as independent corroboration;
- whether and how corroboration affects a score;
- how a fact is considered attributable to the entity when evidence text is
  ambiguous after the existing entity-validation stage;
- how to classify unverifiable claims beyond preserving them without score;
- the exact conditions that constitute a material conflict;
- conflict behavior for different periods, methodologies, units, currencies,
  populations, and minor numerical discrepancies;
- whether any disputed fact can be excluded while other facts still score the
  dimension, or whether it makes the whole dimension `CONFLICTED`;
- the score precision and rounding mode for dimension values;
- any conversion from extracted text to a typed fact.

Until these decisions are approved, no implementation may resolve them using
heuristics, general knowledge, or LLM judgment.

## 5. Dimension rubrics

For all dimensions below, the listed fact families are candidate inputs to the
rubric discussion, not approved scoring mappings. They become scoreable only
after the required facts, conditions, and exact score/band mapping are
explicitly approved. Every mapping currently reads:

```text
fact/condition → score: UNSPECIFIED — REQUIRES APPROVAL
```

### 5.1 Company: `financial_valuation`

**Candidate fact families:** funding rounds and amounts; revenue; valuation;
profitability; financial growth/trajectory.

**Non-scoreable by themselves under current approval:** a funding announcement,
an absolute revenue/valuation amount, investor names, or a generic claim of
growth. These may be preserved as research evidence but there is no approved
interpretation that maps them to a score.

**Potentially required fields, not yet mandated:** metric/value, currency and
unit, reporting period, whether a value is actual or estimated, and an approved
comparison basis. Which fields are mandatory depends on the fact type and is
**UNSPECIFIED — REQUIRES APPROVAL**.

**Fact-to-score mapping:** `UNSPECIFIED — REQUIRES APPROVAL`. In particular,
there is no approved rule that larger funding, revenue, or valuation means a
higher score, nor an approved way to compare organizations or financial
periods.

**Multiple facts/conflicts:** aggregation and material-conflict rules are
`UNSPECIFIED — REQUIRES APPROVAL`. Different financial metrics and periods must
not be combined by an invented arithmetic formula.

### 5.2 Company: `market_position`

**Candidate fact families:** customer counts/reach; market share; product
adoption; competitor comparisons; documented market-position claims.

**Non-scoreable by themselves under current approval:** product descriptions,
customer names without a defined interpretation, unsubstantiated marketing
language such as “leader,” and absolute customer counts without an approved
comparison basis.

**Potentially required fields, not yet mandated:** metric/value, unit, period,
geographic/product market, denominator or addressable market, population, and
the source’s comparison methodology. Required fields are
`UNSPECIFIED — REQUIRES APPROVAL`.

**Fact-to-score mapping:** `UNSPECIFIED — REQUIRES APPROVAL`. There is no
approved definition of a meaningful market metric, valid competitor
comparison, or score for any market-share/customer/adoption value.

**Multiple facts/conflicts:** combination, comparison population, and conflict
rules are `UNSPECIFIED — REQUIRES APPROVAL`.

### 5.3 Company: `engineering_technical`

**Candidate fact families:** patents; research; documented technologies and
technical capabilities; engineering output; architecture/platform facts.

**Non-scoreable by themselves under current approval:** an AI/technology
mention, a product feature list, a patent count without an interpretation, or
research output without an approved comparison basis. Relevance terms do not
measure technical strength.

**Potentially required fields, not yet mandated:** fact type, attributable
technical output/capability, date or period where inherently part of the fact,
counting method/denominator for quantitative facts, and any approved
comparison basis. Requirements are `UNSPECIFIED — REQUIRES APPROVAL`.

**Fact-to-score mapping:** `UNSPECIFIED — REQUIRES APPROVAL`. There is no
approved way to map patents, research, capabilities, or engineering output to
numeric bands.

**Multiple facts/conflicts:** whether qualitative and quantitative facts may
combine, and how they combine, is `UNSPECIFIED — REQUIRES APPROVAL`.

### 5.4 Company: `reputation_compliance`

**Candidate fact families:** certifications and their status; compliance
findings; regulatory events; security incidents; attributable reputation
evidence.

**Non-scoreable by themselves under current approval:** a certification name
without status/scope, a generic security/compliance claim, and absence of
reported incidents. No incident found does not establish positive compliance.

**Potentially required fields, not yet mandated:** credential/finding type,
issuing or reporting body, scope, status, effective/expiry/withdrawal dates
where applicable, and entity attribution. The relevant credential set and
required fields are `UNSPECIFIED — REQUIRES APPROVAL`.

**Fact-to-score mapping:** `UNSPECIFIED — REQUIRES APPROVAL`. Certification
types are not ranked or weighted; compliance/security events have no approved
numeric mapping.

**Multiple facts/conflicts:** current-versus-expired/withdrawn treatment,
conflicting status reports, and the material-conflict rule are
`UNSPECIFIED — REQUIRES APPROVAL`.

### 5.5 College: `official_ranking`

**Candidate fact families:** named ranking system (including NIRF, QS, THE, or
another explicitly identified system), rank, category, and edition/year.

**Non-scoreable by themselves under current approval:** an unlabelled rank,
ranking-system mention, ranking query membership, or ranking evidence lacking
the system/edition needed to interpret it.

**Potentially required fields:** ranking publisher/system, institution/category
scope, rank, edition/year, and any methodology/category stated by the ranking
source.

**Fact-to-score mapping:** `UNSPECIFIED — REQUIRES APPROVAL`. No rank range maps
to a numeric score. There is no cross-system normalization. Ranking evidence
without an approved system-specific mapping is preserved and yields no
dimension score.

**Multiple facts/conflicts:** combining systems, categories, or editions and
resolving changed ranks across editions are `UNSPECIFIED — REQUIRES APPROVAL`.

### 5.6 College: `accreditation`

**Candidate fact families:** accreditation/recognition from an identified body
such as NAAC, NBA, UGC, or AICTE, including status, grade, scope, and validity
where applicable.

**Non-scoreable by themselves under current approval:** a body-name mention,
an unscoped recognition claim, or a status lacking enough context to identify
the institution/program and applicable period.

**Potentially required fields:** accrediting/recognizing body, institution or
program scope, status, grade if used by the body, jurisdiction/context, and
validity/effective dates when the status is time-bounded.

**Fact-to-score mapping:** `UNSPECIFIED — REQUIRES APPROVAL`. No body/status/
grade equivalence or numeric band is approved. Different accreditation systems
must not be treated as equivalent by assumption.

**Multiple facts/conflicts:** simultaneous accreditations, institution versus
program credentials, expired/withdrawn status, and conflicting status reports
are `UNSPECIFIED — REQUIRES APPROVAL`.

### 5.7 College: `academic_research`

**Candidate fact families:** publications, citations, patents, faculty research,
research centers, and other explicitly documented research outputs.

**Non-scoreable by themselves under current approval:** raw publication,
citation, or patent counts; faculty size; a research-center name; or a generic
claim of research excellence. Large absolute counts do not imply a higher
score.

**Potentially required fields, not yet mandated:** metric and value, period,
population/institution scope, counting methodology, and denominator such as
faculty count where required by an approved rule.

**Fact-to-score mapping:** `UNSPECIFIED — REQUIRES APPROVAL`. No denominator,
normalization, sufficiency, or numeric band is approved.

**Multiple facts/conflicts:** combining publications, citations, patents,
centers, and different periods is `UNSPECIFIED — REQUIRES APPROVAL`.

### 5.8 College: `placements`

**Candidate fact families:** placement rate, cohort size/denominator, median or
average salary, reporting year, recruiter count/list, and published placement
report/methodology.

**Non-scoreable by themselves under current approval:** a recruiter list or
count, salary without context, placement percentage without denominator and
cohort scope, or a placement claim without a reporting period/methodology.

**Potentially required fields, not yet mandated:** cohort/program, number placed,
eligible/responding cohort denominator, reporting year, salary statistic and
currency/unit, and report methodology. Which are required for each metric is
`UNSPECIFIED — REQUIRES APPROVAL`.

**Fact-to-score mapping:** `UNSPECIFIED — REQUIRES APPROVAL`. No placement-rate
or salary band, currency normalization, or recruiter-count interpretation is
approved.

**Multiple facts/conflicts:** treatment of different programs, cohorts, years,
salary statistics, and methodologies is `UNSPECIFIED — REQUIRES APPROVAL`.

### 5.9 College: `perception_infrastructure`

**Candidate fact families:** documented campus facilities/infrastructure and
attributable perception evidence, including student-life/alumni evidence where
an approved definition makes it relevant.

**Non-scoreable by themselves under current approval:** isolated anecdotes,
generic or unsupported “top campus”/sentiment claims, search snippets without
the underlying attributable fact, and an infrastructure mention with no
specified evaluation criteria.

**Potentially required fields, not yet mandated:** facility or perception fact
type, campus/population scope, attributable basis, and any approved survey or
measurement method. Requirements are `UNSPECIFIED — REQUIRES APPROVAL`.

**Fact-to-score mapping:** `UNSPECIFIED — REQUIRES APPROVAL`. It is not decided
whether infrastructure and perception can score independently or how they
combine into one dimension.

**Multiple facts/conflicts:** representation, aggregation, and materiality of
perception evidence are `UNSPECIFIED — REQUIRES APPROVAL`.

## 6. Missing, unverifiable, incomparable, and conflict outcomes

The following state distinctions are part of the approved top-level contract,
but their exact operational triggers remain incomplete:

- `INSUFFICIENT_EVIDENCE`: approved state for no qualifying/scoreable evidence.
  Exact sufficiency criteria for each dimension are
  `UNSPECIFIED — REQUIRES APPROVAL`.
- `CONFLICTED`: approved state exists, but what constitutes a material conflict
  and whether it blocks the entire dimension are
  `UNSPECIFIED — REQUIRES APPROVAL`.
- `SCORED`: requires at least one approved fact-to-score rule to apply. No such
  rules are currently approved for any dimension.
- `NOT_APPLICABLE`: supported state, reserved for future applicability rules;
  the applicability rules are `UNSPECIFIED — REQUIRES APPROVAL`.

Unverifiable or incomparable observations must remain available for audit and
must not be converted to favorable or unfavorable numeric evidence. Whether
they are ignored alongside otherwise scoreable facts or force a non-score
state requires dimension-specific approval.

## 7. Overall rank

**Approved emission condition:** calculate a rank only if all applicable
dimensions are `SCORED`; otherwise `overall_rank = None`. No partial rank is
allowed.

**Aggregation formula:** `UNSPECIFIED — REQUIRES APPROVAL`.

The following are not selected: equal-weight arithmetic mean, weighted mean, or
another formula. Also requiring approval are output precision, rounding mode,
and the precise treatment of dimension scores at 0 and 100 within the formula.
The range of dimension scores is already approved as 0–100; no formula should
be implemented until the aggregation decision is approved.

## 8. Future configuration/versioning requirements

After rubric decisions are approved, a future versioned configuration should
contain at least:

```text
rubric_version: "1.0.0"
effective_date: REQUIRES APPROVAL
dimension_definitions: all nine dimensions
fact_types: approved typed facts per dimension
required_fields: approved requirements per fact type
score_mappings: exact conditions and score/band outputs
fact_aggregation_rules: approved duplicate/multiple-fact behavior
conflict_rules: approved materiality and resulting state
missing_evidence_rules: approved sufficiency conditions
overall_aggregation: approved formula, precision, and rounding
```

The repository has versioned configuration patterns for candidate scoring,
but no research scoring configuration convention. This document is placed in
`docs/specifications/` as the smallest standalone specification artifact; it
does not introduce a runtime configuration architecture.

## 9. Approval checklist — implementation remains blocked

Before freezing `research_scoring_v1` as authoritative, approval is required
for:

1. Exact score mappings for each fact type/combination in all nine dimensions.
2. Dimension-specific required fields and evidence sufficiency criteria.
3. Duplicate-fact identity and independent-corroboration behavior.
4. Multiple-fact aggregation within each dimension.
5. Material-conflict definition and the resulting dimension state.
6. Treatment of unverifiable/incomparable facts when other scoreable facts
   exist.
7. Any system-specific ranking mapping (or explicit decision that ranking
   evidence remains unscored until such mappings exist).
8. Overall-rank formula, output precision, and rounding rule.
9. Effective date and confirmation of rubric version `1.0.0`.

No executable scoring tests should encode numeric answers until the associated
rules are approved. Once approved, known-answer tests should cover every
approved band, boundary, missing/conflict state, aggregation case, and overall
rank condition.

## 10. Isolation and implementation constraints

Future implementation must remain in the research boundary and must not import
candidate scoring, policy, eligibility, seniority, or graph behavior into
research scoring. Candidate scoring must not import research scoring. Reports
and UI may display authoritative research results but may not recalculate them.

There is no scoring implementation in this milestone. No thresholds, weights,
fact mappings, conflict heuristics, ranking conversions, or overall-rank
formula have been selected by implication.
