"use client";

import { useEffect, useRef, useState } from "react";
import { DepthRuler } from "./components/DepthRuler";
import { Hud } from "./components/Hud";
import { IntroScreen } from "./components/IntroScreen";
import { PlayScreen } from "./components/PlayScreen";
import { ResultsScreen } from "./components/ResultsScreen";
import { RevealScreen } from "./components/RevealScreen";
import { Scene } from "./components/Scene";
import { Label, Panel } from "./components/ui";
import { useDive } from "./lib/useDive";

// Matches the Scene camera transition (duration-[1800ms]), so the clock starts once we're underwater.
const DESCENT_MS = 1800;

export default function Game() {
  const g = useDive();
  const { daily, phase } = g;
  const [descending, setDescending] = useState(false);
  const started = useRef(false);

  // Begin: sink the camera first, then start the clock. Only once, however many times Enter is pressed.
  function begin() {
    if (started.current) return;
    started.current = true;
    setDescending(true);
    setTimeout(() => {
      g.begin();
      setDescending(false);
    }, DESCENT_MS);
  }

  // Keep the page from scrolling under the fixed scene, except on results.
  useEffect(() => {
    document.body.style.overflow = phase === "done" ? "" : "hidden";
  }, [phase]);

  if (phase === "loading" || phase === "error" || !daily)
    return (
      <>
        <Scene mode="surface" depth={0} />
        <div className="fixed inset-x-0 top-[72vh] flex justify-center px-5">
          {phase === "loading" ? (
            <Label className="animate-blink">Descending</Label>
          ) : (
            <Panel className="max-w-sm p-6">
              <Label className="text-coral">Lost signal</Label>
              <p className="mt-3 text-sm leading-relaxed text-mist">
                Can’t reach the dive server. Check the backend is running on :8000, then refresh.
              </p>
            </Panel>
          )}
        </div>
      </>
    );

  const total = daily.prompts.length;
  const last = g.results[g.results.length - 1];
  const underwater = phase === "play" || phase === "reveal" || descending;

  return (
    <main>
      <Scene mode={underwater ? "dive" : "surface"} depth={g.depth} />

      {phase === "intro" && (
        <IntroScreen
          daily={daily}
          nickname={g.nickname}
          college={g.college}
          leaving={descending}
          onProfile={g.setProfile}
          onBegin={begin}
        />
      )}

      {(phase === "play" || phase === "reveal") && (
        <>
          <DepthRuler depth={g.depth} zones={daily.zones} />
          <Hud
            depth={g.depth}
            zone={g.zone?.name ?? ""}
            score={g.score}
            results={g.results}
            total={total}
            current={phase === "play" ? g.idx : g.idx - 1}
          />
        </>
      )}

      {phase === "play" && g.prompt && (
        <PlayScreen
          prompt={g.prompt}
          index={g.idx}
          total={total}
          remaining={g.remaining}
          limit={g.limitMs}
          submitting={g.submitting}
          onSubmit={g.submit}
        />
      )}

      {phase === "reveal" && last && <RevealScreen result={last} last={g.idx >= total} mpp={g.mpp} onNext={g.next} />}

      {phase === "done" && (
        <ResultsScreen
          daily={daily}
          results={g.results}
          score={g.score}
          depth={g.depth}
          mpp={g.mpp}
          finish={g.finish}
          board={g.board}
          sonarLost={g.sonarLost}
          onRetry={g.retrySonar}
          nickname={g.nickname}
        />
      )}
    </main>
  );
}
