"use client";

import type { Leaderboard } from "../lib/api";
import { meters } from "../lib/game";
import { Label, Panel } from "./ui";

/** Today's leaderboard of individual divers. */
export function Standings({ board, lost, mpp, you }: { board: Leaderboard | null; lost: boolean; mpp: number; you: string }) {
  const rows = (board?.players ?? []).map((p, i) => ({ key: `${i}-${p.nickname}`, name: p.nickname, m: p.score * mpp }));

  return (
    <Panel as="section" className="p-5 sm:p-6">
      <Label>Today’s standings</Label>

      {!board ? (
        <p className="mt-6 text-sm text-slate">{lost ? "Standings unavailable right now." : "Pinging the sonar…"}</p>
      ) : rows.length === 0 ? (
        <p className="mt-6 text-sm text-slate">No divers have surfaced yet today.</p>
      ) : (
        <ol className="mt-4">
          {rows.map((r, i) => {
            const me = r.name === you;
            return (
              <li
                key={r.key}
                className={`grid grid-cols-[2rem_1fr_auto] items-baseline gap-3 border-b border-line/60 py-2 text-sm last:border-0 ${me ? "text-ink" : ""}`}
              >
                <span className={`font-pixel tabular-nums ${i < 3 ? "text-gold" : "text-slate"}`}>{String(i + 1).padStart(2, "0")}</span>
                <span className={`min-w-0 truncate ${me ? "text-sonar" : "text-ink"}`}>{r.name}</span>
                <span className="font-pixel tabular-nums text-mist">{meters(r.m)}</span>
              </li>
            );
          })}
        </ol>
      )}
    </Panel>
  );
}
