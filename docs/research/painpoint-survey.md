# Pain Point Survey: Literature Review Workflow

## Research Methodology

This survey was conducted by searching Reddit, academic forums, Medium,
Substack, research papers, and AI tool review sites (Nature, The Lancet,
arXiv, ResearchGold, CiteDash, ScholarBits, LessWrong, GitHub) for real
researcher frustrations with the literature review process. Every pain point
below is backed by actual quotes and data from these sources.

Sources evaluated: ~35 distinct sources (Reddit threads, blog posts, academic
papers, AI tool benchmarks, systematic review guides).

---

## Pain Point Category 1: Information Overload and Search Chaos

### 1.1. Too Many Results, Too Little Signal

Researchers face millions of results with no effective way to triage.

> "A quick search on Google Scholar for almost any topic will give you
> thousands of results. That sounds helpful, but it is actually the opposite.
> When everything is available, nothing feels clear." — John Marcellin Tan,
> Medium (Feb 2026)

> "Last time I visited Google Scholar and searched on a few project-relevant
> terms, I encountered 105,000 papers. It takes me a full day to read and
> satisfactorily understand an academic paper. So reading 105 kilo-papers
> would take me 288 years." — LessWrong, "How to (not) do a literature review"

> "Conducting a literature review is, in the words of one researcher on
> r/GradSchool, 'like drowning in information and somehow still not having
> what you need.'" — ScholarBits (2025)

### 1.2. Irrelevant Results Waste Time

> "I have spent an entire 40 minutes reading a thirty-page paper only to
> realize at the very end that it has absolutely nothing to do with my
> specific demographic or research question." — Earl Josh Delgado, Medium
> (Feb 2026)

> "A researcher conducting a Google Scholar search on a reasonably broad
> topic may download 200 PDFs, only to find after reading abstracts that 140
> are irrelevant. At two minutes per abstract, that is nearly five hours of
> elimination work." — ScholarBits (2025)

### 1.3. No Clear Filter Strategy

> "Before you even start searching, you need to know exactly what your
> research is about. What is your topic? What are the key concepts? What
> time period are you focused on? Once you have those answers, searching
> becomes a lot less overwhelming." — John Marcellin Tan, Medium (Feb 2026)

### 1.4. Source Duplicates Across Databases

> "Three out of the five tested tools listed sources multiple times. These
> source duplicates usually had a different URL but their content was
> identical. You.com found 82 sources in the first run, of which only 23
> remained after removing all duplicate entries." — arXiv:2605.10125, Useful
> for Exploration, Risky for Precision (2025)

### 1.5. Language Bias in Search Results

> "English results and high-citation papers will usually dominate academic
> APIs." — Project docs (confirmed by language bias research)

**Severity: 9/10** — This is the most frequently cited pain point. Every
stage downstream depends on finding the right papers first.

**How This Maps to Our Project:** Search with multi-source fan-out, query
planning, deduplication, language-bias audit, and source diagnostics.

---

## Pain Point Category 2: Paywalls and Access Inequality

### 2.1. Students Cannot Afford Papers

> "You find the perfect study. It is exactly what you need. And then you
> click on it, and a page pops up telling you it costs thirty to fifty
> dollars to access. For one article." — John Marcellin Tan, Medium

> "Students at smaller public universities are often left with only a
> handful of free resources, and that puts them at a real disadvantage."
> — John Marcellin Tan, Medium

### 2.2. Sci-Hub as a Symptom

> "Sci-Hub has become something of a quiet lifeline for student researchers
> who cannot afford individual article fees... Its existence points to a
> bigger problem: important knowledge should not cost more than a meal just
> to read once." — John Marcellin Tan, Medium

### 2.3. Open-Access Limitations

> "Where it struggles: The tool relies on open-access sources, preprints,
> and grey source databases to obtain full-text PDFs. In domains where most
> research is locked behind paywalls... it will find metadata and abstracts
> but may have limited full-text coverage." — foundry-research, GitHub (2026)

**Severity: 7/10** — Not every researcher faces this equally, but when it
hits, it blocks the entire workflow.

**How This Maps to Our Project:** Use Semantic Scholar, OpenAlex, and arXiv
(open-access sources). Use Exa for research page discovery. Firecrawl for
open-access landing page content extraction.

---

## Pain Point Category 3: Synthesis Failures

### 3.1. The "Laundry List" Trap

