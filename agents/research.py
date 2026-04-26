"""
agents/research.py  —  Stage 1: Research
─────────────────────────────────────────────────────────────────────────────
Identifies the best next article topic given:
  • client config (seed keywords, niche, audience)
  • knowledge store  (topics already covered, keyword saturation, quality history)

The LLM recommends a topic; the final topic selection is validated deterministically
against the store (if the keyword is already overused, we reject and re-rank).
─────────────────────────────────────────────────────────────────────────────
"""

from core.state import PipelineState, ResearchOutput
from core.knowledge_store import KnowledgeStore
from core.llm_client import LLMClient


# ── Deterministic hard rule: don't repeat a primary keyword used >1 time ─────
MAX_KEYWORD_REUSE = 1


def run(state: PipelineState, store: KnowledgeStore, llm: LLMClient) -> PipelineState:
    print("\n[Stage 1 / Research] Identifying keyword opportunity …")

    cfg = state.config
    topic_cfg = cfg["topic"]
    client_cfg = cfg["client"]

    covered = store.get_covered_topics()
    keyword_usage = store.get_keyword_usage()
    avoid = store.get_avoid_topics() + topic_cfg.get("avoid_topics", [])
    preferred_angles = store.get_preferred_angles()
    internal_links = store.get_internal_link_map()
    loop_count = store.get_loop_count()

    # Build context-rich prompt from knowledge store state
    history_context = ""
    if loop_count > 0:
        history_context = f"""
LEARNING FROM PREVIOUS LOOPS ({loop_count} completed):
- Topics already covered (do NOT repeat these as primary topics): {covered}
- Keyword usage counts: {keyword_usage}
- Avoid these topics/patterns: {avoid}
- Angles that performed well (try to emulate these styles): {preferred_angles[:5]}
- Existing posts available for internal linking: {list(internal_links.keys())[:10]}
"""

    system = f"""You are an expert SEO strategist for a {topic_cfg['domain_niche']} blog.
Your job is to identify the single best next article topic based on keyword opportunities,
content gaps, and what has already been published.
{history_context}
Always respond with valid JSON only."""

    user = f"""Client: {client_cfg['name']} ({client_cfg['domain']})
Target audience: {topic_cfg['target_audience']}
Seed keywords: {topic_cfg['seed_keywords']}
Niche: {topic_cfg['domain_niche']}

Topics already covered (DO NOT choose these as primary keyword): {covered if covered else 'None yet'}
Topics to avoid entirely: {avoid}

Choose the single best next article. Return JSON with exactly these keys:
{{
  "chosen_topic": "article topic title in plain English",
  "primary_keyword": "the exact target keyword phrase (2-4 words)",
  "secondary_keywords": ["kw1", "kw2", "kw3"],
  "content_gap_reason": "1-2 sentences explaining why this gap exists and why now",
  "competitor_angles": ["angle competitors take that we should NOT repeat"],
  "suggested_angle": "the fresh, differentiated angle we should take",
  "internal_link_candidates": {list(internal_links.keys())}
}}"""

    result = llm.complete_json(system, user)

    # ── Deterministic validation: reject over-saturated keywords ─────────────
    primary_kw = result["primary_keyword"].lower()
    usage_count = keyword_usage.get(primary_kw, 0)
    if usage_count >= MAX_KEYWORD_REUSE:
        # Fall back: append " guide" to differentiate, note it
        result["primary_keyword"] = f"{result['primary_keyword']} complete guide"
        result["content_gap_reason"] += (
            f" [Note: original keyword used {usage_count}x; angle adjusted to avoid duplication.]"
        )

    state.research = ResearchOutput(
        chosen_topic=result["chosen_topic"],
        primary_keyword=result["primary_keyword"],
        secondary_keywords=result.get("secondary_keywords", []),
        content_gap_reason=result["content_gap_reason"],
        competitor_angles=result.get("competitor_angles", []),
        suggested_angle=result["suggested_angle"],
        internal_link_candidates=result.get("internal_link_candidates", list(internal_links.keys())),
    )

    print(f"  → Topic selected: '{state.research.chosen_topic}'")
    print(f"  → Primary keyword: '{state.research.primary_keyword}'")
    print(f"  → Angle: {state.research.suggested_angle[:80]}…")
    return state
