from vikat_hire.contracts import (
    AccessStatus,
    DerivationMethod,
    Evidence,
    EvidenceConfidence,
    EvidenceStatus,
    SourceReliability,
)


def test_missing_evidence_is_explicitly_non_negative() -> None:
    evidence = Evidence(
        status=EvidenceStatus.NOT_FOUND,
        content={"query": "Python"},
        provenance_refs=("prov-1",),
        confidence=EvidenceConfidence.LOW,
        source_reliability=SourceReliability.REPUTABLE_SECONDARY,
        supports_claim=False,
    )

    assert evidence.status is EvidenceStatus.NOT_FOUND
    assert evidence.supports_claim is False


def test_not_authorized_is_distinct_from_not_found() -> None:
    not_found = Evidence(
        status=EvidenceStatus.NOT_FOUND,
        content={"source": "github"},
        provenance_refs=("prov-1",),
        confidence=EvidenceConfidence.LOW,
        source_reliability=SourceReliability.REPUTABLE_SECONDARY,
        supports_claim=False,
    )

    not_authorized = Evidence(
        status=EvidenceStatus.NOT_AUTHORIZED,
        content={"source": "linkedin"},
        provenance_refs=("prov-2",),
        confidence=EvidenceConfidence.LOW,
        source_reliability=SourceReliability.REPUTABLE_SECONDARY,
        supports_claim=False,
    )

    assert not_found.status != not_authorized.status