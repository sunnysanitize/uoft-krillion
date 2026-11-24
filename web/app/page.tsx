"use client";

import { useEffect, useRef, useState } from "react";
import { Hud } from "./components/Hud";
import { IntroScreen } from "./components/IntroScreen";
import { PlayScreen } from "./components/PlayScreen";
import { ResultsScreen } from "./components/ResultsScreen";
import { DevReset } from "./components/DevReset";
import { Flash } from "./components/Flash";
import { BubbleRush } from "./components/BubbleRush";
import { Scene } from "./components/Scene";
import { Label, Panel } from "./components/ui";
import { SINK_EASE, SINK_MS, sinkEase, sinkMs, useDive } from "./lib/useDive";

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

  // Feed the pointer position to CSS (--px, --py in -1..1) for parallax and tilt.
  useEffect(() => {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let frame = 0;
    const move = (e: PointerEvent) => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const root = document.documentElement.style;
        root.setProperty("--px", ((e.clientX / innerWidth) * 2 - 1).toFixed(3));
        root.setProperty("--py", ((e.clientY / innerHeight) * 2 - 1).toFixed(3));
      });
    };
    addEventListener("pointermove", move);
    return () => {
      removeEventListener("pointermove", move);
      cancelAnimationFrame(frame);
    };
  }, []);

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
  // A deep tier is a long plunge, a weak answer a quick dip.
  const dropping = phase === "flash" && last;
  const sink = dropping ? sinkMs(last) : SINK_MS;
  const ease = dropping ? sinkEase(last) : SINK_EASE;
  const underwater = phase === "play" || phase === "flash" || phase === "done" || descending;

  return (
    <main>
      <Scene mode={underwater ? "dive" : "surface"} depth={g.depth} ping={g.idx} sink={sink} ease={ease} />
      {descending && <BubbleRush />}

      {phase === "intro" && (
        <IntroScreen
          daily={daily}
          leaving={descending}
          onBegin={begin}
        />
      )}

      {(phase === "play" || phase === "flash") && <Hud answered={g.results.length} total={total} current={g.idx} depth={g.depth} zone={g.zone?.name ?? ""} sink={sink} />}

      {phase === "flash" && g.results.length > 0 && (
        <>
          {/* The drop: bubbles stream past in proportion to how far this answer sank you */}
          <BubbleRush key={g.idx} count={Math.round(last.points / 2)} ms={sink} />
          <Flash result={last} />
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

      {phase === "done" && (
        <ResultsScreen
          daily={daily}
          results={g.results}
          score={g.score}
          depth={g.depth}
          mpp={g.mpp}
          finish={g.finish}
          sonarLost={g.sonarLost}
          onRetry={g.retrySonar}
        />
      )}

      {process.env.NODE_ENV === "development" && <DevReset day={daily.day} />}
    </main>
  );
}
