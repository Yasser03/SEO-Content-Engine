"""
agents/evaluate.py  —  Stage 4: Evaluate
─────────────────────────────────────────────────────────────────────────────
Scores published content using proxy signals (no traffic data in prototype).

Scoring dimensions:
  1. semantic_coverage   — LLM judges whether the topic is thoroughly covered
  2. keyword_score       — deterministic: density, placement (title/intro/conclusion)
  3. readability         — deterministic: avg sentence length, paragraph length
  4. structural          — deterministic: section count, H3 usage, list usage
  5. internal_linking    — deterministic: number of internal links present

The LLM is used ONLY for semantic coverage (because that requires language understanding).
All other scores are deterministic.
─────────────────────────────────────────────────────────────────────────────
"""

import re
from core.state import PipelineState, EvaluationOutput
from core.llm_client import LLMClient


# ── Deterministic scorers ─────────────────────────────────────────────────────

def _score_keywords(body: str, primary_kw: str, secondary_kws: list[str]) -> tuple[float, list]:
    findings = []
    score_parts = []

    # Primary keyword in first 100 words?
    first_100 = " ".join(body.split()[:100])
    if primary_kw.lower() in first_100.lower():
        score_parts.append(1.0)
    else:
        score_parts.append(0.5)
        findings.append(f"Primary keyword '{primary_kw}' not found in first 100 words")

    # Primary keyword in last 100 words?
    last_100 = " ".join(body.split()[-100:])
    if primary_kw.lower() in last_100.lower():
        score_parts.append(1.0)
    else:
        score_parts.append(0.6)
        findings.append(f"Primary keyword not in conclusion — missed reinforcement opportunity")

    # Secondary keywords coverage
    found_secondary = sum(1 for kw in secondary_kws if kw.lower() in body.lower())
    coverage_ratio = found_secondary / max(len(secondary_kws), 1)
    score_parts.append(coverage_ratio)
    if coverage_ratio < 0.5:
        findings.append(f"Only {found_secondary}/{len(secondary_kws)} secondary keywords covered")

    return round(sum(score_parts) / len(score_parts), 3), findings


def _score_readability(body: str) -> tuple[float, list]:
    findings = []
    score_parts = []

    sentences = re.split(r"[.!?]+", body)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
    if not sentences:
        return 0.5, ["Could not parse sentences"]

    avg_sentence_len = sum(len(s.split()) for s in sentences) / len(sentences)

    # Ideal: 15–22 words per sentence
    if 15 <= avg_sentence_len <= 22:
        score_parts.append(1.0)
    elif avg_sentence_len < 10:
        score_parts.append(0.7)
        findings.append(f"Sentences very short (avg {avg_sentence_len:.1f} words) — may feel choppy")
    elif avg_sentence_len > 30:
        score_parts.append(0.5)
        findings.append(f"Sentences too long (avg {avg_sentence_len:.1f} words) — reduce for readability")
    else:
        score_parts.append(0.85)

    # Paragraph length: check for wall-of-text (>8 sentences in a row)
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
    long_paragraphs = [p for p in paragraphs if len(p.split(".")) > 6]
    if long_paragraphs:
        score_parts.append(0.6)
        findings.append(f"{len(long_paragraphs)} paragraph(s) are too dense — break them up")
    else:
        score_parts.append(1.0)

    # Passive voice proxy: "is/are/was/were + past participle" patterns
    passive_count = len(re.findall(r"\b(is|are|was|were)\s+\w+ed\b", body, re.IGNORECASE))
    if passive_count > 8:
        score_parts.append(0.7)
        findings.append(f"High passive voice usage ({passive_count} instances) — consider active voice")
    else:
        score_parts.append(1.0)

    return round(sum(score_parts) / len(score_parts), 3), findings


