// Plain-English labels for a non-technical marketer. Codes come from config/triage_rules.yaml
// and the guardrails; unknown codes fall back to a readable version of the code itself.

const REASONS: Record<string, string> = {
  SKIP_NO_OPT_IN: "No email consent",
  SKIP_SUSPECTED_RESELLER: "Looks like a reseller (large seat count)",
  SKIP_DORMANT: "One-off fan, inactive for 2+ years",
  SKIP_OUTSIDE_WINDOW: "Cart older than 7 days",
  DEFER_TOO_RECENT: "Abandoned too recently, check again next run",
  SIGNAL_OLD_CART: "Cart is several days old",
  SIGNAL_LAPSED: "No purchase in 6+ months",
  SIGNAL_LOW_ENGAGEMENT: "Only one ticket bought before",
  SIGNAL_LARGE_FIRST_CART: "Unusually large first purchase",
};

const OFFERS: Record<string, string> = {
  discount_pct: "Discount",
  free_parking: "Free parking",
  extra_seat: "Extra seat",
  seat_upgrade: "Seat upgrade",
  early_entry: "Early entry",
};

const VIOLATIONS: Record<string, string> = {
  RAW_VALUE: "Typed a number instead of using a placeholder",
  DISCOUNT_OUT_OF_RANGE: "Discount outside the allowed range",
  OVER_COST_CAP: "Offer costs more than allowed for this fan",
  OFFER_NOT_ALLOWED: "Offer type not allowed for this fan",
  UNGROUNDED_REASON: "Reason not backed by the fan's data",
  UNGRANTED_OFFER: "Email mentions a perk that was not offered",
  SCARCITY_CLAIM: "Email made an urgency or scarcity claim",
  BANNED_TERM: "Off-brand wording",
  DOUBLED_WORD: "Sentence reads wrong once filled in",
  WORD_BEFORE_NUMBER: "Sentence reads wrong once filled in",
  MISSING_PLACEHOLDER: "Required detail missing from the email",
  UNKNOWN_PLACEHOLDER: "Email used a detail that doesn't apply",
  BAD_JSON: "AI answer was malformed",
  LLM_UNAVAILABLE: "AI service unavailable",
  MOST_EXPENSIVE_OPTION: "Chose the most expensive option available",
  TOO_LONG: "Email is longer than recommended",
};

const titleCase = (code: string) =>
  code.toLowerCase().replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

export const reasonLabel = (code: string) => REASONS[code] ?? titleCase(code);
export const offerLabel = (type: string) => OFFERS[type] ?? titleCase(type);
export const violationLabel = (code: string) => VIOLATIONS[code] ?? titleCase(code);
export const segmentLabel = (segment: string) => titleCase(segment);

/** Reason codes worth showing as "why": everything but the segment/stage context codes. */
export const whyCodes = (codes: string[]) =>
  codes.filter((c) => !c.startsWith("SEGMENT_") && !c.startsWith("STAGE_"));

export const offerSummary = (offers: { type: string; value: number }[]) =>
  offers.length === 0
    ? "Reminder only"
    : offers
        .map((o) => (o.type === "discount_pct" ? `${o.value}% off` : offerLabel(o.type)))
        .join(" + ");

export const money = (usd: number) =>
  usd.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });

export const hoursAgo = (hours: number) =>
  hours < 48 ? `${Math.round(hours)} h ago` : `${Math.round(hours / 24)} days ago`;
