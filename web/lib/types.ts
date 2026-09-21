export type Category =
  | "spam"
  | "phishing"
  | "promotional"
  | "legitimate"
  | "other"
  | "uncertain";

export type UpdateResult = {
  ingest_ok: boolean;
  ingested_new: number;
  ingested_updated: number;
  ingested_fetched: number;
  ingest_complete: boolean;
  classified: number;
  classify_failed: number;
  unclassified_remaining: number;
};

export type CompactMessage = {
  id: number;
  message_id: string;
  classified_at: string;
  category: Category;
  category_confidence: number;
  spam: boolean;
  spam_probability: number;
  reply_probability: number;
  total_ms: number;
  jev_ms: number;
  cost_usd: number;
  sender_domain: string;
  subject: string;
  gmail_spam: boolean;
  disagreed_with_gmail: boolean;
  decision_path: string;
  model_version: string;
  retries: number;
  rate_limited: boolean;
  jev_category: string;
  credential_request: number;
  brand_impersonation: number;
};

export type SpanNode = {
  name: string;
  duration_ms: number;
  offset_ms?: number;
  pct_of_total?: number;
  retries?: number;
  rate_limited?: boolean;
  attributes?: Record<string, string | number | boolean>;
  children?: SpanNode[];
};

export type QuestionCard = {
  name: string;
  type: "Choice" | "Noul" | "Score" | string;
  instructions?: string;
  criteria?: Record<string, string> | string[];
  answer?: {
    choice?: string;
    confidence?: number;
    probabilities?: Record<string, number>;
    noul?: number;
    score?: number;
  };
};

export type DecisionStep = {
  id: string;
  label: string;
  matched: boolean;
};

export type MessageDetail = {
  result: {
    message_id: string;
    category: Category;
    category_confidence: number;
    category_probabilities: Record<string, number>;
    spam: boolean;
    spam_probability: number;
    reply_probability: number;
    signals: {
      credential_request: number;
      brand_impersonation: number;
      pressure_score: number;
    };
    classification_time_ms: {
      total: number;
      gmail_fetch: number;
      parse: number;
      state_build: number;
      jev_call: number;
      decision: number;
    };
    observability: {
      request_id: string;
      trace_id: string;
      model_version: string;
      input_tokens: number;
      input_tokens_estimated: boolean;
      cost_usd: number;
      state_size_chars: number;
      body_truncated: boolean;
      retries: number;
      rate_limited: boolean;
      thresholds_applied: {
        spam: number;
        phishing: number;
        uncertain_floor: number;
      };
      decision_path: string;
      timestamp: string;
    };
  };
  explanation: string;
  decision_trail: DecisionStep[];
  state: Record<string, unknown>;
  state_size_chars: number;
  body_truncated: boolean;
  questions: QuestionCard[];
  spans: SpanNode;
  gmail_spam: boolean;
  from_header: string | null;
  subject: string | null;
};

export type Pct = { "50": number; "95": number; "99": number };

export type StatsSeriesPoint = {
  bucket: string;
  n: number;
  counts: Record<string, number>;
  latency_total: Pct;
  latency_jev: Pct;
  cost_usd: number;
  cost_usd_cumulative: number;
  input_tokens: number;
  uncertain_n: number;
  uncertain_rate: number;
  errors: number;
  rate_limited: number;
  retries: number;
  gmail_agreement: number;
};

export type StatsResponse = {
  n: number;
  counts_by_category: Record<string, number>;
  latency: { total: Pct; jev_call: Pct };
  latency_histogram: { lo: number; hi: number | null; n: number; label: string }[];
  cost_usd_total: number;
  cost_usd_per_email: number;
  cost_usd_per_1000: number;
  projected_cost_usd: { emails_10000: number; emails_100000: number };
  input_tokens_total: number;
  confidence_histogram: { lo: number; hi: number; n: number }[];
  uncertain_rate: number;
  errors: number;
  rate_limited: number;
  retries: number;
  gmail_agreement: number;
  volume: { bucket: string; counts: Record<string, number> }[];
  series: StatsSeriesPoint[];
};

export type CalibrationBin = {
  lo: number;
  hi: number;
  n: number;
  mean_predicted: number;
  actual_rate: number;
};

export type CalibrationResponse = {
  spam: CalibrationBin[];
  reply: CalibrationBin[];
};

