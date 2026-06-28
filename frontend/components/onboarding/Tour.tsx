"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import { Joyride, EventData, STATUS, Step } from "react-joyride";

interface TourProps {
  steps: Step[];
  storageKey: string;
  minWidth?: number;
  startDelay?: number;
}

function useMounted() {
  return useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );
}

export function Tour({ steps, storageKey, minWidth = 0, startDelay = 300 }: TourProps) {
  const [run, setRun] = useState(false);
  const mounted = useMounted();

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (localStorage.getItem(storageKey)) return;

    // Skip the tour on viewports that are too narrow for all targets to exist.
    if (window.innerWidth < minWidth) {
      localStorage.setItem(storageKey, "true");
      return;
    }

    const timer = setTimeout(() => setRun(true), startDelay);
    return () => clearTimeout(timer);
  }, [storageKey, minWidth, startDelay]);

  const handleEvent = (data: EventData) => {
    const { status, type } = data;
    if (status === STATUS.FINISHED || status === STATUS.SKIPPED) {
      localStorage.setItem(storageKey, "true");
      setRun(false);
    }

    // If a target is missing, close the tour and mark it as seen so the user
    // is not nagged on every reload.
    if (type === "error:target_not_found") {
      localStorage.setItem(storageKey, "true");
      setRun(false);
    }
  };

  if (!mounted) return null;

  return (
    <Joyride
      run={run}
      steps={steps}
      continuous
      scrollToFirstStep
      onEvent={handleEvent}
      options={{
        buttons: ["back", "close", "primary", "skip"],
        showProgress: true,
        overlayClickAction: false,
        skipBeacon: true,
        zIndex: 10000,
        scrollDuration: 0,
        scrollOffset: 0,
        arrowColor: "var(--surface-card)",
        backgroundColor: "var(--surface-card)",
        textColor: "var(--ink)",
        primaryColor: "var(--primary)",
      }}
      styles={{
        tooltipContainer: {
          fontFamily: "var(--font-ui)",
        },
        tooltipTitle: {
          fontFamily: "var(--font-display)",
          fontWeight: 600,
        },
        buttonPrimary: {
          fontFamily: "var(--font-ui)",
          borderRadius: "9999px",
          padding: "8px 16px",
        },
        buttonBack: {
          fontFamily: "var(--font-ui)",
        },
        buttonSkip: {
          fontFamily: "var(--font-ui)",
        },
      }}
      locale={{
        last: "Finish",
        skip: "Skip tour",
        next: "Next",
        back: "Back",
        close: "Close",
      }}
    />
  );
}
