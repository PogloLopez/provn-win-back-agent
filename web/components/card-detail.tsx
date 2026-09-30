"use client";

import {
  AlertTriangle,
  Check,
  Copy,
  Mail,
  MessageSquareText,
  Pencil,
  ShieldCheck,
  X,
} from "lucide-react";
import { motion } from "motion/react";
import { useState } from "react";
import { toast } from "sonner";

import { EmailPreview } from "@/components/email-preview";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  hoursAgo,
  money,
  offerLabel,
  reasonLabel,
  segmentLabel,
  violationLabel,
  whyCodes,
} from "@/lib/labels";
import { placeholderValues } from "@/lib/template";
import type { CardData, EditOptions, RejectReason } from "@/lib/types";

const REJECT_REASONS: { reason: RejectReason; label: string }[] = [
  { reason: "too_generous", label: "Too generous" },
  { reason: "wrong_tone", label: "Wrong tone" },
  { reason: "should_not_contact", label: "Shouldn't contact" },
  { reason: "other", label: "Other" },
];

const UPDATED = "rounded-lg p-2 -m-2 ring-2 ring-brand/60 bg-brand/5 transition";

export function CardDetail({
  card,
  options,
  changed,
  busy,
  onApprove,
  onReject,
  onEdit,
  onFeedback,
}: {
  card: CardData;
  options: EditOptions | null;
  changed: { offer: boolean; email: boolean } | null;
  busy: boolean;
  onApprove: () => void;
  onReject: (reason: RejectReason) => void;
  onEdit: () => void;
  onFeedback: () => void;
}) {
  const { cart, triage, offer, email } = card;
  const values = options
    ? placeholderValues(options.values, options.phrases, offer?.proposal.offers ?? [])
    : {};
  const cost = (type: string, value: number) =>
    options?.menu.find((o) => o.type === type && o.value === value)?.cost_usd;

  return (
    <motion.section
      key={card.id}
      initial={{ opacity: 0, y: 12, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      className="mx-auto flex w-full max-w-3xl flex-col gap-5 rounded-2xl border bg-card p-6 shadow-sm"
    >
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Cart {cart.cart_id}</h1>
          <p className="text-sm text-muted-foreground">
            Fan {cart.fan_id} · {segmentLabel(triage.segment)} fan · contact stage{" "}
            {triage.contact_stage}
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {triage.outcome === "CAUTION" && <Badge variant="outline">Handle with caution</Badge>}
          {card.review === "approved" && <Badge className="bg-brand">Ready to send</Badge>}
        </div>
      </header>

      <dl className="grid grid-cols-2 gap-3 rounded-xl bg-muted/50 p-4 text-sm sm:grid-cols-3">
        <Fact label="Seats" value={`${cart.seats} · ${cart.section}`} />
        <Fact label="Cart value" value={money(cart.cart_value)} />
        <Fact label="Left the cart" value={hoursAgo(cart.hours_since_abandon)} />
        <Fact label="Tickets bought before" value={String(cart.lifetime_tickets)} />
        <Fact
          label="Last purchase"
          value={
            cart.days_since_last_purchase === null
              ? "Never"
              : `${cart.days_since_last_purchase} days ago`
          }
        />
        <Fact label="Email consent" value={cart.email_opt_in ? "Yes" : "No"} />
      </dl>

      {whyCodes(triage.reason_codes).length > 0 && (
        <p className="text-sm">
          <span className="font-medium">Flags: </span>
          {whyCodes(triage.reason_codes).map(reasonLabel).join(" · ")}
        </p>
      )}

      {card.status === "failed" && (
        <Notice title="This cart could not be processed">{card.error}</Notice>
      )}

      {offer && (
        <div className={`flex flex-col gap-2 ${changed?.offer ? UPDATED : ""}`}>
          <h2 className="text-sm font-semibold text-muted-foreground">
            Proposed offer {changed?.offer && <UpdatedBadge />}
          </h2>
          {offer.status === "needs_attention" ? (
            <Notice title="The AI's offers broke the business rules on every try">
              A safe reminder with no incentive is prepared instead. Last problems:{" "}
              {lastViolations(offer.attempts)}
            </Notice>
          ) : null}
          <div className="flex flex-wrap items-center gap-2">
            {offer.proposal.offers.length === 0 ? (
              <Badge variant="secondary">Reminder only</Badge>
            ) : (
              offer.proposal.offers.map((o) => (
                <Badge key={o.type} className="bg-brand/15 text-foreground">
                  {o.type === "discount_pct" ? `${o.value}% discount` : offerLabel(o.type)}
                  {cost(o.type, o.value) !== undefined && (
                    <span className="text-muted-foreground">
                      {" "}
                      · costs {money(cost(o.type, o.value)!)}
                    </span>
                  )}
                </Badge>
              ))
            )}
          </div>
          <p className="text-sm leading-relaxed">
            <span className="font-medium">Why: </span>
            {offer.proposal.reason}
          </p>
          {offer.warnings.length > 0 && (
            <p className="text-xs text-amber-700">
              Note: {offer.warnings.map((w) => violationLabel(w.code)).join(" · ")}
            </p>
          )}
        </div>
      )}

      {email && (
        <div className={`flex flex-col gap-2 ${changed?.email ? UPDATED : ""}`}>
          <h2 className="flex items-center gap-1.5 text-sm font-semibold text-muted-foreground">
            <Mail className="size-4" /> Email to the fan {changed?.email && <UpdatedBadge />}
            <span className="ml-auto flex items-center gap-1 text-xs font-normal">
              <ShieldCheck className="size-3.5 text-brand" /> checked against brand & offer rules
            </span>
          </h2>
          {email.status === "needs_attention" && (
            <Notice title="The AI's wording broke the rules on every try">
              A plain template is prepared for you to edit. Last problems:{" "}
              {lastViolations(email.attempts)}
            </Notice>
          )}
          <EmailPreview draft={email.draft} values={values} compact />
        </div>
      )}

      {card.review === "approved" && email ? (
        <ReadyToSend subject={email.email.subject} body={email.email.body} />
      ) : (
        email && (
          <footer className="flex flex-wrap gap-2 border-t pt-4">
            <Button onClick={onApprove} disabled={busy} className="bg-brand hover:bg-brand/90">
              <Check /> Approve
            </Button>
            <Button variant="outline" onClick={onEdit} disabled={busy || !options}>
              <Pencil /> {options ? "Edit" : "Loading options..."}
            </Button>
            <Button variant="outline" onClick={onFeedback} disabled={busy}>
              <MessageSquareText /> Send feedback
            </Button>
            <RejectButton onReject={onReject} disabled={busy} />
          </footer>
        )
      )}
    </motion.section>
  );
}

function UpdatedBadge() {
  return <Badge className="ml-1 bg-brand text-[10px]">Updated by the AI</Badge>;
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="font-medium">{value}</dd>
    </div>
  );
}

function Notice({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
      <AlertTriangle className="mt-0.5 size-4 shrink-0" />
      <div>
        <div className="font-medium">{title}</div>
        <div className="text-amber-800">{children}</div>
      </div>
    </div>
  );
}

function lastViolations(attempts: { violations: { code: string }[] }[]) {
  const last = attempts.at(-1)?.violations ?? [];
  return [...new Set(last.map((v) => violationLabel(v.code)))].join(" · ") || "unknown";
}

function RejectButton({
  onReject,
  disabled,
}: {
  onReject: (reason: RejectReason) => void;
  disabled: boolean;
}) {
  const [open, setOpen] = useState(false);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={<Button variant="destructive" className="ml-auto" disabled={disabled} />}
      >
        <X /> Reject
      </PopoverTrigger>
      <PopoverContent align="end" className="w-60">
        <p className="text-xs font-medium text-muted-foreground">Why reject it?</p>
        <div className="flex flex-wrap gap-1.5">
          {REJECT_REASONS.map(({ reason, label }) => (
            <Button
              key={reason}
              size="sm"
              variant="outline"
              onClick={() => {
                setOpen(false);
                onReject(reason);
              }}
            >
              {label}
            </Button>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}

function ReadyToSend({ subject, body }: { subject: string; body: string }) {
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(`Subject: ${subject}\n\n${body}`);
      toast.success("Email copied. Paste it into your email tool.");
    } catch {
      toast.error("The browser blocked copying. Select the email text and copy it manually.");
    }
  };
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex flex-wrap items-center gap-3 rounded-xl border border-brand/40 bg-brand/10 p-4"
    >
      <Check className="size-5 text-brand" />
      <div className="flex-1 text-sm">
        <div className="font-medium">Approved and ready to send</div>
        <div className="text-muted-foreground">
          No CRM yet: copy the email and send it from your email tool.
        </div>
      </div>
      <Button onClick={copy} className="bg-brand hover:bg-brand/90">
        <Copy /> Copy email
      </Button>
    </motion.div>
  );
}

