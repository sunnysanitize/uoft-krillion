"use client";

import { useState } from "react";
import type { Leaderboard } from "../lib/api";
import { meters } from "../lib/game";
import { Label, Panel } from "./ui";

type Tab = "divers" | "colleges";

/** Today's leaderboard: individual divers or college averages. */
export function Standings({ board, lost, mpp, you }: { board: Leaderboard | null; lost: boolean; mpp: number; you: string }) {
  const [tab, setTab] = useState<Tab>("divers");

  const rows =
    tab === "divers"
      ? (board?.players ?? []).map((p) => ({ key: `${p.nickname}-${p.score}-${p.college}`, name: p.nickname, sub: p.college ?? "", m: p.score * mpp }))
      : (board?.colleges ?? []).map((c) => ({ key: c.college, name: c.college, sub: `${c.n} diving`, m: c.avg * mpp }));

  return (
    <Panel as="section" className="p-5 sm:p-6">
      <div className="flex items-end justify-between gap-4">
        <Label>Today’s standings</Label>
        <div role="tablist" className="flex border-2 border-line text-xs">
          {(["divers", "colleges"] as const).map((t) => (
            <button
              key={t}
              role="tab"
              aria-selected={tab === t}
              onClick={() => setTab(t)}
              className={`px-3 py-1.5 uppercase tracking-[0.2em] cursor-pointer ${tab === t ? "bg-uoft text-ink" : "text-mist hover:text-ink"}`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      {!board ? (
        <p className="mt-6 text-sm text-slate">{lost ? "Standings unavailable right now." : "Pinging the sonar…"}</p>
      ) : rows.length === 0 ? (
        <p className="mt-6 text-sm text-slate">
          {tab === "divers" ? "No divers have surfaced yet today." : "No colleges represented yet. Pick one tomorrow and be first."}
        </p>
      ) : (
        <ol className="mt-4" role="tabpanel">
          {rows.map((r, i) => {
            const me = tab === "divers" && r.name === you;
            return (
              <li
                key={r.key}
                className={`grid grid-cols-[2rem_1fr_auto] items-baseline gap-3 border-b border-line/60 py-2 text-sm last:border-0 ${me ? "text-ink" : ""}`}
              >
                <span className={`font-pixel tabular-nums ${i < 3 ? "text-gold" : "text-slate"}`}>{String(i + 1).padStart(2, "0")}</span>
                <span className="min-w-0 truncate">
                  <span className={me ? "text-sonar" : "text-ink"}>{r.name}</span>
                  {r.sub && <span className="ml-2 text-xs text-slate">{r.sub}</span>}
                </span>
                <span className="font-pixel tabular-nums text-mist">{meters(r.m)}</span>
              </li>
            );
          })}
        </ol>
      )}
    </Panel>
  );
}