The single most common failure mode: students summarize papers one by one
instead of synthesizing.

> "My drafts always start looking something like this: 'Smith (2020) said
> that online learning is good for flexibility. Then, Jones (2021) said
> that students miss face-to-face interactions.' It is basically just a
> series of mini book reports glued together with duct tape." — Earl Josh
> Delgado, Medium

> "Pidro kept writing paragraphs that started with 'According to Smith
> (2020)...' followed by 'Meanwhile, Johnson (2019) found that...' followed
> by 'In contrast, Lee (2021) argued...' Each study got its own paragraph.
> Its own little island. No bridges. No conversation." — James Ga-as,
> Medium (Feb 2026)

> "A real literature review does not just report what each study found. It
> connects them. It asks what the studies agree on, where they contradict
> each other, and what none of them have fully answered yet." — John
> Marcellin Tan, Medium

### 3.2. Cross-Paper Comparison is Overwhelming

> "Now imagine if you have read 50 papers. That means you would have to
> compare the contents, theories, and conclusions of a new paper you would
> read to fifty other papers." — Galileon Destura, Medium (Feb 2026)

> "Each paper has a finding, a method, a theoretical framework, and a set
> of keywords. Synthesising across papers requires identifying patterns
> across all of these dimensions simultaneously — a task that is genuinely
> difficult to do in a spreadsheet." — ScholarBits

### 3.3. No One Teaches Synthesis

> "We are trained, from elementary school through college, to summarize.
> Read a thing, write what it says, move on. Our entire educational
> experience has conditioned us to be reporters of information rather than
> critics of it. So when someone asks us to synthesize... our brains just
> stop working." — James Ga-as, Medium

**Severity: 8/10** — Universal across all student levels. This is where most
literature reviews fail to become more than summaries.

**How This Maps to Our Project:** Literature matrix with structured
columns (method, dataset, result, limitation) forces comparison. Gap
detection from matrix rows. Synthesis scaffold from grouped evidence.

---

## Pain Point Category 4: Citation Hallucinations

### 4.1. Fabrication Rates Are Staggeringly High

Hard data from multiple sources:

| Study | Tool Tested | Fabrication Rate |
|-------|------------|-----------------|
| Walters & Wilder (2023) | GPT-3.5 / GPT-4 | 55% / 18% |
| Nature (2024) study | ChatGPT (biomedical) | >30% |
| Athaluri et al. (2024) | GPT-3.5 & GPT-4 | 36%–72% |
| CiteDash Benchmark (2026) | ChatGPT-4o | ~38% |
| CiteDash Benchmark (2026) | Claude 3.5 Sonnet | ~24% |
| CiteDash Benchmark (2026) | Gemini 1.5 Pro | ~19% |
| PMC study (2025) | GPT-4o (mental health) | 20% fabricated + 45% had errors = 65% total problematic |

### 4.2. Published Papers Contain Fabricated Citations

> "An audit of 2.5 million biomedical papers in PubMed Central Open Access
> covering January 2023 to February 2026 identified 4,046 fabricated
> references across 2,810 papers. The rate rose from 4 per 10,000 papers in
> 2023 to about 57 per 10,000 by early 2026 — a more than 12-fold increase."
> — The Lancet (May 2026)

> "GPTZero performed an analysis of the 4841 papers accepted by the NeurIPS
> 2025 conference. They found 100 hallucinated citations across 51 papers
> that had made it fully through the conference's peer review process."
> — Plagiarism Today (Mar 2026)

### 4.3. Fake Citations Look More Real Than Real Ones

> "AI citations are suspiciously convenient. They appear right when you
> need them, saying exactly what you need them to say." — LLRX (Mar 2026)

> "The model produces a citation blending two real papers by the same
> author into a composite that does not exist. This is arguably a more
> sophisticated failure mode, but it is still a failure mode."
> — CiteDash Benchmark (Apr 2026)

### 4.4. Verification Is a Full-Time Job

> "A colleague asked for her help in tracking down two references... when
> she examined the 14 sources in the paper, she found that 12 simply did
> not exist." — Plagiarism Today (Mar 2026)

> "If ChatGPT claims 'research shows,' your job is to find the actual
> research or acknowledge it might not exist." — LLRX (Mar 2026)

### 4.5. ChatGPT Can't Stop Once It Starts

