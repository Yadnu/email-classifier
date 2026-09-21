import { decide, type Thresholds } from "@/lib/decide";
import { describe, expect, it } from "vitest";

const T: Thresholds = {
  phishing_category_confidence: 0.85,
  phishing_credential_request: 0.8,
  phishing_brand_impersonation: 0.8,
  spam_is_spam: 0.75,
  spam_category_confidence: 0.8,
  promotional_action: 0.6,
  uncertain_floor: 0.5,
  needs_reply_label: 0.7,
};

const base = {
  jev_category: "legitimate",
  category_confidence: 0.9,
  spam_probability: 0.1,
  credential_request: 0.1,
  brand_impersonation: 0.1,
};

describe("decide", () => {
  it("marks uncertain below the floor", () => {
    const d = decide({ ...base, jev_category: "spam", category_confidence: 0.4, spam_probability: 0.2 }, T);
    expect(d.category).toBe("uncertain");
    expect(d.spam).toBe(false);
    expect(d.decision_path).toBe("uncertain_floor");
    expect(d.may_auto_label).toBe(false);
  });

  it("still flags spam noul under uncertain", () => {
    const d = decide({ ...base, jev_category: "spam", category_confidence: 0.3, spam_probability: 0.9 }, T);
    expect(d.category).toBe("uncertain");
    expect(d.spam).toBe(true);
  });

  it("takes phishing by category above the high bar", () => {
    const d = decide({ ...base, jev_category: "phishing", category_confidence: 0.91 }, T);
    expect(d.category).toBe("phishing");
    expect(d.spam).toBe(true);
    expect(d.decision_path).toBe("category_phishing");
  });

  it("does not spam-flag phishing below both bars", () => {
    const d = decide(
      { ...base, jev_category: "phishing", category_confidence: 0.7, spam_probability: 0.1 },
      T,
    );
    expect(d.category).toBe("phishing");
    expect(d.spam).toBe(false);
  });

  it("takes phishing from paired noul signals", () => {
    const d = decide(
      { ...base, category_confidence: 0.7, credential_request: 0.9, brand_impersonation: 0.88 },
      T,
    );
    expect(d.decision_path).toBe("credential_and_impersonation");
    expect(d.spam).toBe(true);
  });

  it("takes spam from is_spam noul", () => {
    const d = decide(
      { ...base, jev_category: "promotional", category_confidence: 0.7, spam_probability: 0.9 },
      T,
    );
    expect(d.spam).toBe(true);
    expect(d.decision_path).toBe("is_spam_noul");
  });
});
