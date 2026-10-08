# Research Scoring Rubric v1

**Version:** `1.0.0` (target version; not frozen)  
**Status:** `REQUIRES HUMAN APPROVAL` (partial policy decisions recorded)
**Scope:** Display-only company and college research  
**Implementation status:** Blocked pending approval of the decisions identified below

> **Execution gate:** No research fact scoring, dimension scoring, or overall
> rank calculation is authorized until the human-policy blockers in Section 9
> are explicitly approved. The NIRF table below is illustrative only and is
> not an executable mapping or a scoring-test oracle.

## 1. Purpose and authority

This document records the policy decisions provided by the human policy owner
and identifies the decisions that still prevent an implementation-ready rubric.
It is not an executable rubric. Rules explicitly marked **APPROVED** below
reflect the supplied policy. Unresolved items remain blockers; no threshold,
mapping, or conflict rule may be inferred to fill them.

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

### 2.1 Evidence contract gap

`RawResearchResult` and the generic `Evidence` contract do not represent the
approved normalized-fact requirements as a typed research fact. Missing
research-specific fields include fact type, normalized metric/value, relevant
unit/currency, period/edition, scope, deterministic fact identity, supporting
source-observation references, and a structured unresolved-conflict link.
Provenance records preserve source observations but do not replace these fact
fields.

After the policy blockers are resolved, the smallest likely contract change is
a research-specific normalized-fact contract containing only the fields
required by the approved fact rules and linking each fact to its original
observation/provenance. Whether conflict state belongs on that fact contract or
in a linked conflict record depends on the still-unapproved conflict policy.
No contract is added in this specification-only step.

## 3. Approved v1 rules

The following top-level rules are **APPROVED**:

1. Dimension and overall scores are Decimal values from `0.00` through
   `100.00`, inclusive. Calculations use Decimal; round only at the final
   output boundary using `ROUND_HALF_UP` to two decimal places.
2. A score represents the strength of verified research evidence available to
   V-Hire under configured rules. It is not an absolute claim about the real-
   world quality or worth of an organization.
3. Evidence states are `SUFFICIENT`, `INSUFFICIENT`, and `UNAVAILABLE`.
   Dimension evaluation states are `SCORED`, `INSUFFICIENT_EVIDENCE`,
   `CONFLICTED`, and `NOT_APPLICABLE`. Their mapping to each other remains
   unresolved where stated below.
4. No qualifying evidence must not become score zero. Insufficient public
   information must not automatically imply poor performance. Zero is only
   permitted where an explicit approved rule maps qualifying evidence to zero.
5. Overall rank is emitted only if every applicable dimension is `SCORED`;
   otherwise it is `None`. Partial overall ranks are prohibited.
6. Search-result count does not contribute to score. Source quality is not a
   score weight. There is no universal recency multiplier. The supplied policy
   says to prefer the latest valid fact within a configured recency policy;
   that policy is not yet defined and remains a blocker.
7. Cross-system ranking normalization is prohibited. Ranking mappings must be
   system-specific and configuration-driven.
8. LLMs have no scoring authority. SearXNG is retrieval only; search relevance
   is not a V-Hire score. Scoring consumes normalized facts, not scraped raw
   text, and must not invent facts from snippets.
9. Research is isolated from candidate suitability scoring, VerifyHire 2.2.0
   scoring, policy, gates, eligibility, seniority, and hiring decisions.

These rules do not determine score mappings for eight dimensions. The supplied
NIRF example mapping is recorded below; other ranking systems/categories have
no approved mapping. Overall aggregation weights/formulas are recorded in
Section 7.

### 3.1 Approved score interpretation bands

| Score interval | Label |
|---|---|
| 90.00–100.00 | Very strong |
| 75.00–89.99 | Strong |
| 60.00–74.99 | Moderate |
| 40.00–59.99 | Limited |
| 20.00–39.99 | Weak |
| 0.00–19.99 | Very weak / little positive evidence |

These labels describe strength of verified research evidence under the rubric,
not intrinsic organizational quality. The bands do not supply fact-to-score
rules.

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
evidence_state: SUFFICIENT | INSUFFICIENT | UNAVAILABLE
evaluation_state: SCORED | INSUFFICIENT_EVIDENCE | CONFLICTED | NOT_APPLICABLE
score: Decimal in [0.00, 100.00] when SCORED; otherwise None
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
- No source-quality score weighting or universal recency multiplier is
  applied. The configured source-credibility eligibility rule and any
  dimension-specific recency/validity selection policy remain unspecified.