> "I'll tell it that quote doesn't exist and it'll acknowledge it was
> wrong, then make up another. And another." — Reddit researcher on
> r/ChatGPT (Jul 2025)

**Severity: 10/10** — This is the trust-killer. If citations can't be
trusted, the entire output is academically worthless. This is the single
most damaging failure mode.

**How This Maps to Our Project:** Citation guardrail is the core
differentiator. Backend validates every citation ID against
`project_papers`. Reference list built from database, not model text.
Invalid citations rejected before export.

---

## Pain Point Category 5: Source Quality and Credibility

### 5.1. Not All Published Papers Are Credible

> "One of the hardest lessons for student researchers is accepting that
> not all sources are trustworthy, even ones that look academic. Blog posts
> dressed up to look like studies, opinion pieces with citations that do
> not actually support the claims, and even fake research exist in large
> numbers online." — John Marcellin Tan, Medium

> "Some of the sources listed by the tools were published in predatory
> journals. This could put their scientific quality further into question."
> — arXiv:2605.10125 (2025)

### 5.2. Poor Search Reproducibility

> "Literature review tools supported exploratory searches but showed low
> reproducibility, limited transparency regarding chosen sources and
> databases, and inconsistent source quality, making them unsuitable for
> systematic reviews." — arXiv:2605.10125

> "You.com achieved a Jaccard Index Score of 17.6%, ChatGPT of 25.0%,
> Consensus AI scored the best with 28.0% and Perplexity AI the worst with
> 11.8% overlap" between two identical search runs. — arXiv:2605.10125

**Severity: 7/10** — Credibility issues compound with citation problems.

**How This Maps to Our Project:** Source adapters with canonical paper
schema. Papers stored with source names and identifiers. Enrichment
service fills gaps before downstream AI workflows.

---

## Pain Point Category 6: Structural and Organizational Problems

### 6.1. No Clear Structure Template

> "Nobody teaches you how to organize a literature review. Do you go
> chronologically? Thematically? Methodologically? By theoretical
> framework? The answer is 'it depends,' which is the most useless answer
> in academia." — James Ga-as, Medium

> "The Paralysis of the Blank Page... You have a tracking spreadsheet full
> of 60 papers. You have notes, highlights, and PDFs scattered across your
> desktop. Now, you open a blank document, and the paralysis sets in."
> — Galileon Destura, Medium

### 6.2. Keeping Track of Everything

> "I have had my fair share of difficulty in keeping track of different
> papers. Sometimes I can reach up to 60 citations without a proper
> tracker, and it gets really confusing and really hard remembering which
> paper mentioned this and which one correlated to your paper."
> — Galileon Destura, Medium

> "Sources pile up fast, and if you are manually tracking them in a
> document or trying to remember which article said what, mistakes are
> going to happen. Citations will get formatted wrong. Studies will get
> mixed up. References will go missing right before the deadline."
> — John Marcellin Tan, Medium

### 6.3. PRISMA Diagrams Are Manual "Soul-Crushing Work"

> "A TeX Stack Exchange thread and multiple r/PhD threads describe this as
> 'soul-crushing work' — building a diagram that has no creative content,
> only data entry into a fixed structure, using design tools that were not
> designed for it." — ScholarBits

**Severity: 7/10** — Universal organizational pain, affects everyone.

**How This Maps to Our Project:** Project as the organizing container.
Structured matrix rows. Saved papers with status labels. Exportable
outputs with database-backed references.

---

## Pain Point Category 7: Research Gap Detection is Hard

### 7.1. Generic Gaps Are Easy, Real Gaps Are Hard

> "'More work is needed on real-world deployment' can fit almost any field.
> Unless every gap is tied to extracted limitations and missing combinations
> in the matrix, the feature can become generic." — Project review docs

> "Research gaps generally fall into four distinct categories... You do
> not find a research gap by staring at the literature. You find it by
> noticing what's not there." — Galileon Destura, Medium

### 7.2. The Meta-Skill Nobody Teaches

> "The easiest place to start is the 'Discussion' or 'Future Work' section
> of a published paper. When you compile twenty papers and notice that
> fifteen of them share the exact same limitation, you have found a
> massive, validated research gap." — Galileon Destura, Medium

**Severity: 6/10** — Critical for research contribution, but most students
don't get this far before struggling with earlier stages.

**How This Maps to Our Project:** Gap detection from matrix rows with
mandatory evidence paper IDs. Gaps rejected if no evidence. Gap cards
showing supporting papers side by side.

