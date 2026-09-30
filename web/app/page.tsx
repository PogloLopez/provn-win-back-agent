"use client";

import { Loader2, MousePointerClick, Play } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { CardDetail } from "@/components/card-detail";
import { EditDialog } from "@/components/edit-dialog";
import { FeedbackDialog } from "@/components/feedback-dialog";
import { OfferQueue } from "@/components/offer-queue";
import { PlatformShell } from "@/components/platform-shell";
import { Button } from "@/components/ui/button";
import { api, ApiError, streamRun } from "@/lib/api";
import type { CardData, EditOptions, ProposedOffer, RejectReason } from "@/lib/types";

type Dialog = "edit" | "feedback" | null;

export default function Home() {
  const [runId, setRunId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [total, setTotal] = useState(0);
  const [cards, setCards] = useState<CardData[]>([]);
  const [running, setRunning] = useState(false);
  const [telemetryFailures, setTelemetryFailures] = useState(0);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [options, setOptions] = useState<Record<number, EditOptions>>({});
  const [busy, setBusy] = useState(false);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [changed, setChanged] = useState<{ offer: boolean; email: boolean } | null>(null);
  const closeStream = useRef<(() => void) | null>(null);

  useEffect(() => () => closeStream.current?.(), []);

  const upsert = useCallback((card: CardData) => {
    setCards((current) =>
      current.some((c) => c.id === card.id)
        ? current.map((c) => (c.id === card.id ? card : c))
        : [...current, card],
    );
  }, []);

  const loadOptions = useCallback(async (card: CardData) => {
    if (!card.offer) return;
    try {
      const loaded = await api.options(card.id);
      setOptions((current) => ({ ...current, [card.id]: loaded }));
    } catch (error) {
      toast.error(`Could not load the offer options for ${card.cart_id}: ${error}`);
    }
  }, []);

  const start = async () => {
    setStarting(true);
    try {
      const run = await api.startRun();
      setRunId(run.run_id);
      setTotal(run.total);
      setRunning(true);
      closeStream.current = streamRun(run.run_id, {
        onCard: upsert,
        onDone: (failures) => {
          setRunning(false);
          setTelemetryFailures(failures);
          toast.success("All carts processed. Pick an offer to review.");
        },
        onFailure: (detail) => {
          setRunning(false);
          toast.error(`The run stopped: ${detail}`);
        },
      });
    } catch (error) {
      toast.error(
        error instanceof ApiError && error.status === 429
          ? `The demo is busy: ${error.message}.`
          : `Could not start the demo: ${error}`,
      );
    } finally {
      setStarting(false);
    }
  };

  const selected = cards.find((c) => c.id === selectedId) ?? null;

  const select = (id: number) => {
    setSelectedId(id);
    setDialog(null);
    setChanged(null);
    const card = cards.find((c) => c.id === id);
    if (card && !options[id]) void loadOptions(card);
  };

  const act = async (action: () => Promise<CardData>, success: string) => {
    setBusy(true);
    try {
      const card = await action();
      upsert(card);
      void loadOptions(card);
      toast.success(success);
      return card;
    } catch (error) {
      toast.error(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  };

  const reject = async (reason: RejectReason) => {
    if (!selected) return;
    const card = await act(() => api.reject(selected.id, reason), "Rejected. Thanks, that's logged.");
    if (card) setSelectedId(null); // the card flies to the trash
  };

  const saveEdit = async (change: { offers: ProposedOffer[]; subject: string; body: string }) => {
    if (!selected) return;
    const card = await api.edit(selected.id, change); // errors surface inside the dialog
    upsert(card);
    void loadOptions(card);
    toast.success("Changes saved and re-checked. Review and approve when ready.");
  };

  const sendFeedback = async (text: string) => {
    const before = selected!;
    const result = await api.feedback(before.id, text);
    upsert(result.card);
    void loadOptions(result.card);
    // Show the marketer what the agents changed.
    setChanged({
      offer:
        JSON.stringify(before.offer?.proposal.offers) !==
        JSON.stringify(result.card.offer?.proposal.offers),
      email: JSON.stringify(before.email?.draft) !== JSON.stringify(result.card.email?.draft),
    });
    return result;
  };

  const restart = () => {
    closeStream.current?.();
    setRunId(null);
    setCards([]);
    setSelectedId(null);
    setOptions({});
    setDialog(null);
    setChanged(null);
    setTelemetryFailures(0);
  };

  if (!runId) return <Landing starting={starting} onStart={start} />;

  return (
    <PlatformShell
      status={
        <span className="flex items-center gap-3">
          {telemetryFailures > 0 && (
            <span className="rounded bg-amber-400/90 px-2 py-0.5 text-xs text-amber-950">
              Telemetry degraded
            </span>
          )}
          Run {runId}
          {!running && (
            <Button size="sm" variant="secondary" onClick={restart}>
              New run
            </Button>
          )}
        </span>
      }
    >
      <OfferQueue
        cards={cards}
        selectedId={selectedId}
        onSelect={select}
        running={running}
        total={total}
      />
      <div className="min-w-0 flex-1 overflow-y-auto p-6">
        <AnimatePresence mode="wait">
          {selected ? (
            <CardDetail
              key={selected.id}
              card={selected}
              options={options[selected.id] ?? null}
              changed={changed}
              busy={busy}
              onApprove={() => act(() => api.approve(selected.id), "Approved and ready to send.")}
              onReject={reject}
              onEdit={() => setDialog("edit")}
              onFeedback={() => setDialog("feedback")}
            />
          ) : (
            <motion.div
              key="empty"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="grid h-full place-items-center text-center text-sm text-muted-foreground"
            >
              <div className="flex flex-col items-center gap-2">
                <MousePointerClick className="size-8" />
                {cards.length === 0
                  ? "The agents are reviewing the stale carts..."
                  : "Select an offer on the left to review it."}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {selected && dialog === "edit" && options[selected.id] && (
        <EditDialog
          card={selected}
          options={options[selected.id]}
          open
          onOpenChange={(open) => !open && setDialog(null)}
          onSave={saveEdit}
        />
      )}
      {selected && dialog === "feedback" && (
        <FeedbackDialog
          cartId={selected.cart_id}
          open
          onOpenChange={(open) => !open && setDialog(null)}
          onSend={sendFeedback}
        />
      )}
    </PlatformShell>
  );
}

function Landing({ starting, onStart }: { starting: boolean; onStart: () => void }) {
  return (
    <main className="grid min-h-dvh place-items-center bg-primary px-6 text-primary-foreground">
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex max-w-xl flex-col items-center gap-6 text-center"
      >
        <span className="grid size-14 place-items-center rounded-2xl bg-brand text-xl font-bold">
          SW
        </span>
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
          Seattle Seawolves cart win-back
        </h1>
        <p className="text-primary-foreground/75">
          AI agents review fans who left tickets in their cart, decide who is worth contacting,
          propose an offer within the club&apos;s rules, and draft an on-brand email. You approve,
          edit, reject, or send feedback before anything reaches a fan.
        </p>
        <Button
          size="lg"
          onClick={onStart}
          disabled={starting}
          className="h-12 bg-brand px-8 text-base hover:bg-brand/90"
        >
          {starting ? <Loader2 className="animate-spin" /> : <Play />} Start demo
        </Button>
        <p className="text-xs text-primary-foreground/50">
          Runs the real agents on 5 sample carts. Offers appear as each one finishes.
        </p>
      </motion.div>
    </main>
  );
}
