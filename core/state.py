"""
core/state.py
─────────────────────────────────────────────────────────────────────────────
Single source of truth for pipeline state. Every stage receives and returns
a PipelineState instance. No global variables; state flows explicitly.
─────────────────────────────────────────────────────────────────────────────
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, UTC


@dataclass
class ResearchOutput:
    chosen_topic: str
    primary_keyword: str
    secondary_keywords: list[str]
    content_gap_reason: str          # why this topic was chosen over others
    competitor_angles: list[str]     # angles already covered (to differentiate)
    suggested_angle: str             # the fresh angle we'll take
    internal_link_candidates: list[str]  # slugs of existing posts to link to


@dataclass
class GenerateOutput:
    title: str
    slug: str
    meta_description: str
    body_markdown: str               # full article in markdown
    word_count: int
    sections: list[str]              # H2 headings extracted
    keyword_density: float           # deterministic calculation
    internal_links_used: list[str]


@dataclass
class QualityGateResult:
    passed: bool
    score: float                     # 0.0–1.0 composite
    failures: list[str]              # list of specific failure reasons
    warnings: list[str]


@dataclass
class PublishOutput:
    published: bool
    destination_path: str
    timestamp: str


@dataclass
class EvaluationOutput:
    overall_score: float
    semantic_coverage_score: float
    keyword_score: float
    readability_score: float
    structural_score: float
    internal_linking_score: float
    findings: list[str]              # specific, actionable findings
    strengths: list[str]
    improvements: list[str]


@dataclass
class PipelineState:
    """Passed sequentially through all five stages."""
    run_id: str = field(default_factory=lambda: datetime.now(UTC).strftime("%Y%m%d_%H%M%S"))
    config: dict = field(default_factory=dict)

    # Stage outputs — populated as the loop progresses
    research: Optional[ResearchOutput] = None
    generation: Optional[GenerateOutput] = None
    quality_gate: Optional[QualityGateResult] = None
    publish: Optional[PublishOutput] = None
    evaluation: Optional[EvaluationOutput] = None

    # Error tracking
    errors: list[str] = field(default_factory=list)
    aborted_at: Optional[str] = None   # stage name if pipeline was halted
