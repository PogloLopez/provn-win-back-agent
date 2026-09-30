import type {
  CardData,
  EditOptions,
  FeedbackResult,
  ProposedOffer,
  RejectReason,
  Violation,
} from "@/lib/types";

// Same-origin in production; next.config.ts rewrites /api to FastAPI in development.
const API = process.env.NEXT_PUBLIC_API_BASE ?? "";

/** A guardrail or validation refusal, carrying what the marketer needs to fix. */
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public violations: Violation[] = [],
  ) {
    super(message);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const violations: Violation[] = body.violations ?? [];
    const detail =
      violations.map((v) => v.message).join("; ") ||
      (typeof body.detail === "string" ? body.detail : "Request failed");
    throw new ApiError(detail, response.status, violations);
  }
  return body as T;
}

const post = <T>(path: string, body?: unknown) =>
  call<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  startRun: () => post<{ run_id: string; total: number }>("/api/runs"),
  options: (id: number) => call<EditOptions>(`/api/cards/${id}/options`),
  approve: (id: number) => post<CardData>(`/api/cards/${id}/approve`),
  reject: (id: number, reason: RejectReason) =>
    post<CardData>(`/api/cards/${id}/reject`, { reason }),
  edit: (id: number, change: { offers?: ProposedOffer[]; subject?: string; body?: string }) =>
    post<CardData>(`/api/cards/${id}/edit`, change),
  feedback: (id: number, text: string) =>
    post<FeedbackResult>(`/api/cards/${id}/feedback`, { text }),
};

/** Stream a run's cards. Returns a function that closes the stream. */
export function streamRun(
  runId: string,
  handlers: {
    onCard: (card: CardData) => void;
    onDone: (telemetryFailures: number) => void;
    onFailure: (detail: string) => void;
  },
): () => void {
  const source = new EventSource(`${API}/api/runs/${runId}/stream`);
  const close = () => source.close(); // never let EventSource auto-reconnect a finished run
  source.addEventListener("card", (e) => handlers.onCard(JSON.parse((e as MessageEvent).data)));
  source.addEventListener("done", (e) => {
    close();
    handlers.onDone(JSON.parse((e as MessageEvent).data).telemetry_failures ?? 0);
  });
  source.addEventListener("run_failed", (e) => {
    close();
    handlers.onFailure(JSON.parse((e as MessageEvent).data).detail);
  });
  source.onerror = () => {
    close();
    handlers.onFailure("Lost connection to the server.");
  };
  return close;
}