def _score_structure(sections: list[str], body: str) -> tuple[float, list]:
    findings = []
    score_parts = []

    # Section count
    section_count = len(sections)
    if section_count < 3:
        score_parts.append(0.4)
        findings.append(f"Only {section_count} H2 sections — add more for topic depth")
    elif section_count >= 5:
        score_parts.append(1.0)
    else:
        score_parts.append(0.75)

    # H3 subheadings present?
    h3_count = len(re.findall(r"^### .+$", body, re.MULTILINE))
    if h3_count >= 2:
        score_parts.append(1.0)
    elif h3_count == 1:
        score_parts.append(0.7)
    else:
        score_parts.append(0.5)
        findings.append("No H3 subheadings — add for better structure and featured snippet potential")

    # Lists (bullet or numbered)
    list_count = len(re.findall(r"^[-*\d]\.", body, re.MULTILINE))
    bullet_count = len(re.findall(r"^[-*] ", body, re.MULTILINE))
    total_lists = list_count + bullet_count
    if total_lists >= 3:
        score_parts.append(1.0)
    elif total_lists >= 1:
        score_parts.append(0.75)
    else:
        score_parts.append(0.5)
        findings.append("No lists detected — add bullet points or numbered lists for scannability")

    return round(sum(score_parts) / len(score_parts), 3), findings


def _score_internal_linking(internal_links: list[str]) -> tuple[float, list]:
    findings = []
    count = len(internal_links)
    if count == 0:
        return 0.2, ["No internal links — critical for SEO and site architecture"]
    elif count == 1:
        return 0.6, ["Only 1 internal link — aim for 2–4 per post"]
    elif count <= 4:
        return 1.0, []
    else:
        return 0.8, [f"{count} internal links may seem unnatural — consider trimming to 3–4"]


# ── LLM semantic coverage scorer ─────────────────────────────────────────────

def _score_semantic_coverage_llm(
    body: str, topic: str, primary_kw: str, secondary_kws: list, llm: LLMClient
) -> tuple[float, list, list]:

    system = "You are an expert SEO content evaluator. Respond with JSON only."
    user = f"""Evaluate this article on semantic coverage. Topic: "{topic}"
Primary keyword: "{primary_kw}"
Expected secondary themes: {secondary_kws}

Article body (first 1500 chars):
{body[:1500]}

Rate semantic coverage on a scale 0.0-1.0 and identify:
- What the article covers well (strengths)
- What's missing or underdeveloped (improvements)

Return JSON:
{{
  "score": 0.0,
  "strengths": ["strength 1", "strength 2"],
  "improvements": ["improvement 1", "improvement 2"]
}}"""

    result = llm.complete_json(system, user)
    return (
        float(result.get("score", 0.5)),
        result.get("strengths", []),
        result.get("improvements", []),
    )


# ── Main runner ───────────────────────────────────────────────────────────────

def run(state: PipelineState, llm: LLMClient) -> PipelineState:
    print("\n[Stage 4 / Evaluate] Scoring published content …")

    if not state.generation or not state.publish or not state.publish.published:
        state.errors.append("Evaluate: no published post to evaluate")
        state.aborted_at = "evaluate"
        return state

    g = state.generation
    r = state.research
    body = g.body_markdown

    # 1. Semantic coverage (LLM)
    sem_score, strengths, improvements = _score_semantic_coverage_llm(
        body, r.chosen_topic, r.primary_keyword, r.secondary_keywords, llm
    )

    # 2–5. Deterministic scores
    kw_score, kw_findings = _score_keywords(body, r.primary_keyword, r.secondary_keywords)
    read_score, read_findings = _score_readability(body)
    struct_score, struct_findings = _score_structure(g.sections, body)
    link_score, link_findings = _score_internal_linking(g.internal_links_used)

    all_findings = kw_findings + read_findings + struct_findings + link_findings

    # Weighted composite
    weights = {
        "semantic": 0.30,
        "keyword": 0.25,
        "readability": 0.20,
        "structural": 0.15,
        "linking": 0.10,
    }
    overall = round(
        sem_score * weights["semantic"] +
        kw_score * weights["keyword"] +
        read_score * weights["readability"] +
        struct_score * weights["structural"] +
        link_score * weights["linking"],
        3,
    )

    print(f"  → Overall: {overall:.2f} | Semantic: {sem_score:.2f} | KW: {kw_score:.2f} "
          f"| Readability: {read_score:.2f} | Structure: {struct_score:.2f} | Linking: {link_score:.2f}")

    state.evaluation = EvaluationOutput(
        overall_score=overall,
        semantic_coverage_score=sem_score,
        keyword_score=kw_score,
        readability_score=read_score,
        structural_score=struct_score,
        internal_linking_score=link_score,
        findings=all_findings,
        strengths=strengths,
        improvements=improvements,
    )

    return state
