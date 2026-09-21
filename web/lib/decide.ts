import type { Category } from "@/lib/types";

export type Thresholds = {
  phishing_category_confidence: number;
  phishing_credential_request: number;
  phishing_brand_impersonation: number;
  spam_is_spam: number;
  spam_category_confidence: number;
  promotional_action: number;
  uncertain_floor: number;
  needs_reply_label: number;
};

export type DecideInput = {
  jev_category: string;
  category_confidence: number;
  spam_probability: number;
  credential_request: number;
  brand_impersonation: number;
};

export type Decision = {
  category: Category;
  spam: boolean;
  decision_path: string;
  may_auto_label: boolean;
};

const CATS = new Set(["spam", "phishing", "promotional", "legitimate", "other"]);

export function decide(answers: DecideInput, t: Thresholds): Decision {
  let raw = CATS.has(answers.jev_category) ? answers.jev_category : "other";
  const confidence = answers.category_confidence;

  if (confidence < t.uncertain_floor) {
    return {
      category: "uncertain",
      spam: answers.spam_probability > t.spam_is_spam,
      decision_path: "uncertain_floor",
      may_auto_label: false,
    };
  }

  if (raw === "phishing" && confidence > t.phishing_category_confidence) {
    return {
      category: "phishing",
      spam: true,
      decision_path: "category_phishing",
      may_auto_label: true,
    };
  }

  if (
    answers.credential_request > t.phishing_credential_request &&
    answers.brand_impersonation > t.phishing_brand_impersonation
  ) {
    return {
      category: "phishing",
      spam: true,
      decision_path: "credential_and_impersonation",
      may_auto_label: true,
    };
  }

  let spam = false;
  let path = `category_${raw}`;
  if (answers.spam_probability > t.spam_is_spam) {
    spam = true;
    path = raw !== "spam" ? "is_spam_noul" : "category_spam+is_spam_noul";
  } else if ((raw === "spam" || raw === "phishing") && confidence > t.spam_category_confidence) {
    spam = true;
    path = raw === "spam" ? "category_spam" : "category_phishing";
  }

  let mayLabel = true;
  if (raw === "promotional" && confidence < t.promotional_action) {
    mayLabel = false;
  }

  return {
    category: raw as Category,
    spam,
    decision_path: path,
    may_auto_label: mayLabel,
  };
}

export function wouldReply(replyProbability: number, t: Thresholds): boolean {
  return replyProbability >= t.needs_reply_label;
}
