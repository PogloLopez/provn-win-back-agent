"use client";

import { AlertTriangle, CheckCircle2, ChevronDown, Loader2, Trash2 } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";

import { Badge } from "@/components/ui/badge";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { offerSummary, reasonLabel, segmentLabel, whyCodes } from "@/lib/labels";
import type { CardData } from "@/lib/types";

export function OfferQueue({
  cards,
  selectedId,
  onSelect,
  running,
  total,
}: {
  cards: CardData[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  running: boolean;
  total: number;
}) {
  const toReview = cards.filter(
    (c) => ["ready", "needs_attention", "failed"].includes(c.status) && c.review !== "rejected",
  );
  const notContacted = cards.filter((c) => c.status === "skipped" || c.status === "deferred");
  const rejected = cards.filter((c) => c.review === "rejected");

  return (
    <aside className="flex w-80 shrink-0 flex-col border-r bg-background">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <h2 className="text-sm font-semibold">Offers to review</h2>
        <span className="text-xs text-muted-foreground">
          {running ? (
            <span className="inline-flex items-center gap-1">
              <Loader2 className="size-3 animate-spin" /> {cards.length}/{total} carts
            </span>
          ) : (
            `${toReview.length} to review`
          )}
        </span>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        <ul className="flex flex-col gap-2">
          <AnimatePresence initial={false}>
            {toReview.map((card) => (
              <motion.li
                key={card.id}
                layout
                initial={{ opacity: 0, x: -24 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, y: 380, x: -40, scale: 0.25, rotate: -14 }}
                transition={{ type: "spring", stiffness: 260, damping: 26 }}
              >
                <QueueItem
                  card={card}
                  selected={card.id === selectedId}
                  onClick={() => onSelect(card.id)}
                />
              </motion.li>
            ))}
          </AnimatePresence>
          {running && (
            <li className="rounded-lg border border-dashed px-3 py-4 text-center text-xs text-muted-foreground">
              The agents are working on the next cart...
            </li>
          )}
        </ul>

        {notContacted.length > 0 && (
          <Collapsible className="mt-5">
            <CollapsibleTrigger className="group flex w-full items-center justify-between text-xs font-medium text-muted-foreground">
              Not contacted ({notContacted.length})
              <ChevronDown className="size-3.5 transition group-data-[panel-open]:rotate-180" />
            </CollapsibleTrigger>
            <CollapsibleContent>
              <ul className="mt-2 flex flex-col gap-1.5">
                {notContacted.map((card) => (
                  <li key={card.id} className="rounded-md bg-muted/60 px-3 py-2 text-xs">
                    <div className="flex justify-between font-medium">
                      {card.cart_id}
                      <span className="text-muted-foreground">
                        {card.status === "skipped" ? "Skipped" : "Later"}
                      </span>
                    </div>
                    <div className="text-muted-foreground">
                      {whyCodes(card.triage.reason_codes).map(reasonLabel).join(" · ")}
                    </div>
                  </li>
                ))}
              </ul>
            </CollapsibleContent>
          </Collapsible>
        )}
      </div>

      <motion.div
        key={rejected.length}
        animate={rejected.length ? { scale: [1, 1.25, 1] } : {}}
        className="flex items-center gap-2 border-t px-4 py-3 text-xs text-muted-foreground"
      >
        <Trash2 className="size-4" /> Rejected: {rejected.length}
      </motion.div>
    </aside>
  );
}

function QueueItem({
  card,
  selected,
  onClick,
}: {
  card: CardData;
  selected: boolean;
  onClick: () => void;
}) {
  const attention = card.status !== "ready";
  return (
    <button
      onClick={onClick}
      aria-current={selected ? "true" : undefined}
      className={`w-full rounded-lg border px-3 py-2.5 text-left transition hover:border-brand/50 hover:bg-brand/5 ${
        selected ? "border-brand bg-brand/10 ring-1 ring-brand/40" : "bg-card"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-semibold">{card.cart_id}</span>
        {card.review === "approved" ? (
          <CheckCircle2 className="size-4 text-brand" />
        ) : attention ? (
          <AlertTriangle className="size-4 text-amber-500" />
        ) : null}
      </div>
      <div className="mt-0.5 text-xs text-muted-foreground">
        {segmentLabel(card.triage.segment)} · {card.cart.section} ·{" "}
        {card.offer ? offerSummary(card.offer.proposal.offers) : "No offer"}
      </div>
      <div className="mt-1.5 flex flex-wrap gap-1">
        {card.triage.outcome === "CAUTION" && <Badge variant="outline">Caution</Badge>}
        {card.status === "needs_attention" && <Badge variant="destructive">Needs attention</Badge>}
        {card.status === "failed" && <Badge variant="destructive">Failed</Badge>}
        {card.review === "approved" && <Badge className="bg-brand">Ready to send</Badge>}
      </div>
    </button>
  );
}
