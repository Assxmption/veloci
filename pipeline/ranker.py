"""
pipeline/ranker.py

Trend ranking engine.

Takes TrendCluster objects from NLPProcessor and computes:
  1. Velocity score — rate of mention growth over the last window
  2. Cross-platform score — weighted confirmation across platforms
  3. Novelty score — already computed by NLPProcessor
  4. Sentiment score — already computed by NLPProcessor
  5. Engagement potential — historical engagement proxy
  6. Composite score — weighted sum of above → final rank

Then classifies each cluster into a tier:
  early     → act NOW, 12-48h before mainstream
  emerging  → good window, act within 24h
  trending  → still viable, saturating
  saturated → discard

The velocity calculation is the most important.
We compare mentions in the last 1h vs the previous N-1h.
A trend that's accelerating is more valuable than one that's
just popular.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from datetime import timezone
from typing import List, Optional, Dict
from loguru import logger

from config import (
    WEIGHTS, PLATFORM_TRUST, TREND_TIERS,
    MIN_COMPOSITE_SCORE, MAX_TRENDS_PER_NICHE
)
from pipeline.nlp_processor import TrendCluster


class TrendRanker:
    """
    Scores and ranks TrendCluster objects.
    Stateless — can be called repeatedly without side effects.
    """

    def rank(
        self,
        clusters: List[TrendCluster],
        historical_clusters: Optional[List[TrendCluster]] = None,
        top_n: int = MAX_TRENDS_PER_NICHE,
    ) -> List[TrendCluster]:
        """
        Score all clusters, filter by min threshold, return top N.

        Args:
            clusters: Current cycle's TrendClusters
            historical_clusters: Previous cycles' clusters for velocity calculation
            top_n: Maximum trends to return

        Returns:
            Ranked list of TrendClusters with scores filled in, best first.
        """
        if not clusters:
            return []

        logger.info(f"[Ranker] Scoring {len(clusters)} clusters...")

        for cluster in clusters:
            self._score_cluster(cluster, historical_clusters or [])

        for cluster in clusters:
            self._score_cluster(cluster, historical_clusters or [])

        # Filter by minimum composite score
        valid = [c for c in clusters if c.composite_score >= MIN_COMPOSITE_SCORE]

        # Sort by composite score descending
        valid.sort(key=lambda c: c.composite_score, reverse=True)

        # Classify into tiers
        for cluster in valid:
            cluster.tier = self._classify_tier(cluster.composite_score)

        logger.info(
            f"[Ranker] {len(valid)} valid trends after filtering. "
            f"Top score: {valid[0].composite_score:.3f}" if valid else ""
        )
        return valid[:top_n]

    def _score_cluster(
        self,
        cluster: TrendCluster,
        historical: List[TrendCluster],
    ) -> None:
        """Compute all sub-scores and composite score for a cluster."""

        # 1. Velocity score
        cluster.velocity_score = self._compute_velocity(cluster, historical)

        # 2. Cross-platform score
        cluster.cross_platform_score = self._compute_cross_platform(cluster)

        # 3. Novelty — already set by NLPProcessor, just ensure bounds
        cluster.novelty_score = max(0.0, min(1.0, cluster.novelty_score))

        # 4. Sentiment — already set by NLPProcessor
        cluster.sentiment_score = max(0.0, min(1.0, cluster.sentiment_score))

        # 5. Engagement potential
        cluster.engagement_potential = self._compute_engagement_potential(cluster)

        # 6. Composite weighted sum
        cluster.composite_score = (
            WEIGHTS["velocity"]            * cluster.velocity_score +
            WEIGHTS["cross_platform"]      * cluster.cross_platform_score +
            WEIGHTS["novelty"]             * cluster.novelty_score +
            WEIGHTS["sentiment"]           * cluster.sentiment_score +
            WEIGHTS["engagement_potential"]* cluster.engagement_potential
        )
        cluster.composite_score = round(min(cluster.composite_score, 1.0), 4)

    def _compute_velocity(
        self,
        cluster: TrendCluster,
        historical: List[TrendCluster],
    ) -> float:
        """
        Velocity = relative growth of mentions over last two time windows.

        Formula:
          current_window = signals published in last 1h
          previous_window = signals published 1-4h ago
          velocity = log(1 + current/max(1, previous)) / log(10)  → 0-1 scale

        If no historical data: use internal signal distribution
        (clusters with more RECENT signals score higher).
        """
        now = datetime.now(timezone.utc)
        one_hour_ago = now - timedelta(hours=1)
        four_hours_ago = now - timedelta(hours=4)

        # Count signals in windows
        recent = sum(
            1 for s in cluster.sources
            if s.scraped_at >= one_hour_ago
        )
        previous = sum(
            1 for s in cluster.sources
            if four_hours_ago <= s.scraped_at < one_hour_ago
        )

        # Baseline velocity from raw mention count (log-scaled)
        base = math.log1p(len(cluster.sources)) / math.log1p(50)

        if recent == 0 and previous == 0:
            return base * 0.3

        if previous == 0:
            # All signals are new — extremely fast-moving
            velocity = min(math.log1p(recent * 5) / math.log1p(25), 1.0)
        else:
            ratio = recent / max(previous, 1)
            velocity = min(math.log1p(ratio * 3) / math.log1p(10), 1.0)

        # Cross-validate with historical data if available
        if historical:
            prev_cluster = self._find_matching_cluster(cluster, historical)
            if prev_cluster:
                # How much did cross-platform score grow?
                growth = len(cluster.sources) - len(prev_cluster.sources)
                historical_boost = min(growth / 10, 0.3)
                velocity = min(velocity + historical_boost, 1.0)

        return round(velocity, 4)

    def _compute_cross_platform(self, cluster: TrendCluster) -> float:
        """
        Cross-platform score = weighted count of distinct platforms confirming the topic.

        More platforms = higher confidence it's a real trend (not just Reddit noise).
        Each platform contributes its trust weight, capped at 1.0 total.
        """
        seen_platforms = set()
        total_weight = 0.0
        max_possible = sum(sorted(PLATFORM_TRUST.values(), reverse=True)[:4])

        for signal in cluster.sources:
            platform = signal.platform
            if platform in seen_platforms:
                continue
            seen_platforms.add(platform)
            trust = PLATFORM_TRUST.get(platform, 0.65)
            total_weight += trust

        score = total_weight / max_possible
        return round(min(score, 1.0), 4)

    def _compute_engagement_potential(self, cluster: TrendCluster) -> float:
        """
        Engagement potential = log-scaled aggregate engagement across all signals.

        We can't know the exact future engagement, but high existing engagement
        on sources (upvotes, views, shares) is a proxy for topic interest.

        Additionally: positive sentiment boosts this score (shareable content).
        """
        if not cluster.sources:
            return 0.0

        total_engagement = sum(s.engagement_score for s in cluster.sources)
        # Log scale: 50 signals with 1 each = similar to 1 signal with 1000
        base = math.log1p(total_engagement) / math.log1p(1000)
        base = min(base, 1.0)

        # Sentiment multiplier: positive content is more shareable
        # 0.5 = neutral (no boost), 1.0 = max positive (30% boost)
        sentiment_boost = 1.0 + (cluster.sentiment_score - 0.5) * 0.3
        return round(min(base * sentiment_boost, 1.0), 4)

    def _classify_tier(self, score: float) -> str:
        """Map composite score to trend tier."""
        for tier, (low, high) in TREND_TIERS.items():
            if low <= score < high:
                return tier
        return "saturated"

    def _find_matching_cluster(
        self,
        cluster: TrendCluster,
        historical: List[TrendCluster],
    ) -> Optional[TrendCluster]:
        """
        Find the best-matching cluster from a previous cycle.
        Uses keyword overlap as a simple matching heuristic.
        """
        if not historical or not cluster.keywords:
            return None

        cluster_kws = set(cluster.keywords[:5])
        best_overlap = 0.0
        best_match = None

        for hc in historical:
            hc_kws = set(hc.keywords[:5])
            if not hc_kws:
                continue
            overlap = len(cluster_kws & hc_kws) / len(cluster_kws | hc_kws)
            if overlap > best_overlap and overlap >= 0.3:
                best_overlap = overlap
                best_match = hc

        return best_match
