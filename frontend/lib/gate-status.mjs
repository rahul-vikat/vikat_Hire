const PRESENTATION = {
  PASS: { label: "Pass", className: "positive" },
  FAIL: { label: "Fail", className: "negative" },
  NOT_APPLICABLE: { label: "Not applicable", className: "neutral" },
};

export function gateStatusPresentation(status) {
  return Object.hasOwn(PRESENTATION, status)
    ? PRESENTATION[status]
    : { label: "Unknown", className: "neutral" };
}

export function eligibilityPresentation(isEligible, hasBlockingReview) {
  if (hasBlockingReview) return { label: "Review required", className: "neutral" };
  return isEligible
    ? { label: "Eligible", className: "positive" }
    : { label: "Not eligible", className: "negative" };
}
