export type GateStatusPresentation = {
  label: string;
  className: "positive" | "negative" | "neutral";
};

export function gateStatusPresentation(status: string): GateStatusPresentation;

export function eligibilityPresentation(
  isEligible: boolean,
  hasBlockingReview: boolean,
): GateStatusPresentation;