- The evaluator must be deterministic, pure, and reproducible for identical
  evidence and the same rubric version.

### 4.4 Owner-approved fact-handling rules

- A normalized fact must retain entity identity, dimension, fact type, value,
  applicable unit/currency, period/edition, scope, source observation, and
  provenance. Not every field applies to every fact type; required fields
  below remain to be finalized where noted.
- Multiple websites reporting one underlying fact produce one normalized fact
  with multiple supporting source/provenance references. Corroboration does
  not multiply the fact value or award a source-count score bonus.
- Different periods, scopes, programs, and metric types must not be blindly
  averaged or substituted for one another.
- Unverifiable claims do not become negative facts. Conflicting facts are
  preserved; do not arbitrarily select one. An unresolved material conflict
  leaves the fact unresolved and excludes it from deterministic scoring.
- Explicitly distinct quantities remain distinct: paid-up capital is not
  valuation; revenue is not valuation or funding; highest package is not
  average package or median salary.
- No scoring code may scrape or infer facts directly from raw search text.

### 4.5 Evidence-state semantics still requiring resolution

The supplied policy describes `SUFFICIENT`, `INSUFFICIENT`, and `UNAVAILABLE`
as evidence states, and separately requires the four dimension evaluation
states. It does not specify the complete conversion table. At minimum,
`INSUFFICIENT` evidence cannot yield a score; absence of qualifying evidence
must not yield zero. The exact distinction between `INSUFFICIENT` and
`UNAVAILABLE`, and their mapping to `INSUFFICIENT_EVIDENCE` versus
`NOT_APPLICABLE`, requires approval. No current company/college dimension is
approved as not applicable by default.

### 4.6 Remaining common policy questions

The following remain **UNSPECIFIED — REQUIRES APPROVAL**:

- how the proposed fact-identity tuple is normalized (including metric/value,
  unit, period, and scope canonicalization);
- how independent sources are distinguished from copied/syndicated sources;
- what makes a source credible enough to admit a fact, and how source
  authority is considered in conflict resolution. This is an eligibility/
  precedence rule, not an approved score weight;
- which recency/validity policy selects the latest valid fact for each
  dimension, without a universal score multiplier;
- how a fact is considered attributable to the entity when evidence text is
  ambiguous after the existing entity-validation stage;
- the exact conditions that constitute a material conflict;
- conflict behavior for different periods, methodologies, units, currencies,
  populations, and minor numerical discrepancies;
- whether any disputed fact can be excluded while other facts still score the
  dimension, or whether it makes the whole dimension `CONFLICTED`;
- any conversion from extracted text to a typed fact.

Until these decisions are approved, no implementation may resolve them using
heuristics, general knowledge, or LLM judgment.

## 5. Dimension rubrics

For all dimensions below, the listed fact families are accepted fact types for
normalization, as supplied by the policy owner. Acceptance as a fact type does
not itself make a fact scoreable. A fact becomes scoreable only when required
fields, qualifying conditions, and an exact score/band mapping are defined.
Mappings not shown as approved below read:

```text
fact/condition → score: UNSPECIFIED — REQUIRES APPROVAL
```

### 5.1 Company: `financial_valuation`

**Owner-approved fact families:** funding, funding rounds/amounts, valuation,
revenue, profit/loss where available, paid-up capital, authorized capital,
investors, and other explicitly configured financial metrics.

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

**Owner-approved fact families:** customers and enterprise customers, customer
counts/reach, revenue/customer evidence, market share, products, market
presence, adoption, partnerships, competitors, industry position, and
geographic presence.

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

**Owner-approved fact families:** technology/platform, engineering
capabilities, AI/security technology, R&D, patents, technical publications,
technical products, technical architecture, and engineering capability
evidence.

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

**Owner-approved fact families:** ISO 27001, SOC 2, GDPR, HIPAA, configured
compliance/security certifications, regulatory approvals/findings, audits,
credible reputation signals, and other explicitly configured credentials.

For certifications preserve certification, status, scope, validity, issuer,
and source/provenance. A generic security statement is not proof of a
certification. Exact source-credibility rules and status-to-score mappings
remain unresolved.

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

**Owner-approved systems:** NIRF, QS, and THE. Preserve system, category, rank,
year/edition, and source/provenance. Mappings are system/category-specific;
cross-system normalization is prohibited.

**Non-scoreable by themselves under current approval:** an unlabelled rank,
ranking-system mention, ranking query membership, or ranking evidence lacking
the system/edition needed to interpret it.

