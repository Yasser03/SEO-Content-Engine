# JUDGEMENT.md

Honest answers to the four questions in the spec. Written after building the system, not before.

---

## 1. What would break your quality gate? What kind of content would slip through that should not?

**What would break it (false negatives — content that passes but shouldn't):**

The quality gate is deterministic and structural. It can be gamed by content that satisfies the measurable criteria while being genuinely bad. Specifically:

- **Keyword-stuffed but legal density.** A post could hit 1.2% density by using the keyword exactly the right number of times in awkward, unnatural sentences. The gate checks frequency, not naturalness. A sentence like *"AI productivity tools for startups are the AI productivity tools for startups founders choose"* passes the density check.

- **Correct section names, thin content.** The gate checks that `## Introduction` and `## Conclusion` exist — it doesn't check how many words those sections contain. A 700-word post with a two-sentence introduction and a one-sentence conclusion will pass.

- **Fabricated internal links.** The gate checks that markdown links to `/some-slug` exist in the body. It doesn't verify those slugs correspond to real published posts. The LLM could hallucinate plausible-sounding URLs.

- **Structurally complete, factually wrong.** The gate has no fact-checking layer. A post claiming a tool costs £5/month when it actually costs £500/month passes every check.

- **Plagiarised or near-duplicate content.** There's no similarity check against existing published posts or external sources. The gate will pass content that is structurally novel but semantically identical to a competitor article.

**What I'd add with more time:** A semantic deduplication check against the knowledge store (embedding similarity against covered slugs), a minimum-words-per-section check, and a link-resolution step that validates internal slugs against the actual internal link map.

---

## 2. What does the learning layer actually know after one loop that it did not before? Be specific.

After one complete loop, the knowledge store gains the following concrete, functional knowledge:

**1. The specific topic is permanently blocked.**
`topics_covered` now contains `{"slug": "ai-productivity-tools-startups-founders-guide", "primary_keyword": "AI productivity tools for startups", ...}`. When Research runs on loop 2, this keyword appears in the `covered` list injected into the LLM prompt. The model will not pick it again. The deterministic keyword reuse check (`MAX_KEYWORD_REUSE = 1`) acts as a hard backstop — if the LLM somehow picks the same keyword, the pipeline appends `" complete guide"` to force differentiation.

**2. The keyword usage counter is incremented.**
`keyword_usage["ai productivity tools for startups"] = 1`. On loop 2, Research sees this count and understands this keyword cluster has been addressed, biasing selection toward uncovered seed keywords.

**3. A high-performing section structure is recorded.**
Because the post scored 0.804 (above the 0.75 threshold), the sequence `Introduction → Why Most AI Tool Roundups Get This Wrong → The Tools That Actually Stuck → ...→ Conclusion` is stored in `high_performing_structures`. On loop 2, Generate receives this structure as an example in its system prompt: *"Previous high-scoring article structures to emulate."* This means loop 2's article will tend to open with a contrarian framing section rather than going straight to a list — a pattern the evaluator rewarded.

**4. Three specific improvement targets are recorded.**
`low_performing_patterns` now contains the three improvements flagged by the evaluator: missing secondary keyword coverage, too few internal links, and no FAQ section. On loop 2, Research can bias toward topics where these patterns are naturally addressed, and Generate has these as implicit anti-patterns to avoid.

**5. Five preferred angles are logged.**
The evaluator's `strengths` — concrete cost figures, opinionated naming, H3 usage — are stored in `preferred_angles`. The Research prompt for loop 2 explicitly includes these: *"Angles that performed well (try to emulate these styles)."*

**6. Rolling quality average is initialised.**
`avg_quality_score = 0.804`. From loop 3 onwards, this gives the system a quality baseline to detect regression — if a post scores below the rolling average, the deviation is visible in the store.

**What the learning layer does NOT yet know:** it doesn't know how the post performed with actual readers (traffic, bounce rate, time-on-page). All signals are proxy signals. The architecture is correct; the quality of the feedback improves significantly once real traffic data is piped in as an evaluation input.

---

## 3. What is the biggest risk in this architecture at scale: 500 posts in, running for 10 clients simultaneously?

**The biggest risk is knowledge store contention and context explosion — in that order.**

**Knowledge store contention (multi-client concurrency):**
The current store is a flat JSON file, one per client. That's fine for sequential single-client use. At 10 simultaneous clients, if two processes try to write to the same store at the same moment (possible in a scheduled/cron setup), you get a write collision and corrupt JSON. The fix is SQLite with WAL mode (handles concurrent reads, serialised writes) or a proper key-value store like Redis. The `KnowledgeStore` class is the only thing that needs to change — the rest of the pipeline is unaffected because it talks to the store through that abstraction.

**Context explosion in Research and Generate (500 posts in):**
By post 500, `topics_covered` is a list of 500 items being injected into the LLM's context window on every Research call. At ~20 tokens per entry, that's 10,000 tokens just for the covered topics list — before the actual prompt. This will hit context limits and massively increase per-call cost. The fix is to stop injecting raw lists and instead inject a summary: "covered topics in clusters X, Y, Z" derived from embedding-based grouping, or simply a keyword frequency histogram rather than the full slug list.

**Secondary risks:**
- **Quality drift**: with 500 posts the high_performing_structures list may contain patterns that were good at post 50 but are stale by post 500. There's no decay mechanism — patterns never expire.
- **LLM prompt injection via knowledge store**: if evaluation findings contain adversarial text (unlikely but possible if the LLM produces unusual output), that text gets written to the store and re-injected into future prompts. The store is trusted; it shouldn't be.
- **Topic exhaustion**: a narrow-niche client (say, a blog about one specific software product) will run out of genuinely new primary keywords within 50–100 posts. The research stage needs a semantic similarity threshold — not just exact keyword matching — to avoid near-duplicate articles that technically use different keywords but cover the same ground.

---

## 4. What did you cut to hit the timebox, and would you make the same call again?

**What I cut:**

**1. Real keyword research (SEMrush / Ahrefs / Google Search Console API)**
The Research stage uses the LLM to reason about keyword opportunities from seed terms, not actual search volume or competition data. In production, Research would call an SEO API to get volume, difficulty, and click-through estimates. I cut this because API setup (keys, billing, rate limits) would have eaten 45 minutes and produced no architectural insight. The slot in the architecture exists — `ResearchOutput` has a `content_gap_reason` field that in production would contain data-backed justification.

*Would I make the same call?* Yes. The architecture demonstrates the loop. The keyword data source is a swap-in, not a redesign.

**2. A scheduler / daemon mode**
The spec says "publishes fresh content daily." I built the loop as a single invocable unit, not a scheduler. In production this would be a cron job or a Cloud Scheduler trigger calling `python pipeline.py`. I cut this because scheduling is infrastructure, not system design — and the spec said "runs locally from a README in under 90 seconds for a single loop."

*Would I make the same call?* Yes. Adding `schedule` or `APScheduler` is three lines once the loop itself works.

**3. A Contentful/Ghost CMS integration**
The publish stage supports `local_markdown` and a generic `webhook` endpoint. A real CMS integration (Ghost Admin API, Contentful Management API) would require client-specific API keys and a non-trivial field mapping layer. I built the webhook path as the extension point — any CMS with a REST API is reachable through it.

*Would I make the same call?* Yes. The local markdown output is real and inspectable. A CMS integration would have added complexity without demonstrating anything new about the loop.

**4. Embedding-based deduplication**
Checking new topics for semantic similarity against published posts (not just exact keyword matching) would require either an embedding API call or a local model. I cut it in favour of shipping clean deterministic keyword matching, which covers 80% of the deduplication problem.

*Would I make the same call?* No, actually. This is a real gap. The quality gate section above describes exactly the failure mode it would prevent. If I were doing this again I'd add a lightweight sentence-transformer cosine similarity check (10 lines, no extra API) as a deterministic pre-check in Research. It would have taken 20 minutes.

**Overall:**
The cuts were mostly right. The one I'd reverse is the embedding deduplication — it's small effort for meaningful quality improvement. Everything else cut was infrastructure or integration work that would have added setup time without demonstrating system design judgment, which is what the task is actually testing.
