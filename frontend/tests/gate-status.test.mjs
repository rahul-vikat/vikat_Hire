import assert from "node:assert/strict";
import test from "node:test";

import {
  eligibilityPresentation,
  gateStatusPresentation,
} from "../lib/gate-status.mjs";

test("renders a passing gate as pass", () => {
  assert.deepEqual(gateStatusPresentation("PASS"), {
    label: "Pass",
    className: "positive",
  });
});

test("renders a failed gate as fail", () => {
  assert.deepEqual(gateStatusPresentation("FAIL"), {
    label: "Fail",
    className: "negative",
  });
});

test("renders a non-applicable gate distinctly", () => {
  assert.deepEqual(gateStatusPresentation("NOT_APPLICABLE"), {
    label: "Not applicable",
    className: "neutral",
  });
});

test("does not mislabel an unrecognized status as fail", () => {
  assert.deepEqual(gateStatusPresentation("unexpected"), {
    label: "Unknown",
    className: "neutral",
  });
});

test("does not present eligibility as final while a blocking review is pending", () => {
  assert.deepEqual(eligibilityPresentation(true, true), {
    label: "Review required",
    className: "neutral",
  });
});

test("presents final eligibility when no blocking review is pending", () => {
  assert.deepEqual(eligibilityPresentation(true, false), {
    label: "Eligible",
    className: "positive",
  });
  assert.deepEqual(eligibilityPresentation(false, false), {
    label: "Not eligible",
    className: "negative",
  });
});
