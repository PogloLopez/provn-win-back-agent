// Shapes returned by the FastAPI backend (src/winback/review.py `_view`).

export type CartStatus = "skipped" | "deferred" | "ready" | "needs_attention" | "failed";
export type Review = "pending" | "approved" | "rejected";
export type RejectReason = "too_generous" | "wrong_tone" | "should_not_contact" | "other";

export interface Cart {
  cart_id: string;
  fan_id: string;
  seats: number;
  section: string;
  cart_value: number;
  hours_since_abandon: number;
  lifetime_tickets: number;
  days_since_last_purchase: number | null;
  email_opt_in: boolean;
}

export interface Triage {
  cart_id: string;
  outcome: "SKIP" | "DEFER" | "CAUTION" | "ELIGIBLE";
  reason_codes: string[];
  segment: string;
  contact_stage: string;
  caution_score: number;
}

export interface Violation {
  code: string;
  message: string;
  severity: "block" | "warn";
}

export interface Attempt {
  raw: string;
  violations: Violation[];
}

export interface ProposedOffer {
  type: string;
  value: number;
}

export interface Proposal {
  cart_id: string;
  decision: "offer" | "reminder_only" | "no_offer";
  offers: ProposedOffer[];
  reason: string;
  reason_codes_cited: string[];
  confidence: number;
}

export interface OfferResult {
  status: "ok" | "needs_attention";
  proposal: Proposal;
  warnings: Violation[];
  attempts: Attempt[];
}

export interface Draft {
  subject: string;
  body: string;
}

export interface CopyResult {
  status: "ok" | "needs_attention";
  draft: Draft;
  email: Draft;
  warnings: Violation[];
  attempts: Attempt[];
}

export interface CardData {
  id: number;
  run_id: string;
  cart_id: string;
  review: Review;
  reject_reason: RejectReason | null;
  cart: Cart;
  triage: Triage;
  status: CartStatus;
  offer: OfferResult | null;
  email: CopyResult | null;
  error: string | null;
}

export interface MenuOption {
  type: string;
  value: number;
  unit: "percent" | "seats" | "flag";
  description: string;
  cost_usd: number;
  conversion_rate: number;
  expected_value_usd: number;
}

export interface EditOptions {
  menu: MenuOption[];
  max_offers: number;
  total_cost_cap_usd: number;
  values: Record<string, string>;
  phrases: Record<string, Record<string, string>>;
}

export interface FeedbackAnalysis {
  feedback_category: string;
  target_component: string;
  severity: "low" | "medium" | "high";
  summary: string;
  instruction: string;
}

export interface FeedbackResult {
  card: CardData;
  analysis: FeedbackAnalysis | null;
  routed_to: string | null;
  note: string;
}
