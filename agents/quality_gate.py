"""
agents/quality_gate.py  —  Stage 2b: Quality Gate
─────────────────────────────────────────────────────────────────────────────
Hard conditional between Generate and Publish.
ALL checks are deterministic (rules-based, no LLM).
A post that fails does NOT proceed to Publish; failures are logged.

Scoring (0.0–1.0 composite):
  word_count          : 0–1  (hard fail if out of range)
  required_sections   : 0–1  (hard fail if missing)
  keyword_density     : 0–1  (hard fail if out of range)
  meta_description    : 0–1  (warn if wrong length)
  title_length        : 0–1
  composite_score     : weighted average of above
─────────────────────────────────────────────────────────────────────────────
"""

from core.state import PipelineState, QualityGateResult


def run(state: PipelineState) -> PipelineState:
    print("\n[Stage 2b / Quality Gate] Running deterministic checks …")

    if not state.generation:
        state.errors.append("QualityGate: no generation output")
        state.aborted_at = "quality_gate"
        return state

    g = state.generation
    qg_cfg = state.config["quality_gate"]

    failures = []
    warnings = []
    component_scores = []

    # ── 1. Word count (hard fail) ─────────────────────────────────────────────
    min_wc = qg_cfg["min_word_count"]
    max_wc = qg_cfg["max_word_count"]
    if g.word_count < min_wc:
        failures.append(f"Word count too low: {g.word_count} < {min_wc}")
        component_scores.append(0.0)
    elif g.word_count > max_wc:
        failures.append(f"Word count too high: {g.word_count} > {max_wc}")
        component_scores.append(0.5)
    else:
        # Score within range: peak at midpoint
        midpoint = (min_wc + max_wc) / 2
        distance_ratio = abs(g.word_count - midpoint) / (midpoint - min_wc)
        component_scores.append(max(0.6, 1.0 - distance_ratio * 0.3))

    # ── 2. Required sections (hard fail if any missing) ───────────────────────
    required = [s.lower() for s in qg_cfg.get("required_sections", [])]
    actual_lower = [s.lower() for s in g.sections]
    missing = [s for s in required if not any(s in a for a in actual_lower)]
    if missing:
        # Report with original case for readability
        original_missing = [s for s in qg_cfg.get("required_sections", []) if s.lower() in missing]
        failures.append(f"Missing required sections: {original_missing}")
        component_scores.append(0.0)
    else:
        # Bonus for having more sections (more comprehensive coverage)
        section_score = min(1.0, 0.5 + len(g.sections) * 0.1)
        component_scores.append(section_score)

    # ── 3. Keyword density (hard fail if out of safe range) ───────────────────
    min_kd = qg_cfg["min_keyword_density"]
    max_kd = qg_cfg["max_keyword_density"]
    if g.keyword_density < min_kd:
        failures.append(
            f"Keyword density too low: {g.keyword_density:.2%} < {min_kd:.2%} "
            f"(keyword may be missing or underused)"
        )
        component_scores.append(0.0)
    elif g.keyword_density > max_kd:
        failures.append(
            f"Keyword density too high: {g.keyword_density:.2%} > {max_kd:.2%} "
            f"(potential keyword stuffing)"
        )
        component_scores.append(0.2)
    else:
        # Ideal is 1–2%
        ideal_centre = (min_kd + max_kd) / 2
        density_score = 1.0 - abs(g.keyword_density - ideal_centre) / ideal_centre
        component_scores.append(max(0.5, density_score))

    # ── 4. Meta description length (warn, not hard fail) ─────────────────────
    meta_len = len(g.meta_description)
    if meta_len < 120:
        warnings.append(f"Meta description short ({meta_len} chars; ideal 140–155)")
        component_scores.append(0.6)
    elif meta_len > 160:
        warnings.append(f"Meta description too long ({meta_len} chars; Google truncates >160)")
        component_scores.append(0.7)
    else:
        component_scores.append(1.0)

    # ── 5. Title length (SEO best practice: 50–60 chars) ─────────────────────
    title_len = len(g.title)
    if title_len < 30:
        warnings.append(f"Title very short ({title_len} chars)")
        component_scores.append(0.6)
    elif title_len > 70:
        warnings.append(f"Title may be truncated in SERPs ({title_len} chars)")
        component_scores.append(0.8)
    else:
        component_scores.append(1.0)

    # ── 6. Internal links present ─────────────────────────────────────────────
    if not g.internal_links_used:
        warnings.append("No internal links detected — add at least one for SEO")
        component_scores.append(0.5)
    else:
        component_scores.append(min(1.0, 0.7 + len(g.internal_links_used) * 0.1))

    # ── Composite score (weighted mean) ──────────────────────────────────────
    weights = [0.20, 0.25, 0.25, 0.10, 0.10, 0.10]
    composite = sum(s * w for s, w in zip(component_scores, weights))
    composite = round(composite, 3)

    min_score = qg_cfg.get("min_score", 0.65)
    if composite < min_score:
        failures.append(
            f"Composite quality score {composite:.2f} below minimum {min_score:.2f}"
        )

    passed = len(failures) == 0

    if passed:
        print(f"  ✓ Quality gate passed (score: {composite:.2f})")
    else:
        print(f"  ✗ Quality gate FAILED (score: {composite:.2f})")
        for f in failures:
            print(f"    → FAIL: {f}")
    for w in warnings:
        print(f"    → WARN: {w}")

    state.quality_gate = QualityGateResult(
        passed=passed,
        score=composite,
        failures=failures,
        warnings=warnings,
    )

    if not passed:
        state.aborted_at = "quality_gate"

    return state
