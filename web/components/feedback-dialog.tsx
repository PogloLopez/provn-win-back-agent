"use client";

import { Loader2, Send } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import type { FeedbackResult } from "@/lib/types";

const EXAMPLES = [
  "Too generous for a loyal fan, give a perk instead",
  "Make it warmer and mention the matchday atmosphere",
  "This fan shouldn't get a discount at all",
];

export function FeedbackDialog({
  cartId,
  open,
  onOpenChange,
  onSend,
}: {
  cartId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSend: (text: string) => Promise<FeedbackResult>;
}) {
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<FeedbackResult | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  const close = (next: boolean) => {
    if (sending) return;
    onOpenChange(next);
    if (!next) {
      setText("");
      setResult(null);
      setFailure(null);
    }
  };

  const send = async () => {
    setSending(true);
    setFailure(null);
    try {
      setResult(await onSend(text));
    } catch (error) {
      setFailure(String(error instanceof Error ? error.message : error));
    } finally {
      setSending(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Feedback for the AI on {cartId}</DialogTitle>
          <DialogDescription>
            Say what should change. It goes to the right agent (offer or wording) and comes back
            through the same checks.
          </DialogDescription>
        </DialogHeader>

        <div className="relative min-h-40">
          <AnimatePresence mode="wait">
            {sending ? (
              <motion.div
                key="loading"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="absolute inset-0 grid place-items-center"
              >
                <div className="flex flex-col items-center gap-3 text-sm text-muted-foreground">
                  <Loader2 className="size-10 animate-spin text-brand" />
                  Reading your feedback and preparing a new version...
                </div>
              </motion.div>
            ) : result ? (
              <motion.div
                key="result"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex flex-col gap-3 text-sm"
              >
                <p className="font-medium">{result.note}</p>
                {result.analysis && (
                  <div className="flex flex-wrap gap-1.5">
                    <Badge variant="secondary">
                      {result.analysis.feedback_category.replaceAll("_", " ")}
                    </Badge>
                    <Badge variant="outline">
                      affects {result.analysis.target_component.replaceAll("_", " ")}
                    </Badge>
                    <Badge variant="outline">{result.analysis.severity} priority</Badge>
                  </div>
                )}
                {result.routed_to && (
                  <p className="text-muted-foreground">
                    The card has been updated. Review the new version before approving.
                  </p>
                )}
              </motion.div>
            ) : (
              <motion.div key="form" className="flex flex-col gap-2">
                <Textarea
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder="e.g. Too generous, this fan buys anyway"
                  className="min-h-28"
                />
                <div className="flex flex-wrap gap-1.5">
                  {EXAMPLES.map((example) => (
                    <button
                      key={example}
                      onClick={() => setText(example)}
                      className="rounded-full border px-2.5 py-1 text-xs text-muted-foreground hover:bg-muted"
                    >
                      {example}
                    </button>
                  ))}
                </div>
                {failure && <p className="text-sm text-destructive">{failure}</p>}
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <DialogFooter>
          {result ? (
            <Button onClick={() => close(false)}>Done</Button>
          ) : (
            <Button
              onClick={send}
              disabled={sending || text.trim().length < 3}
              className="bg-brand hover:bg-brand/90"
            >
              <Send /> Send feedback
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
