from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Protocol

from groq import Groq

from vikat_hire.config.models import (
    AIModelConfiguration,
    AIRuntimeConfiguration,
)
from vikat_hire.contracts.explanation import (
    DimensionExplanation,
    ExplanationContext,
    ExplanationResult,
)


class GroqControllerError(ValueError):
    """Raised when Groq explanation generation cannot produce a valid result."""


class GroqCompletionClient(Protocol):
    """Minimal client contract required by GroqController."""

    def chat(self, *args: Any, **kwargs: Any) -> Any:
        ...


class GroqController:
    """
    Groq-backed implementation of the provider-neutral explanation contract.

    Groq is responsible only for proposing explanatory content. Authoritative
    identifiers, timestamps, provider metadata, and validated application
    contracts are constructed locally.
    """

    _SUPPORTED_PROVIDER = "groq"

    def __init__(
        self,
        *,
        api_key: str,
        model_configuration: AIModelConfiguration,
        runtime_configuration: AIRuntimeConfiguration,
        client: Any | None = None,
    ) -> None:
        if not api_key.strip():
            raise GroqControllerError("api_key must not be blank")

        if model_configuration.provider != self._SUPPORTED_PROVIDER:
            raise GroqControllerError(
                "GroqController requires provider 'groq'; "
                f"got {model_configuration.provider!r}"
            )

        self._api_key = api_key
        self._model_configuration = model_configuration
        self._runtime_configuration = runtime_configuration
        self._client = client if client is not None else Groq(api_key=api_key)

    def __call__(
        self,
        context: ExplanationContext,
    ) -> ExplanationResult:
        if not isinstance(context, ExplanationContext):
            raise GroqControllerError(
                "context must be an ExplanationContext"
            )

        response = self._request_completion(context)
        payload = self._extract_json_payload(response)

        return self._build_result(
            context=context,
            payload=payload,
        )

    def _request_completion(
        self,
        context: ExplanationContext,
    ) -> Any:
        messages = [
            {
                "role": "system",
                "content": self._system_prompt(),
            },
            {
                "role": "user",
                "content": self._build_context_payload(context),
            },
        ]

        request: dict[str, Any] = {
            "model": self._model_configuration.model,
            "messages": messages,
            "temperature": float(self._runtime_configuration.temperature),
            "max_tokens": self._runtime_configuration.max_tokens,
        }

        if self._runtime_configuration.structured_output:
            request["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "explanation_proposal",
                    "strict": True,
                    "schema": self._response_schema(),
                },
            }

        try:
            return self._client.chat.completions.create(**request)
        except Exception as exc:
            raise GroqControllerError(
                "Groq explanation generation failed"
            ) from exc

    @staticmethod
    def _system_prompt() -> str:
        return (
            "Generate a recruiter-facing explanation from the supplied "
            "authoritative screening artifacts. "
            "You may summarize strengths, gaps, review items, and dimension "
            "explanations. "
            "Do not calculate, change, infer, or replace scores, evaluations, "
            "policy, eligibility, provenance, identifiers, or timestamps. "
            "Use only supplied evidence and references. "
            "Return JSON matching the requested schema."
        )

    @staticmethod
    def _build_context_payload(
        context: ExplanationContext,
    ) -> str:
        dimensions = []

        for dimension in context.evaluation.dimensions:
            dimensions.append(
                {
                    "dimension": dimension.dimension.value,
                    "status": dimension.status.value,
                    "raw_score": (
                        str(dimension.raw_score)
                        if dimension.raw_score is not None
                        else None
                    ),
                    "reason": dimension.reason,
                    "evidence_refs": list(dimension.evidence_refs),
                    "requirement_refs": list(dimension.requirement_refs),
                    "provenance_refs": list(dimension.provenance_refs),
                    "evaluation_ref": dimension.evaluation_ref,
                }
            )

        payload = {
            "screening_id": context.screening_id,
            "evaluation": {
                "dimensions": dimensions,
            },
            "score": (
                {
                    "score": str(context.score.score),
                    "release": context.score.release,
                }
                if context.score is not None
                else None
            ),
            "policy": (
                {
                    "status": context.policy.status.value,
                    "eligible": context.policy.eligible,
                    "review_required": context.policy.review_required,
                    "review_reasons": [
                        review.reason.value
                        for review in context.policy.review_requests
                    ],
                }
                if context.policy is not None
                else None
            ),
        }

        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _response_schema() -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "summary",
                "strengths",
                "gaps",
                "review_items",
                "dimensions",
            ],
            "properties": {
                "summary": {
                    "type": "string",
                },
                "strengths": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "gaps": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "review_items": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "dimensions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "dimension",
                            "summary",
                            "strengths",
                            "gaps",
                            "evidence_refs",
                            "requirement_refs",
                            "provenance_refs",
                            "evaluation_ref",
                        ],
                        "properties": {
                            "dimension": {
                                "type": "string",
                            },
                            "summary": {
                                "type": "string",
                            },
                            "strengths": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "gaps": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "evidence_refs": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "requirement_refs": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "provenance_refs": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "evaluation_ref": {
                                "type": ["string", "null"],
                            },
                        },
                    },
                },
            },
        }

    @staticmethod
    def _extract_json_payload(
        response: Any,
    ) -> Mapping[str, Any]:
        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError, TypeError) as exc:
            raise GroqControllerError(
                "Groq response does not contain message content"
            ) from exc

        if not isinstance(content, str) or not content.strip():
            raise GroqControllerError(
                "Groq response content must be a non-empty JSON string"
            )

        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise GroqControllerError(
                "Groq response content is not valid JSON"
            ) from exc

        if not isinstance(payload, Mapping):
            raise GroqControllerError(
                "Groq response JSON must be an object"
            )

        return payload

    def _build_result(
        self,
        *,
        context: ExplanationContext,
        payload: Mapping[str, Any],
    ) -> ExplanationResult:
        self._validate_top_level_payload(payload)

        dimensions_payload = payload["dimensions"]

        if not isinstance(dimensions_payload, list):
            raise GroqControllerError(
                "Groq explanation dimensions must be an array"
            )

        expected_dimensions = {
            dimension.dimension
            for dimension in context.evaluation.dimensions
        }

        returned_dimensions: set[Any] = set()
        dimensions: list[DimensionExplanation] = []

        for item in dimensions_payload:
            if not isinstance(item, Mapping):
                raise GroqControllerError(
                    "each Groq dimension explanation must be an object"
                )

            dimension = self._parse_dimension(
                context=context,
                payload=item,
            )

            if dimension.dimension in returned_dimensions:
                raise GroqControllerError(
                    f"duplicate dimension explanation: "
                    f"{dimension.dimension.value}"
                )

            returned_dimensions.add(dimension.dimension)
            dimensions.append(dimension)

        if returned_dimensions != expected_dimensions:
            missing = expected_dimensions - returned_dimensions
            unexpected = returned_dimensions - expected_dimensions

            details = []

            if missing:
                details.append(
                    "missing: "
                    + ", ".join(
                        sorted(dimension.value for dimension in missing)
                    )
                )

            if unexpected:
                details.append(
                    "unexpected: "
                    + ", ".join(
                        sorted(dimension.value for dimension in unexpected)
                    )
                )

            raise GroqControllerError(
                "Groq dimension explanations do not match evaluation: "
                + "; ".join(details)
            )

        return ExplanationResult(
            screening_id=context.screening_id,
            summary=payload["summary"],
            strengths=tuple(payload["strengths"]),
            gaps=tuple(payload["gaps"]),
            review_items=tuple(payload["review_items"]),
            dimensions=tuple(
                sorted(
                    dimensions,
                    key=lambda item: item.dimension.value,
                )
            ),
            evidence_refs=self._collect_evidence_refs(dimensions),
            policy_refs=self._policy_refs(context),
            evaluation_refs=tuple(
                dimension.evaluation_ref
                for dimension in dimensions
                if dimension.evaluation_ref is not None
            ),
            generated_by=self._model_configuration.provider,
            model_config_ref=self._model_configuration.model_config_ref,
        )

    @staticmethod
    def _validate_top_level_payload(
        payload: Mapping[str, Any],
    ) -> None:
        required = {
            "summary",
            "strengths",
            "gaps",
            "review_items",
            "dimensions",
        }

        missing = required - set(payload)

        if missing:
            raise GroqControllerError(
                "Groq response is missing required fields: "
                + ", ".join(sorted(missing))
            )

        for field in (
            "summary",
            "strengths",
            "gaps",
            "review_items",
        ):
            value = payload[field]

            if field == "summary":
                if not isinstance(value, str) or not value.strip():
                    raise GroqControllerError(
                        "Groq explanation summary must not be blank"
                    )
            elif (
                not isinstance(value, list)
                or any(
                    not isinstance(item, str) or not item.strip()
                    for item in value
                )
            ):
                raise GroqControllerError(
                    f"Groq explanation field {field!r} must contain "
                    "non-blank strings"
                )

    @classmethod
    def _parse_dimension(
        cls,
        *,
        context: ExplanationContext,
        payload: Mapping[str, Any],
    ) -> DimensionExplanation:
        required = {
            "dimension",
            "summary",
            "strengths",
            "gaps",
            "evidence_refs",
            "requirement_refs",
            "provenance_refs",
            "evaluation_ref",
        }

        missing = required - set(payload)

        if missing:
            raise GroqControllerError(
                "Groq dimension explanation is missing fields: "
                + ", ".join(sorted(missing))
            )

        try:
            dimension = next(
                item.dimension
                for item in context.evaluation.dimensions
                if item.dimension.value == payload["dimension"]
            )
        except StopIteration as exc:
            raise GroqControllerError(
                f"Groq returned unknown dimension: {payload['dimension']!r}"
            ) from exc

        cls._validate_string_field(
            payload["summary"],
            "dimension summary",
        )

        for field in (
            "strengths",
            "gaps",
            "evidence_refs",
            "requirement_refs",
            "provenance_refs",
        ):
            cls._validate_string_list(
                payload[field],
                field,
            )

        evaluation = next(
            item
            for item in context.evaluation.dimensions
            if item.dimension == dimension
        )

        allowed_evidence_refs = set(evaluation.evidence_refs)
        allowed_requirement_refs = set(evaluation.requirement_refs)
        allowed_provenance_refs = set(evaluation.provenance_refs)

        cls._validate_refs(
            payload["evidence_refs"],
            allowed_evidence_refs,
            "evidence_refs",
        )
        cls._validate_refs(
            payload["requirement_refs"],
            allowed_requirement_refs,
            "requirement_refs",
        )
        cls._validate_refs(
            payload["provenance_refs"],
            allowed_provenance_refs,
            "provenance_refs",
        )

        evaluation_ref = payload["evaluation_ref"]

        if evaluation_ref is not None:
            if not isinstance(evaluation_ref, str) or not evaluation_ref.strip():
                raise GroqControllerError(
                    "evaluation_ref must be null or a non-blank string"
                )

            if evaluation.evaluation_ref != evaluation_ref:
                raise GroqControllerError(
                    f"invalid evaluation_ref for {dimension.value}"
                )

        return DimensionExplanation(
            dimension=dimension,
            summary=payload["summary"],
            strengths=tuple(payload["strengths"]),
            gaps=tuple(payload["gaps"]),
            evidence_refs=tuple(payload["evidence_refs"]),
            requirement_refs=tuple(payload["requirement_refs"]),
            provenance_refs=tuple(payload["provenance_refs"]),
            evaluation_ref=evaluation_ref,
        )

    @staticmethod
    def _validate_string_field(
        value: Any,
        field_name: str,
    ) -> None:
        if not isinstance(value, str) or not value.strip():
            raise GroqControllerError(
                f"{field_name} must be a non-blank string"
            )

    @staticmethod
    def _validate_string_list(
        value: Any,
        field_name: str,
    ) -> None:
        if not isinstance(value, list):
            raise GroqControllerError(
                f"{field_name} must be an array"
            )

        if any(
            not isinstance(item, str) or not item.strip()
            for item in value
        ):
            raise GroqControllerError(
                f"{field_name} must contain only non-blank strings"
            )

    @staticmethod
    def _validate_refs(
        refs: list[Any],
        allowed_refs: set[str],
        field_name: str,
    ) -> None:
        invalid = set(refs) - allowed_refs

        if invalid:
            raise GroqControllerError(
                f"Groq returned unauthorized {field_name}: "
                + ", ".join(sorted(invalid))
            )

    @staticmethod
    def _collect_evidence_refs(
        dimensions: list[DimensionExplanation],
    ) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    reference
                    for dimension in dimensions
                    for reference in dimension.evidence_refs
                }
            )
        )

    @staticmethod
    def _policy_refs(
        context: ExplanationContext,
    ) -> tuple[str, ...]:
        if context.policy is None:
            return ()

        return tuple(
            review.review_id
            for review in context.policy.review_requests
        )