**Potentially required fields:** ranking publisher/system, institution/category
scope, rank, edition/year, and any methodology/category stated by the ranking
source.

**Unapproved NIRF example mapping (reference only; not executable):**

| Rank/fact | Score |
|---|---:|
| 1–10 | 100.00 |
| 11–25 | 95.00 |
| 26–50 | 90.00 |
| 51–100 | 80.00 |
| 101–150 | 70.00 |
| 151–200 | 60.00 |
| Greater than 200 | 50.00 |
| Explicitly reported “not ranked” | 0.00 |

This table was supplied as an example only. It is not an approved production
mapping, implementation rule, or golden-test oracle. The policy owner must
confirm which NIRF categories it applies to, the qualifying evidence/source
conditions, and how category/year are established. No QS or THE mapping was
supplied. Ranking evidence without an approved system/category mapping is
preserved without a dimension score.

**Multiple facts/conflicts:** combining systems, categories, or editions and
resolving changed ranks across editions are `UNSPECIFIED — REQUIRES APPROVAL`.

### 5.6 College: `accreditation`

**Owner-approved fact families:** NAAC, NBA, UGC recognition, AICTE
approval/recognition where applicable, Institute of National Importance, and
other explicitly configured statutory recognition. Preserve type, status,
validity/current period when available, institution/program scope, and
source/provenance. General reputation statements are not accreditation facts.

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

**Owner-approved fact families:** publications, citations, patents, research
projects, research funding, faculty research recognition, and research
labs/centres. Preserve metric, value, unit, period/year, scope, and
source/provenance for quantitative facts. An individual's publication or
patent does not automatically become an institutional metric.

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

**Owner-approved fact families:** placement rate, median salary, average
salary, number of offers, number of recruiters, PPOs, and placement-period
outcomes. Preserve metric, value, unit, placement/academic year,
program/category, and source/provenance. Highest package, average package, and
median salary remain distinct metrics; no substitution is allowed.

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

**Owner-approved fact families:** campus infrastructure, hostels,
laboratories/facilities, student ecosystem/life, alumni evidence, and
institutional reputation evidence. Official institutional information can
establish existence of a facility; existence alone does not define its quality
score. Arbitrary reviews/opinions do not automatically become deterministic
quality scores.

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

Evidence state definitions approved by the policy owner:

- `SUFFICIENT`: target entity is identified; a recognized fact type exists;
  required fields are present; the source is credible enough for that fact;
  and required temporal/scope information is available where applicable.
- `INSUFFICIENT`: relevant evidence exists, but required information is
  incomplete.
- `UNAVAILABLE`: no qualifying evidence was found after the configured
  research queries.

The following dimension evaluation states are also approved:

- `INSUFFICIENT_EVIDENCE`: a non-score state; exact conversion from the three
  evidence states, including `UNAVAILABLE`, is `UNSPECIFIED — REQUIRES
  APPROVAL`.
- `CONFLICTED`: approved state exists, but what constitutes a material conflict
  and whether it blocks the entire dimension are
  `UNSPECIFIED — REQUIRES APPROVAL`.
- `SCORED`: requires at least one approved fact-to-score rule to apply. No such
  complete dimension rule is currently approved. The supplied NIRF example is
  partial until its category and evidence conditions are confirmed.
- `NOT_APPLICABLE`: supported state, reserved for future applicability rules;
  the applicability rules are `UNSPECIFIED — REQUIRES APPROVAL`.

Unverifiable or incomparable observations must remain available for audit and
must not be converted to favorable or unfavorable numeric evidence. Their
dimension-state conversion and treatment alongside otherwise scoreable facts
remain unresolved.

## 7. Overall rank

**Approved emission condition:** calculate a rank only if all applicable
dimensions are `SCORED`; otherwise `overall_rank = None`. No partial rank is
allowed.

**Approved aggregation formulae:**

College:

```text
overall_rank =
    official_ranking          * Decimal("0.25")
  + accreditation             * Decimal("0.15")
  + academic_research         * Decimal("0.25")
  + placements                * Decimal("0.25")
  + perception_infrastructure * Decimal("0.10")
```

Company:

```text
overall_rank =
    financial_valuation   * Decimal("0.25")
  + market_position       * Decimal("0.30")
  + engineering_technical * Decimal("0.25")
  + reputation_compliance * Decimal("0.20")
```

Weights total `Decimal("1.00")` for each entity type. Calculate in Decimal,
keep full intermediate precision, and round the final output once using
`ROUND_HALF_UP` to two decimal places. A dimension value of `0.00` contributes
zero; `100.00` contributes its full configured weight. Since all applicable
dimensions must be scored, missing/non-score states prevent the overall
calculation rather than being substituted with zero. No tie-breaking policy is
needed for this numeric aggregate; equal overall scores remain equal scores.

