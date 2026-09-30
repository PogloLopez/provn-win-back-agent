import { renderParts } from "@/lib/template";
import type { Draft } from "@/lib/types";

/** The email as the fan will read it; values filled in by the system are highlighted. */
export function EmailPreview({
  draft,
  values,
  compact = false,
}: {
  draft: Draft;
  values: Record<string, string>;
  compact?: boolean;
}) {
  return (
    <div className="rounded-lg border bg-background">
      <div className="border-b px-4 py-2.5 text-sm">
        <span className="text-muted-foreground">Subject: </span>
        <Highlighted text={draft.subject} values={values} />
      </div>
      <p
        className={`whitespace-pre-wrap px-4 py-3 text-sm leading-relaxed ${
          compact ? "max-h-64 overflow-y-auto" : ""
        }`}
      >
        <Highlighted text={draft.body} values={values} />
      </p>
    </div>
  );
}

function Highlighted({ text, values }: { text: string; values: Record<string, string> }) {
  return (
    <>
      {renderParts(text, values).map((part, i) =>
        part.kind === "text" ? (
          <span key={i}>{part.text}</span>
        ) : (
          <mark
            key={i}
            title={`Filled in by the system from {{${part.name}}}`}
            className="rounded bg-brand/15 px-1 text-foreground ring-1 ring-brand/30"
          >
            {part.text}
          </mark>
        ),
      )}
    </>
  );
}
