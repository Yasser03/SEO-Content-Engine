"""
core/knowledge_store.py
─────────────────────────────────────────────────────────────────────────────
Persistent JSON knowledge base. Read at the START of every loop (to inform
Research) and written at the END (after Evaluate). This is what makes loop
N+1 smarter than loop N.

Design choice: flat JSON over SQLite for portability and human readability.
The trade-off is that querying becomes linear scan at large scale, but for
prototype use (< 500 posts) this is negligible.
─────────────────────────────────────────────────────────────────────────────
"""

import json
import os
from datetime import datetime, UTC
from pathlib import Path


DEFAULT_STORE = {
    "version": "1.0",
    "created_at": None,
    "last_updated": None,
    "topics_covered": [],            # list of {slug, title, primary_keyword, date}
    "keyword_usage": {},             # keyword → count of times used as primary
    "quality_history": [],           # list of {run_id, score, date}
    "learned_patterns": {
        "high_performing_structures": [],    # section patterns from high-scoring posts
        "low_performing_patterns": [],       # what to avoid
        "avg_quality_score": None,
        "best_score": None,
        "worst_score": None,
    },
    "avoid_topics": [],              # topics that scored poorly or were rejected
    "preferred_angles": [],          # angles that scored well
    "internal_link_map": {},         # slug → title for linking
}


class KnowledgeStore:
    def __init__(self, store_path: str = "store/knowledge.json"):
        self.store_path = Path(store_path)
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self._data = self._load()

    # ── I/O ──────────────────────────────────────────────────────────────────

    def _load(self) -> dict:
        if self.store_path.exists():
            with open(self.store_path, "r") as f:
                return json.load(f)
        import copy
        store = copy.deepcopy(DEFAULT_STORE)
        store["created_at"] = datetime.now(UTC).isoformat()
        return store

    def save(self):
        self._data["last_updated"] = datetime.now(UTC).isoformat()
        with open(self.store_path, "w") as f:
            json.dump(self._data, f, indent=2)

    # ── Read helpers (used by Research stage) ────────────────────────────────

    def get_covered_topics(self) -> list[str]:
        """Returns primary keywords in lowercase for consistent deduplication comparisons."""
        return [t["primary_keyword"].lower() for t in self._data["topics_covered"]]

    def get_covered_slugs(self) -> list[str]:
        return [t["slug"] for t in self._data["topics_covered"]]

    def get_keyword_usage(self) -> dict:
        return self._data["keyword_usage"]

    def get_avg_quality_score(self) -> float | None:
        return self._data["learned_patterns"]["avg_quality_score"]

    def get_avoid_topics(self) -> list[str]:
        return self._data["avoid_topics"]

    def get_preferred_angles(self) -> list[str]:
        return self._data["preferred_angles"]

    def get_internal_link_map(self) -> dict:
        return self._data["internal_link_map"]

    def get_high_performing_structures(self) -> list[str]:
        return self._data["learned_patterns"]["high_performing_structures"]

    def get_quality_history(self) -> list[dict]:
        return self._data["quality_history"]

    def get_loop_count(self) -> int:
        return len(self._data["quality_history"])

    # ── Write helpers (used by Learn stage) ──────────────────────────────────

    def record_published_post(self, slug: str, title: str, primary_keyword: str):
        self._data["topics_covered"].append({
            "slug": slug,
            "title": title,
            "primary_keyword": primary_keyword,
            "date": datetime.now(UTC).isoformat(),
        })
        # Update keyword usage counter
        kw = primary_keyword.lower()
        self._data["keyword_usage"][kw] = self._data["keyword_usage"].get(kw, 0) + 1

        # Add to internal link map
        self._data["internal_link_map"][slug] = title

    def record_evaluation(self, run_id: str, score: float, findings: list[str],
                           strengths: list[str], improvements: list[str],
                           sections: list[str]):
        self._data["quality_history"].append({
            "run_id": run_id,
            "score": score,
            "date": datetime.now(UTC).isoformat(),
        })

        patterns = self._data["learned_patterns"]

        # Update rolling average
        all_scores = [h["score"] for h in self._data["quality_history"]]
        patterns["avg_quality_score"] = round(sum(all_scores) / len(all_scores), 3)
        patterns["best_score"] = max(all_scores)
        patterns["worst_score"] = min(all_scores)

        # If this was a high-scoring post, record its structure as a good pattern
        if score >= 0.75 and sections:
            structure_sig = " → ".join(sections[:6])  # first 6 headings as signature
            if structure_sig not in patterns["high_performing_structures"]:
                patterns["high_performing_structures"].append(structure_sig)

        # Record improvements as things to avoid or fix
        for imp in improvements:
            if imp not in patterns["low_performing_patterns"]:
                patterns["low_performing_patterns"].append(imp)

        # Record strengths as preferred angles
        for s in strengths:
            if s not in self._data["preferred_angles"]:
                self._data["preferred_angles"].append(s)

    def add_avoided_topic(self, topic: str):
        if topic not in self._data["avoid_topics"]:
            self._data["avoid_topics"].append(topic)

    def summary(self) -> str:
        p = self._data["learned_patterns"]
        return (
            f"Loops completed: {self.get_loop_count()} | "
            f"Topics covered: {len(self._data['topics_covered'])} | "
            f"Avg score: {p['avg_quality_score']} | "
            f"Best: {p['best_score']} | "
            f"Worst: {p['worst_score']}"
        )