---

## Pain Point Category 8: Time and Resource Constraints

### 8.1. Systematic Reviews Are Inhumanly Long

> "A full systematic review averages 1,000–2,000 person-hours across its
> lifecycle. It takes 12–24 months from protocol registration to
> publication. The literature search alone takes 2–6 weeks. Title and
> abstract screening for a large review can occupy a team of three for
> three to six months." — "The Complete Systematic Review Guide" (May 2026)

> "A master's student came to me in full meltdown mode, because he'd been
> asked to produce a full-scale systematic review (something usually done
> by a whole research team) entirely on his own, with no training and no
> structure." — SystematicReviewTools.app (Feb 2026)

### 8.2. "Clerical Drain" - 15-20 Hours/Week Lost

> "A 2024 analysis of research workflows found that literature reviews
> account for a disproportionate share of researchers' 'clerical drain' —
> the 15–20 hours per week lost to tasks that produce no new scientific
> insight." — ScholarBits

### 8.3. Screening Is the Biggest Bottleneck

> "The first stage of a systematic literature review — screening titles
> and abstracts for relevance — is among the most time-consuming and
> intellectually unrewarding tasks in academic research." — ScholarBits

### 8.4. AI-Assisted Screening Still Has Problems

> "AI screening should be validated against human screening before relying
> on it... Screen 50 papers with AI and also screen them yourself
> independently. Compare results. If agreement is above 90%, your criteria
> are well-defined. If below 80%, your criteria need clarification before
> continuing." — Prismer Blog (Apr 2026)

> "Most of the tools available were developed by private companies... the
> whole process takes longer than doing the work manually." — Cochrane
> Collaboration, Nature (May 2026)

**Severity: 9/10** — Time pressure is the meta-problem that makes every
other pain point worse.

**How This Maps to Our Project:** AI-assisted screening via matrix
generation. Structured extraction from saved papers. Editable matrix rows.
Backend enrichment to reduce manual metadata hunting. Project as workflow
container with clear next-step indicators.

---

## Pain Point Category 9: AI Tool Fragmentation

### 9.1. No Single Tool Covers the Full Workflow

> "The biggest mistake in AI research work is trying to use one tool for
> everything. Research is not one task. It is a sequence of different
> tasks." — AI Research Reviews (Apr 2026)

> "The best AI for literature review in 2026 is not one tool but a stack.
> Elicit handles structured extraction. Consensus answers evidence-stance
> questions. Scite shows citation context. Research Rabbit and Litmaps
> visualise citation networks. ChatGPT and Claude handle synthesis writing.
> No single AI literature review tool does it all." — ResearchGold (May 2026)

### 9.2. Switching Tools Creates Friction

> "A reasonable 2026 stack: Elicit + Scite + Claude. Total cost: roughly
> $60 per month." — ResearchGold

> "The key decision is not choosing one winner. The key decision is
> refusing to force one tool into every stage." — AI Research Reviews

### 9.3. Generic Agents Fail at Research

A researcher documented an entire conversation with a GPT agent that
produced 50x more text than the user's complaint:

> "anyone successfully managed to use a generic agent for serious
> literature search? what is your technique? i've been chatting with
> hermes (gpt) since this morning via telegram trying to get it to find
> papers, and it keeps deflecting from actual serious searching. now i
> see its actual output and its even worse." — Digg/Reddit (May 2026)

The agent kept reorganizing files, renaming vaults, counting papers
inconsistently, and mostly avoided actually searching for new papers.

**Severity: 6/10** — This is a UX fragmentation problem. Researchers
cobble together workflows from multiple tools.

**How This Maps to Our Project:** Single integrated workflow from search
to export. One tool covering the full pipeline. No switching between
Elicit, NotebookLM, ChatGPT, Zotero, and PowerPoint.

---

## Pain Point Category 10: Emotional and Psychological Toll

### 10.1. Imposter Syndrome

> "You sit alone with a screen and a pile of sources and you try to make
> sense of a field that took hundreds of researchers decades to build. The
> imposter syndrome is relentless. Every well-written paper you read makes
> you feel less capable. Every brilliant finding makes your own work feel
> insignificant." — James Ga-as, Medium

### 10.2. Translation Difficulty for Practitioner-Researchers

