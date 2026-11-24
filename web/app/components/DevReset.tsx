"use client";

import { useState } from "react";
import { api } from "../lib/api";
import { playerId } from "../lib/game";

/** Dev-only: wipe today's dive on the server and in this browser, then start over. */
export function DevReset({ day }: { day: string }) {
  const [failed, setFailed] = useState(false);

  async function reset() {
    try {
      await api.devReset(playerId());
    } catch {
      return setFailed(true);
    }
    localStorage.removeItem(`rb:dive:${day}`);
    location.reload();
  }

  return (
    <button
      onClick={reset}
      title={failed ? "Reset failed: is the backend running with DEV_RESET=1?" : "Dev only: replay today's dive"}
      className={`fixed right-3 top-3 z-50 border-2 bg-abyss/80 px-3 py-1.5 text-[11px] uppercase tracking-[0.32em] cursor-pointer ${failed ? "border-coral text-coral" : "border-line text-mist hover:border-mist hover:text-ink"}`}
    >
      {failed ? "Reset failed" : "Dev reset"}
    </button>
  );
}