## 8. Future configuration/versioning requirements

After rubric decisions are approved, a future versioned configuration should
contain at least:

```text
rubric_id: "research_scoring_v1"
rubric_version: "1.0.0" (proposed; not frozen)
effective_date: REQUIRES HUMAN APPROVAL
dimension_definitions: all nine dimensions
fact_types: approved typed facts per dimension
required_fields: approved requirements per fact type
score_mappings: exact conditions and score/band outputs
fact_aggregation_rules: approved duplicate/multiple-fact behavior
conflict_rules: approved materiality and resulting state
missing_evidence_rules: approved sufficiency conditions
overall_aggregation: approved entity-specific weights/formula, precision,
  and rounding
```

The repository has versioned configuration patterns for candidate scoring,
but no research scoring configuration convention. This document is placed in
`docs/specifications/` as the smallest standalone specification artifact; it
does not introduce a runtime configuration architecture.

## 9. Remaining approval blockers — implementation remains blocked

Before freezing `research_scoring_v1` as authoritative, approval is required
for:

1. Fact-to-score mappings and dimension-specific sufficiency for
   `financial_valuation`, `market_position`, `engineering_technical`,
   `reputation_compliance`, `accreditation`, `academic_research`, `placements`,
   and `perception_infrastructure`.
2. Confirm NIRF rank table scope (which categories and applicable editions),
   plus its evidence source and explicit `not ranked` condition. No QS/THE
   mapping is provided.
3. Source credibility/admissibility criteria and deterministic authority
   precedence for conflict handling; source quality may not be a numeric
   weight.
4. Recency/validity policy for selecting the latest valid fact by dimension;
   no universal recency multiplier is allowed.
5. Exact evidence-state conversion, especially `UNAVAILABLE` versus
   `INSUFFICIENT`, and whether either can ever mean `NOT_APPLICABLE`.
6. Deterministic fact normalization/canonicalization and duplicate identity
   over the supplied tuple: entity, dimension, fact type, normalized metric,
   normalized value, unit, period, and scope.
7. Definition of independent/corroborating sources. Corroboration does not
   change fact value or directly award score; its role in evidence sufficiency
   is unresolved.
8. Dimension-specific handling of different periods, scopes, programs,
   currencies, units, methodologies, and incomparable facts.
9. Material-conflict criteria and when a fact becomes unresolved; whether
   unresolved facts make a whole dimension `CONFLICTED` or can be excluded
   while other facts still score.
10. Operational criteria for `SUFFICIENT`, `INSUFFICIENT`, and `UNAVAILABLE`,
    including “credible enough” source admissibility.
11. The public output shape for dimensions that are non-scored: the illustrative
    output shows numeric values only, while approved states require non-score
    representation and the overall may be null.
12. Effective date and confirmation/finalization of version `1.0.0`.

No executable scoring tests should encode numeric answers until the associated
rules are approved. Once approved, known-answer tests should cover every
approved band, boundary, missing/conflict state, aggregation case, and overall
rank condition.

### 9.1 Deterministic examples currently derivable

The supplied NIRF example table suggests these illustrative outcomes only.
They are not approved expected scores and must not be encoded in production or
golden tests before category scope and evidence conditions are approved:

| Input fact | Expected score | Notes |
|---|---:|---|
| NIRF rank 1, within an approved category/edition | 100.00 | Top supplied band |
| NIRF rank 75, within an approved category/edition | 80.00 | Middle supplied band |
| NIRF rank 201, within an approved category/edition | 50.00 | `>200` supplied band |
| Explicit “not ranked” fact | 0.00 | Only if the required category/edition and fact are established |

There is no approved positive-score or conflict example for the other eight
dimensions, nor a general known-answer example for duplicates/conflicts. Adding
such scores now would invent business policy.

## 10. Isolation and implementation constraints

Future implementation must remain in the research boundary and must not import
candidate scoring, policy, eligibility, seniority, or graph behavior into
research scoring. Candidate scoring must not import research scoring. Reports
and UI may display authoritative research results but may not recalculate them.

There is no scoring implementation in this milestone. No unapproved
thresholds, fact mappings, conflict heuristics, ranking conversions, or
additional overall-rank rules have been selected by implication. The
company/college aggregate weights and formula above were explicitly supplied
earlier; they do not unblock dimension scoring. All remaining blockers still
prevent implementation.
