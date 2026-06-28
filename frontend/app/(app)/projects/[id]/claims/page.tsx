/* eslint-disable */
"use client";

import { useParams } from "next/navigation";
import { useEffect } from "react";
import { toast } from "sonner";
import { Intersect, ArrowCounterClockwise, CaretDown, CaretUp } from "@phosphor-icons/react";
import { useClaimsStore } from "@/lib/stores/claims-store";
import { useJobPolling } from "@/lib/hooks/useJobPolling";
import type { ClaimResponse } from "@/lib/types";

const claimTypeColor = (type: string) => {
    switch (type) {
        case "support":
            return "bg-green-50 text-green-700";
        case "contradict":
            return "bg-red-50 text-red-700";
        case "mixed":
            return "bg-amber-50 text-amber-700";
        case "weak":
        default:
            return "bg-stone text-charcoal";
    }
};

const confidenceColor = (conf: string) => {
    switch (conf) {
        case "high":
            return "text-green-600";
        case "low":
            return "text-amber-600";
        case "medium":
        default:
            return "text-blue-600";
    }
};

function ClaimCard({
    claim,
    expanded,
    onToggle,
}: {
    claim: ClaimResponse;
    expanded: boolean;
    onToggle: () => void;
}) {
    return (
        <div
            className="flex flex-col gap-0 rounded-[10px] bg-surface-card transition-shadow hover:shadow-sm"
            style={{ border: "1px solid var(--hairline)" }}
        >
            <div
                onClick={onToggle}
                className="flex cursor-pointer items-start justify-between gap-4 p-4 sm:p-5"
            >
                <div className="flex-1 space-y-2">
                    {/* Top meta tags */}
                    <div className="flex flex-wrap items-center gap-2">
                        <span
                            className={`font-ui rounded px-2 py-0.5 text-[11px] font-bold uppercase tracking-wider ${claimTypeColor(
                                claim.claim_type
                            )}`}
                        >
                            {claim.claim_type}
                        </span>
                        <span className="font-ui text-[12px] font-medium text-stone">
                            Confidence:{" "}
                            <span className={`font-semibold ${confidenceColor(claim.confidence)}`}>
                                {claim.confidence}
                            </span>
                        </span>
                        <span className="font-ui text-[12px] text-stone">Source: {claim.source_type}</span>
                    </div>

                    <p className="font-ui text-[14px] leading-snug text-ink sm:text-[15px]">
                        {claim.canonical_text}
                    </p>

                    <div className="font-ui mt-1 text-[12px] font-medium text-charcoal">
                        {claim.evidence.length} Evidence{" "}
                        {claim.evidence.length === 1 ? "entry" : "entries"}{" "}
                        <span className="inline-flex items-center text-stone">
                            (click to {expanded ? "collapse" : "expand"})
                        </span>
                    </div>
                </div>

                <button className="shrink-0 text-stone transition-colors hover:text-ink">
                    {expanded ? <CaretUp size={18} weight="bold" /> : <CaretDown size={18} weight="bold" />}
                </button>
            </div>

            {expanded && (
                <div className="border-t border-[var(--hairline)] bg-surface-bone/30 p-4 sm:p-5">
                    <div className="space-y-3">
                        {claim.evidence.map((ev) => (
                            <div
                                key={ev.id}
                                className="rounded-md border border-[var(--hairline)] bg-surface-card p-3"
                            >
                                <div className="mb-1 flex items-center justify-between gap-2">
                                    <span className="font-ui text-[13px] font-semibold text-ink line-clamp-1">
                                        {ev.paper_title || "Unknown Paper"}
                                    </span>
                                    <span
                                        className={`font-ui shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${claimTypeColor(
                                            ev.polarity
                                        )}`}
                                    >
                                        {ev.polarity}
                                    </span>
                                </div>
                                {ev.snippet ? (
                                    <p className="font-ui text-[13px] text-charcoal">"{ev.snippet}"</p>
                                ) : (
                                    <p className="font-ui text-[13px] italic text-stone">No exact quote matched.</p>
                                )}
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}

export default function ProjectClaimsPage() {
    const { id } = useParams<{ id: string }>();
    const projectId = id ?? "";

    const claims = useClaimsStore((s) => s.claims);
    const aggregate = useClaimsStore((s) => s.aggregate);
    const loading = useClaimsStore((s) => s.loadingClaims);
    const generating = useClaimsStore((s) => s.generatingClaims);
    const expandedClaimId = useClaimsStore((s) => s.expandedClaimId);
    const toggleExpand = useClaimsStore((s) => s.toggleExpand);
    const fetchClaims = useClaimsStore((s) => s.fetchClaims);
    const fetchAggregate = useClaimsStore((s) => s.fetchAggregate);
    const generateClaims = useClaimsStore((s) => s.generateClaims);

    const { poll } = useJobPolling({
        onSuccess: (result) => `Synthesized ${(result.claim_count as number) ?? 0} claims`,
    });

    useEffect(() => {
        if (!projectId) return;
        void fetchClaims(projectId);
        void fetchAggregate(projectId);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [projectId]);

    async function handleGenerate() {
        if (!projectId) return;
        try {
            await generateClaims(projectId, async (jobId) => {
                await poll(jobId);
                return null;
            });
        } catch (err) {
            toast.error(err instanceof Error ? err.message : "Synthesis failed");
        }
    }

    // Header chip metrics
    const hasClaims = aggregate && (aggregate.support + aggregate.contradict + aggregate.weak + aggregate.mixed > 0);

    return (
        <div>
            <div className="mb-4">
                <h2 className="font-display text-[22px] font-bold leading-[1.0] text-ink">
                    Claim Consensus
                </h2>
                <p className="mt-1 font-ui text-[12px] text-charcoal">
                    Aggregated claims synthesized from your literature matrix results and detected conflicts.
                </p>
            </div>

            {hasClaims && aggregate && (
                <div className="mb-6 flex flex-wrap gap-2">
                    <div className="flex h-8 items-center gap-2 rounded-full border border-[var(--hairline)] bg-surface-card px-3 text-[13px]">
                        <span className="h-2 w-2 rounded-full bg-green-500"></span>
                        <span className="font-ui font-medium text-ink">Support</span>
                        <span className="font-ui font-semibold text-charcoal">{aggregate.support}</span>
                    </div>
                    <div className="flex h-8 items-center gap-2 rounded-full border border-[var(--hairline)] bg-surface-card px-3 text-[13px]">
                        <span className="h-2 w-2 rounded-full bg-red-500"></span>
                        <span className="font-ui font-medium text-ink">Contradict</span>
                        <span className="font-ui font-semibold text-charcoal">{aggregate.contradict}</span>
                    </div>
                    <div className="flex h-8 items-center gap-2 rounded-full border border-[var(--hairline)] bg-surface-card px-3 text-[13px]">
                        <span className="h-2 w-2 rounded-full bg-stone"></span>
                        <span className="font-ui font-medium text-ink">Weak/Limit</span>
                        <span className="font-ui font-semibold text-charcoal">{aggregate.weak}</span>
                    </div>
                </div>
            )}

            <div className="mb-4 flex items-center gap-3">
                <button
                    onClick={handleGenerate}
                    disabled={generating}
                    className="focus-ring font-ui inline-flex h-[40px] items-center gap-2 rounded-full bg-primary px-4 text-[13px] font-semibold text-on-primary transition-colors hover:bg-primary-deep disabled:opacity-50"
                >
                    {generating ? (
                        <>
                            <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-on-primary border-t-transparent" />
                            Synthesizing…
                        </>
                    ) : (
                        <>
                            <Intersect size={14} />
                            Synthesize Claims
                        </>
                    )}
                </button>
                {claims.length > 0 && (
                    <button
                        onClick={handleGenerate}
                        disabled={generating}
                        className="font-ui inline-flex h-[40px] items-center gap-2 rounded-full bg-primary/10 px-4 text-[13px] font-semibold text-primary transition-colors hover:bg-primary/20 disabled:opacity-50"
                    >
                        <ArrowCounterClockwise size={14} />
                        Resynthesize
                    </button>
                )}
            </div>

            {loading ? (
                <div className="space-y-4">
                    {[1, 2, 3].map((i) => (
                        <div
                            key={i}
                            className="animate-pulse rounded-[10px] bg-surface-card p-5"
                            style={{ border: "1px solid var(--hairline)" }}
                        >
                            <div className="h-4 w-1/4 rounded bg-surface-bone" />
                            <div className="mt-3 h-4 w-3/4 rounded bg-surface-bone" />
                            <div className="mt-3 h-3 w-1/5 rounded bg-surface-bone" />
                        </div>
                    ))}
                </div>
            ) : claims.length === 0 ? (
                <div
                    className="flex flex-col items-center justify-center rounded-[12px] bg-surface-card py-16 text-center"
                    style={{ border: "1px solid var(--hairline)" }}
                >
                    <Intersect size={36} className="mb-3 text-stone" weight="light" />
                    <p className="font-ui text-base font-semibold text-ink">No claims synthesized yet</p>
                    <p className="mt-2 max-w-md text-sm text-charcoal">
                        Synthesize claims from your populated literature matrix to view the overarching consensus and contradictions across papers.
                    </p>
                </div>
            ) : (
                <div className="space-y-3">
                    {claims.map((claim) => (
                        <ClaimCard
                            key={claim.id}
                            claim={claim}
                            expanded={expandedClaimId === claim.id}
                            onToggle={() => toggleExpand(claim.id)}
                        />
                    ))}
                </div>
            )}
        </div>
    );
}
