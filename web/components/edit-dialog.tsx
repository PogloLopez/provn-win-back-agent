"use client";

import { AlertTriangle, Loader2 } from "lucide-react";
import { useRef, useState } from "react";

import { EmailPreview } from "@/components/email-preview";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api";
import { money, offerLabel, violationLabel } from "@/lib/labels";
import { placeholderValues } from "@/lib/template";
import type { CardData, EditOptions, ProposedOffer, Violation } from "@/lib/types";

export function EditDialog({
  card,
  options,
  open,
  onOpenChange,
  onSave,
}: {
  card: CardData;
  options: EditOptions;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (change: { offers: ProposedOffer[]; subject: string; body: string }) => Promise<void>;
}) {
  const [offers, setOffers] = useState<ProposedOffer[]>(card.offer?.proposal.offers ?? []);
  const [subject, setSubject] = useState(card.email?.draft.subject ?? "");
  const [body, setBody] = useState(card.email?.draft.body ?? "");
  const [saving, setSaving] = useState(false);
  const [violations, setViolations] = useState<Violation[]>([]);
  const bodyRef = useRef<HTMLTextAreaElement>(null);

  const types = [...new Set(options.menu.map((o) => o.type))];
  const costOf = (o: ProposedOffer) =>
    options.menu.find((m) => m.type === o.type && m.value === o.value)?.cost_usd ?? 0;
  const total = offers.reduce((sum, o) => sum + costOf(o), 0);
  const overCap = total > options.total_cost_cap_usd;
  const tooMany = offers.length > options.max_offers;
  const placeholders = [...Object.keys(options.values), ...offers.map((o) => o.type)];
  const values = placeholderValues(options.values, options.phrases, offers);

  const toggle = (type: string) =>
    setOffers((current) =>
      current.some((o) => o.type === type)
        ? current.filter((o) => o.type !== type)
        : [...current, { type, value: options.menu.find((m) => m.type === type)!.value }],
    );
  const setLevel = (type: string, value: number) =>
    setOffers((current) => current.map((o) => (o.type === type ? { type, value } : o)));

  const insert = (name: string) => {
    const el = bodyRef.current;
    const token = `{{${name}}}`;
    const at = el?.selectionStart ?? body.length;
    setBody(body.slice(0, at) + token + body.slice(el?.selectionEnd ?? at));
    requestAnimationFrame(() => el?.focus());
  };

  const save = async () => {
    setSaving(true);
    setViolations([]);
    try {
      await onSave({ offers, subject, body });
      onOpenChange(false);
    } catch (error) {
      setViolations(
        error instanceof ApiError && error.violations.length
          ? error.violations
          : [{ code: "ERROR", message: String(error), severity: "block" }],
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[80vh] w-[80vw] max-w-none flex-col gap-4 sm:max-w-none">
        <DialogHeader>
          <DialogTitle>Edit offer and email for {card.cart_id}</DialogTitle>
          <DialogDescription>
            Values are limited to what the business rules allow for this fan. Highlighted text is
            filled in by the system, so prices and discounts can never be mistyped.
          </DialogDescription>
        </DialogHeader>

        <div className="grid min-h-0 flex-1 gap-5 overflow-y-auto md:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
          <section className="flex flex-col gap-3">
            <h3 className="text-sm font-semibold">
              Offer{" "}
              <span className="font-normal text-muted-foreground">
                (up to {options.max_offers}, max {money(options.total_cost_cap_usd)} total)
              </span>
            </h3>
            {types.map((type) => {
              const chosen = offers.find((o) => o.type === type);
              const levels = options.menu.filter((m) => m.type === type);
              return (
                <div
                  key={type}
                  className={`rounded-lg border p-3 ${chosen ? "border-brand bg-brand/5" : ""}`}
                >
                  <button
                    onClick={() => toggle(type)}
                    aria-pressed={Boolean(chosen)}
                    className="flex w-full items-center justify-between text-left text-sm font-medium"
                  >
                    {offerLabel(type)}
                    <span className="text-xs text-muted-foreground">
                      {chosen ? "Included" : "Add"}
                    </span>
                  </button>
                  <p className="text-xs text-muted-foreground">{levels[0].description}</p>
                  {chosen && levels.length > 1 && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {levels.map((level) => (
                        <Button
                          key={level.value}
                          size="xs"
                          variant={chosen.value === level.value ? "default" : "outline"}
                          aria-pressed={chosen.value === level.value}
                          onClick={() => setLevel(type, level.value)}
                        >
                          {level.value}
                          {level.unit === "percent" ? "%" : ""} · {money(level.cost_usd)}
                        </Button>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
            <p className={`text-sm ${overCap || tooMany ? "text-destructive" : ""}`}>
              Total cost to the club: {money(total)}
              {overCap && " (over the cap)"}
              {tooMany && " (too many offers)"}
              {offers.length === 0 && " (reminder only)"}
            </p>
          </section>

          <section className="flex min-w-0 flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="subject">Subject</Label>
              <Input id="subject" value={subject} onChange={(e) => setSubject(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="body">Body</Label>
              <Textarea
                id="body"
                ref={bodyRef}
                value={body}
                onChange={(e) => setBody(e.target.value)}
                className="min-h-40 font-mono text-xs"
              />
              <div className="flex flex-wrap items-center gap-1.5 text-xs">
                <span className="text-muted-foreground">Insert:</span>
                {placeholders.map((name) => (
                  <button
                    key={name}
                    onClick={() => insert(name)}
                    className="rounded bg-brand/15 px-1.5 py-0.5 font-mono ring-1 ring-brand/30 hover:bg-brand/25"
                  >
                    {`{{${name}}}`}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex flex-col gap-1.5">
              <h4 className="text-sm font-medium">Preview</h4>
              <EmailPreview draft={{ subject, body }} values={values} />
            </div>
          </section>
        </div>

        {violations.length > 0 && (
          <div className="flex gap-2 rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm">
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" />
            <ul>
              {violations.map((v, i) => (
                <li key={i}>
                  <span className="font-medium">{violationLabel(v.code)}:</span> {v.message}
                </li>
              ))}
            </ul>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={save} disabled={saving} className="bg-brand hover:bg-brand/90">
            {saving && <Loader2 className="animate-spin" />} Save changes
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
