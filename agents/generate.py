"""
agents/generate.py  —  Stage 2: Generate
─────────────────────────────────────────────────────────────────────────────
Produces a full SEO-optimised blog post from the Research output.
Includes title, meta description, structured markdown body, and internal links.

The LLM writes the content; keyword density is then calculated DETERMINISTICALLY
(no AI involved) before the quality gate runs.
─────────────────────────────────────────────────────────────────────────────
"""

import re
from core.state import PipelineState, GenerateOutput
from core.knowledge_store import KnowledgeStore
from core.llm_client import LLMClient


def _slug_from_title(title: str) -> str:
    """Deterministic slug generation."""
    slug = title.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:80]  # cap length


def _count_words(text: str) -> int:
    """Deterministic word count."""
    return len(re.findall(r"\b\w+\b", text))


def _calc_keyword_density(body: str, keyword: str) -> float:
    """
    Deterministic keyword density calculation.
    density = occurrences / total_words
    Case-insensitive, whole-phrase match.
    """
    total_words = _count_words(body)
    if total_words == 0:
        return 0.0
    keyword_pattern = re.compile(re.escape(keyword), re.IGNORECASE)
    occurrences = len(keyword_pattern.findall(body))
    return round(occurrences / total_words, 4)


def _extract_h2_sections(markdown: str) -> list[str]:
    """Deterministic extraction of H2 headings from markdown."""
    return re.findall(r"^## (.+)$", markdown, re.MULTILINE)


def _extract_internal_links(markdown: str) -> list[str]:
    """Extract slugs used in markdown links."""
    return re.findall(r"\[.*?\]\((/[^\)]+)\)", markdown)


def run(state: PipelineState, store: KnowledgeStore, llm: LLMClient) -> PipelineState:
    print("\n[Stage 2 / Generate] Writing SEO blog post …")

    if not state.research:
        state.errors.append("Generate: no research output available")
        state.aborted_at = "generate"
        return state

    cfg = state.config
    topic_cfg = cfg["topic"]
    client_cfg = cfg["client"]
    r = state.research
    high_perf_structures = store.get_high_performing_structures()

    structure_hint = ""
    if high_perf_structures:
        structure_hint = f"\nPrevious high-scoring article structures to emulate:\n" + "\n".join(
            f"  - {s}" for s in high_perf_structures[:3]
        )

    internal_links_context = ""
    if r.internal_link_candidates:
        link_map = store.get_internal_link_map()
        lines = []
        for slug in r.internal_link_candidates[:5]:
            if slug in link_map:
                lines.append(f"  - [{link_map[slug]}](/{slug})")
        if lines:
            internal_links_context = "\nExisting posts to naturally link to:\n" + "\n".join(lines)

    system = f"""You are a professional SEO content writer for {client_cfg['name']}.
Write in this tone: {topic_cfg['tone']}
Target audience: {topic_cfg['target_audience']}
{structure_hint}
Produce well-structured, genuinely useful content — not generic fluff.
Return a JSON object only."""

    user = f"""Write a complete SEO blog post with these specifications:

Topic: {r.chosen_topic}
Primary keyword: "{r.primary_keyword}" (use naturally 4–8 times across the article)
Secondary keywords to include: {r.secondary_keywords}
Angle: {r.suggested_angle}
Do NOT cover these competitor angles: {r.competitor_angles}
{internal_links_context}

Target length: 800–1400 words
Must include: Introduction section, at least 3 body sections with H2 headings, Conclusion section.
Use H3 subheadings within body sections where helpful.
Include a call-to-action in the conclusion.

Return JSON with exactly these keys:
{{
  "title": "SEO-optimised title (50–60 chars, includes primary keyword)",
  "meta_description": "compelling meta description 140–155 chars, includes primary keyword",
  "body_markdown": "full article body in markdown starting from ## Introduction"
}}

The body_markdown must start immediately with ## Introduction (no title H1 needed — that's separate)."""

    result = llm.complete_json(system, user)

    body = result["body_markdown"]
    title = result["title"]
    slug = _slug_from_title(title)

    # ── All metrics calculated deterministically (no LLM involvement) ────────
    word_count = _count_words(body)
    keyword_density = _calc_keyword_density(body, r.primary_keyword)
    sections = _extract_h2_sections(body)
    internal_links_used = _extract_internal_links(body)

    print(f"  → Title: {title}")
    print(f"  → Words: {word_count} | KW density: {keyword_density:.2%} | Sections: {sections}")

    state.generation = GenerateOutput(
        title=title,
        slug=slug,
        meta_description=result["meta_description"],
        body_markdown=body,
        word_count=word_count,
        sections=sections,
        keyword_density=keyword_density,
        internal_links_used=internal_links_used,
    )

    return state
