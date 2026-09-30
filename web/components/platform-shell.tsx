"use client";

import {
  BarChart3,
  Inbox,
  LayoutDashboard,
  Megaphone,
  Settings,
  Users,
  Workflow,
} from "lucide-react";
import { motion } from "motion/react";
import type { ReactNode } from "react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

// Modules a full fan platform would have. They are visibly out of scope for v1 on purpose.
const LATER = [
  { label: "Dashboard", icon: LayoutDashboard },
  { label: "Campaigns", icon: Megaphone },
  { label: "Segments", icon: Users },
  { label: "Automations", icon: Workflow },
  { label: "Analytics", icon: BarChart3 },
  { label: "Settings", icon: Settings },
];

export function PlatformShell({ status, children }: { status: ReactNode; children: ReactNode }) {
  return (
    <div className="flex h-dvh flex-col bg-muted/40">
      <motion.header
        initial={{ opacity: 0, y: -12 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex h-14 shrink-0 items-center justify-between border-b bg-primary px-5 text-primary-foreground"
      >
        <div className="flex items-center gap-2 font-semibold tracking-tight">
          <span className="grid size-7 place-items-center rounded-md bg-brand text-sm">SW</span>
          Seawolves Fan Platform
        </div>
        <div className="text-sm text-primary-foreground/80">{status}</div>
      </motion.header>

      <div className="flex min-h-0 flex-1">
        <motion.nav
          initial={{ opacity: 0, x: -16 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.1 }}
          className="hidden w-52 shrink-0 flex-col gap-1 border-r bg-background p-3 md:flex"
        >
          <div className="flex items-center gap-2 rounded-md bg-brand/10 px-3 py-2 text-sm font-medium text-brand">
            <Inbox className="size-4" /> Win-back review
          </div>
          {LATER.map(({ label, icon: Icon }, i) => (
            <Tooltip key={label}>
              <TooltipTrigger
                render={
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.15 + i * 0.05 }}
                  />
                }
                aria-disabled
                className="flex cursor-not-allowed items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground/60"
              >
                <Icon className="size-4" /> {label}
              </TooltipTrigger>
              <TooltipContent side="right">Not part of v1 (see the README scope)</TooltipContent>
            </Tooltip>
          ))}
        </motion.nav>
        <main className="flex min-h-0 flex-1">{children}</main>
      </div>
    </div>
  );
}