> "It isn't impostor syndrome, and it isn't a confidence problem... You
> know the field. You're doubting whether what you know can be said in the
> form being asked of you." — Dr. Eleanor Pritchard, Substack (May 2026)

> "When the sentence won't form, the question isn't what's wrong with me.
> The question is what's the gap between what I know and what this form
> wants." — Dr. Eleanor Pritchard, Substack

### 10.3. Loneliness and Burnout

> "Writing a thesis is an incredibly lonely, frustrating, and isolating
> experience. I spend hours and hours alone in my dorm, staring at a
> glowing screen until my eyes literally burn." — Earl Josh Delgado, Medium

> "A literature review is not an endeavor that we commonly attempt. I have
> never seen a single student that has willingly wanted to create an
> article review out of pure, unfiltered love of the game." — Galileon
> Destura, Medium

**Severity: 5/10** — Not directly solvable by software, but a well-designed
tool can reduce the "alone in chaos" feeling by providing structure.

**How This Maps to Our Project:** Clear workflow steps with visual
progress. Editable intermediate artifacts. Error messages that explain
what to do next (not just "failed"). Seeded demo project for training.

---

## Pain Point Category 11: Writing and Argumentation

### 11.1. Moving from Reading to Writing

> "The most common failure mode is using ChatGPT too early and never
> building a real source-grounded understanding of the material."
> — AI Research Reviews

> "It's much easier to absorb information that you care about. One way
> that I hacked this... I reached out to a number of authors that I had
> encountered in my literature search for an informal chat."
> — LessWrong

### 11.2. Structure is the Invisible Framework

> "Structure is the invisible framework that holds the massive weight of a
> literature review together. You could have the most groundbreaking
> research topic, the most exhaustive list of peer-reviewed sources... but
> if your paper is a disorganized, rambling wall of text, your reader will
> never realize your brilliance." — Galileon Destura, Medium

**Severity: 6/10** — Depends on skill level. Early-career researchers
struggle most.

**How This Maps to Our Project:** Structured report sections with inline
citation IDs. Matrix as evidence scaffolding. Gap evidence as
argumentation building blocks.

---

## Pain Point Category 12: Verification and Quality Control

### 12.1. AI Extraction Errors Are Common

> "Both RAs achieved nearly identical in-sample success rates (98%) but
> diverged sharply in out-of-sample performance (Allen 67%, Anne 41%)."
> — MAER-NET, Building Meta-Analysis Datasets with AI (Mar 2026)

> "Always verify AI extraction against the original paper for key results.
> Extraction errors in systematic reviews have serious consequences — they
> propagate to meta-analyses and clinical guidelines." — Prismer Blog

### 12.2. No Explainability

> "xAI accuracy scores ranged between 1 and 3, indicating that highlighted
> passages often did not reliably correspond to the information used to
> generate the responses." — arXiv:2605.10125

> "Some tools highlighted entire pages or irrelevant sections such as
> reference lists instead of specific supporting passages." — arXiv:2605.10125

### 12.3. Citation Context Is Hidden

> "AI treats a conference paper, a journal article, a blog post, and a
> Nobel laureate's research with equal authority if they contain the right
> keywords." — LLRX

**Severity: 8/10** — This is a trust and integrity issue. Errors that
survive into published work damage the scientific record.

**How This Maps to Our Project:** Matrix rows are editable by users.
Extraction confidence levels displayed. Hybrid RAG evidence with
`project_paper_id` per chunk. Citation audit stored with every report.

---

## Summary: Top Pain Points by Severity

| Rank | Pain Point | Severity | Our Solution |
|------|-----------|----------|-------------|
| 1 | Citation hallucinations (30-72% of AI output) | 10/10 | Citation guardrail: validate against DB, reject invalid |
| 2 | Information overload / search chaos | 9/10 | Multi-source search with dedup, language-bias audit |
| 3 | Time constraints (1000-2000 hrs/review) | 9/10 | AI-assisted screening, matrix generation, enrichment |
| 4 | Synthesis failures / "laundry list" trap | 8/10 | Literature matrix forces cross-paper comparison |
| 5 | Verification burden (spot-checking extraction) | 8/10 | Editable matrix rows, extraction confidence, citation audit |
| 6 | Paywalls and access inequality | 7/10 | Open-access sources (Semantic Scholar, arXiv, OpenAlex) |
| 7 | Source quality and credibility | 7/10 | Source adapters, enrichment, canonical paper schema |
| 8 | Organizational chaos (tracking 60+ papers) | 7/10 | Project as container, saved papers with status, matrix rows |
| 9 | AI tool fragmentation (5-tool stack) | 6/10 | Single integrated workflow: search → matrix → gaps → export |
| 10 | Research gap detection difficulty | 6/10 | Evidence-based gaps from matrix rows, mandatory paper IDs |
| 11 | Writing paralysis / structural confusion | 6/10 | Structured report sections, matrix as scaffolding |
| 12 | Emotional toll / imposter syndrome | 5/10 | Clear workflow steps, visible progress, seeded demo |

