/**
 * Assistant layout - wraps all assistant pages inside the app shell.
 *
 * The AppShell's <main> adds `pt-8 pb-12` padding which makes the chat
 * container overflow the viewport and forces the whole body to scroll.
 * We escape that constraint by rendering a fixed-position wrapper that
 * fills the viewport below the header (and to the right of the desktop
 * sidebar). `overflow-hidden` on the wrapper guarantees only the inner
 * chat body can scroll, not the page itself.
 */

import { AssistantOnboardingTour } from "@/components/onboarding/AssistantOnboardingTour";

export default function AssistantLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div
      className="fixed inset-x-0 top-[60px] bottom-0 xl:left-[56px] overflow-hidden bg-canvas"
      style={{
        zIndex: 1,
        // On mobile, dvh shrinks when the virtual keyboard opens so the
        // chat input stays above the keyboard. Falls back gracefully.
        height: "calc(100dvh - 60px)",
      }}
    >
      <AssistantOnboardingTour />
      {children}
    </div>
  );
}