---

## Key Insight: The Trust Chain

The most important finding from this research is that the literature review
pain points form a **trust chain**:

```
Can't find right papers → Don't know if sources are good →
Can't organize what was found → Can't synthesize across papers →
AI invents citations → Can't verify output → Don't trust final product
```

Each weakness compounds the next. A tool that only solves one stage (e.g.,
paper discovery) leaves the researcher to fail at synthesis. A tool that
generates fluent text but fabricates citations is worse than no tool at all.

Our product's core differentiator must be that it preserves trust at every
stage: real papers from real sources → structured evidence matrix →
evidence-based gaps → citations validated against database → exportable
review with traceable references.

---

## Sources

1. "Mastering the Literature Review: Overcoming Common Academic Hurdles" — Galileon Destura, Medium (Feb 2026)
2. "According to Zhang et al., I Have No Idea What I'm Doing" — James Ga-as, Medium (Feb 2026)
3. "The Review of Related 'Literature' Problems" — John Marcellin Tan, Medium (Feb 2026)
4. "The 'Laundry List' Trap in Literature Reviews is CRAZY" — Earl Josh Delgado, Medium (Feb 2026)
5. "The expert who can't find the words" — Dr. Eleanor Pritchard, Substack (May 2026)
6. "How to (not) do a literature review" — LessWrong
7. "Best AI for Literature Review 2026: Tools" — ResearchGold (May 2026)
8. "AI Research Workflow: Best Tool for Each Research Stage" — AI Research Reviews (Apr 2026)
9. "How Researchers Are Actually Losing the Literature Review" — ScholarBits (2025)
10. "Audit Finds AI-Fabricated Citations Across Biomedical Papers" — Let's Data Science / The Lancet (May 2026)
11. "GPT-5's Source Problem: Why AI Hallucinates Citations" — Arsturn
12. "ChatGPT Fake Citations: Why AI Hallucinations Matter for Research" — CiteDash (Mar 2026)
13. "The 2026 AI Citation Hallucination Benchmark" — CiteDash (Apr 2026)
14. "The Growing Epidemic of Hallucinated Citations" — Plagiarism Today (Mar 2026)
15. "AI-hallucinated citations are creeping into papers" — The Decoder / The Lancet (May 2026)
16. "Why AI can't be trusted to write scientific reviews" — Nature / Cochrane (May 2026)
17. "Generative artificial intelligence for literature reviews" — arXiv:2605.16475
18. "Useful for Exploration, Risky for Precision" — arXiv:2605.10125
19. "Researcher Reports Generic GPT Agent Struggles with Literature Searches" — Digg/Reddit (May 2026)
20. "ChatGPT keeps making up quotes" — Financial Express / Reddit (Jul 2025)
21. "Influence of Topic Familiarity on Citation Fabrication" — PMC / NIH (2025)
22. "foundry-research" — GitHub (Mar 2026)
23. "Building Meta-Analysis Datasets with AI Assistance" — MAER-NET (Mar 2026)
24. "How a Clear Systematic Review Workflow Transformed an Overwhelmed MSc Student's Project" — SystematicReviewTools.app (Feb 2026)
25. "The Complete Systematic Review Guide" — Emirate Prestige (May 2026)
26. "Hallucinated citations and phantom references" — Pascal Vrticka, Substack (Jan 2026)
27. "How to Spot AI Hallucinations Like a Reference Librarian" — LLRX (Mar 2026)
28. "Scientists Warn AI Slop Is Wreaking Havoc in the Research World" — CNET (May 2026)
29. "How to Do a Systematic Literature Review with AI (2026)" — Prismer Blog (Apr 2026)
30. "AI Systematic Literature Review Tutorial Without Hallucination" — AI Tools Guidebook (May 2026)
