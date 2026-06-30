"""
pipeline/script_generator.py

VELOCI Stage 02 — Video Script Generation Engine

Takes ranked TrendCluster objects from Stage 01 and generates multiple
short-form video scripts per trend — ready for production.

For each trend, generates 3-5 scripts using different content angles:
  - Explainer    → "What is X and why it matters"
  - Hot-take     → "My controversial opinion on X"
  - Tutorial     → "How to use/leverage X right now"
  - Listicle     → "5 things about X you didn't know"
  - Storytime    → "The story behind X that nobody talks about"
  - Comparison   → "X vs Y — which one wins?"
  - Myth-bust    → "3 myths about X debunked"
  - News-flash   → "BREAKING: X just happened — here's what it means"

Each script includes:
  - Hook (first 3 seconds — make-or-break)
  - Body beats (key content points)
  - CTA (call to action)
  - Format + duration + platform target
  - Hashtags + content tags
  - Multi-dimensional scoring

Output:
  - Per-trend scripts (JSON)
  - Master ranked list across all trends (JSON + CSV)
  - Script archive log (appended each run)

No LLM dependency — uses intelligent template engine with trend data.
Can be upgraded to LLM generation by swapping _generate_body().
"""

from __future__ import annotations

import hashlib
import json
import os
import csv
import random
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple

from loguru import logger


# ─── SCRIPT SCHEMA ───────────────────────────────────────────────────────────

@dataclass
class VideoScript:
    """
    A single production-ready video script generated from a trend.
    """
    # ── Identity ──────────────────────────────────────────────────────────────
    script_id: str                   # Unique hash ID
    trend_topic: str                 # Parent trend topic
    trend_score: float               # Parent trend composite score
    trend_tier: str                  # early / emerging / trending
    niche: str                       # tech_ai / finance / entertainment / etc.

    # ── Content ───────────────────────────────────────────────────────────────
    hook: str                        # Opening line (first 3 seconds)
    body_points: List[str]           # Key content beats (3-7 points)
    cta: str                         # Call to action (closing)
    full_script: str                 # Complete script text (hook + body + CTA)

    # ── Format ────────────────────────────────────────────────────────────────
    content_angle: str               # explainer / hot-take / tutorial / etc.
    format_type: str                 # vertical-video / carousel / talking-head
    duration: str                    # 15s / 30s / 60s / 90s
    platform_target: str             # reels / shorts / both / tiktok

    # ── Discovery ─────────────────────────────────────────────────────────────
    hashtags: List[str]              # Recommended hashtags (with #)
    content_tags: List[str]          # Internal topic categories
    seo_title: str                   # Optimized title for search/caption
    thumbnail_text: str              # Suggested text overlay for thumbnail

    # ── Scoring (0.0 - 1.0 each) ─────────────────────────────────────────────
    hook_score: float = 0.0          # How attention-grabbing the hook is
    trend_alignment: float = 0.0     # How well script matches trend data
    virality_potential: float = 0.0  # Predicted shareability
    format_fit: float = 0.0         # How well format matches content
    production_ease: float = 0.0     # How easy to produce (lower = harder)
    engagement_forecast: float = 0.0 # Predicted engagement rate
    composite_script_score: float = 0.0  # Weighted final score

    # ── Metadata ──────────────────────────────────────────────────────────────
    keywords: List[str] = field(default_factory=list)
    source_urls: List[str] = field(default_factory=list)
    generated_at: str = ""
    rank_in_trend: int = 0           # Rank within its parent trend
    global_rank: int = 0             # Rank across all scripts

    def to_dict(self) -> dict:
        """Serialize to JSON-safe dict."""
        return {
            "script_id": self.script_id,
            "trend_topic": self.trend_topic,
            "trend_score": round(self.trend_score, 4),
            "trend_tier": self.trend_tier,
            "niche": self.niche,
            "hook": self.hook,
            "body_points": self.body_points,
            "cta": self.cta,
            "full_script": self.full_script,
            "content_angle": self.content_angle,
            "format_type": self.format_type,
            "duration": self.duration,
            "platform_target": self.platform_target,
            "hashtags": self.hashtags,
            "content_tags": self.content_tags,
            "seo_title": self.seo_title,
            "thumbnail_text": self.thumbnail_text,
            "hook_score": round(self.hook_score, 4),
            "trend_alignment": round(self.trend_alignment, 4),
            "virality_potential": round(self.virality_potential, 4),
            "format_fit": round(self.format_fit, 4),
            "production_ease": round(self.production_ease, 4),
            "engagement_forecast": round(self.engagement_forecast, 4),
            "composite_script_score": round(self.composite_script_score, 4),
            "keywords": self.keywords,
            "source_urls": self.source_urls,
            "generated_at": self.generated_at,
            "rank_in_trend": self.rank_in_trend,
            "global_rank": self.global_rank,
        }

    def to_csv_row(self) -> list:
        """Flat row for CSV export."""
        return [
            self.global_rank,
            self.rank_in_trend,
            self.script_id[:12],
            self.trend_topic[:80],
            self.trend_tier,
            round(self.trend_score, 3),
            round(self.composite_script_score, 3),
            self.content_angle,
            self.hook[:120],
            " | ".join(self.body_points[:5]),
            self.cta[:100],
            self.duration,
            self.platform_target,
            self.format_type,
            self.seo_title[:100],
            self.thumbnail_text[:60],
            " ".join(self.hashtags[:10]),
            "|".join(self.content_tags[:5]),
            round(self.hook_score, 3),
            round(self.trend_alignment, 3),
            round(self.virality_potential, 3),
            round(self.format_fit, 3),
            round(self.production_ease, 3),
            round(self.engagement_forecast, 3),
            "|".join(self.keywords[:6]),
            "|".join(self.source_urls[:3]),
            self.niche,
            self.generated_at,
        ]

    @staticmethod
    def csv_header() -> list:
        return [
            "global_rank", "rank_in_trend", "script_id",
            "trend_topic", "trend_tier", "trend_score",
            "composite_script_score", "content_angle",
            "hook", "body_points", "cta",
            "duration", "platform_target", "format_type",
            "seo_title", "thumbnail_text",
            "hashtags", "content_tags",
            "hook_score", "trend_alignment",
            "virality_potential", "format_fit",
            "production_ease", "engagement_forecast",
            "keywords", "source_urls",
            "niche", "generated_at",
        ]


# ─── HOOK TEMPLATES ──────────────────────────────────────────────────────────
# Proven hook patterns organized by content angle.
# {topic}, {entity}, {kw}, {stat} are replaced at generation time.

HOOK_TEMPLATES: Dict[str, List[str]] = {
    "explainer": [
        "Here's why everyone is suddenly talking about {topic}",
        "{topic} — explained in {duration}",
        "If you don't understand {topic} yet, watch this",
        "What exactly is {topic}? Let me break it down",
        "Everything you need to know about {topic} in one video",
    ],
    "hot_take": [
        "Unpopular opinion: {topic} is NOT what you think it is",
        "I'm going to say what nobody else will about {topic}",
        "Everyone's wrong about {topic} — here's the truth",
        "This is my honest take on {topic} and you might disagree",
        "Hot take: {topic} is either genius or a complete disaster",
    ],
    "tutorial": [
        "Here's how to use {topic} before everyone else catches on",
        "Stop scrolling — I'm about to show you how {topic} actually works",
        "3 steps to leverage {topic} right now (it's free)",
        "I figured out {topic} so you don't have to — follow along",
        "In the next {duration}, I'll show you exactly how to do {topic}",
    ],
    "listicle": [
        "5 things about {topic} that will blow your mind",
        "{topic} — here are the top facts nobody tells you",
        "I found {stat} reasons why {topic} changes everything",
        "The top tools and resources for {topic} — save this",
        "Everything about {topic} ranked from worst to best",
    ],
    "storytime": [
        "The story behind {topic} is actually insane",
        "How {entity} changed {topic} forever — and nobody noticed",
        "I just discovered something about {topic} that changes everything",
        "The untold story of {topic} starts with a single moment",
        "Remember when nobody cared about {topic}? Look at it now",
    ],
    "comparison": [
        "{entity} vs the competition — which one actually wins?",
        "I tested {topic} against every alternative — here's what happened",
        "The real difference between {entity} and everyone else",
        "{topic}: which option is actually worth your time?",
        "I compared everything in {topic} — the winner surprised me",
    ],
    "myth_bust": [
        "STOP believing this myth about {topic}",
        "3 things everyone gets wrong about {topic}",
        "This common belief about {topic} is completely wrong",
        "Myth vs reality: the truth about {topic}",
        "I debunked the biggest lies about {topic}",
    ],
    "news_flash": [
        "BREAKING: {topic} just happened and here's what it means",
        "This changes EVERYTHING about {topic}",
        "{entity} just dropped a bombshell on {topic}",
        "Major update on {topic} that you need to know RIGHT NOW",
        "Nobody expected this from {topic} — but here we are",
    ],
}

# ─── BODY TEMPLATES ──────────────────────────────────────────────────────────

BODY_TEMPLATES: Dict[str, List[str]] = {
    "explainer": [
        "So {topic} is basically {summary_short}",
        "The key thing to understand is {point1}",
        "This matters because {point2}",
        "The data shows {point3}",
        "And here's the part nobody's covering — {point4}",
        "By now this is being discussed on {platforms}",
        "Experts are saying this could {prediction}",
    ],
    "hot_take": [
        "Okay so here's my take on {topic}",
        "Everyone's saying {consensus} but I think {contrarian}",
        "The real issue is {point1}",
        "What nobody's mentioning is {point2}",
        "Here's why I think this differently — {point3}",
        "I could be wrong but the evidence says {point4}",
    ],
    "tutorial": [
        "Step 1: {point1}",
        "Step 2: {point2}",
        "Step 3: {point3}",
        "Pro tip: {point4}",
        "The result? {outcome}",
        "This works because {reasoning}",
    ],
    "listicle": [
        "Number 1: {point1}",
        "Number 2: {point2}",
        "Number 3: {point3}",
        "Number 4: {point4}",
        "And the most important one: {point5}",
    ],
    "storytime": [
        "It all started when {origin}",
        "Then something unexpected happened — {turn}",
        "The key moment was when {point1}",
        "Nobody expected {point2}",
        "And now here we are with {current_state}",
    ],
    "comparison": [
        "On one side we have {entity_a}",
        "On the other side, {entity_b}",
        "In terms of {criteria1}, {comparison1}",
        "When it comes to {criteria2}, {comparison2}",
        "The clear winner for most people is {verdict}",
    ],
    "myth_bust": [
        "Myth number 1: {myth1} — Actually, {truth1}",
        "Myth number 2: {myth2} — The reality is {truth2}",
        "Myth number 3: {myth3} — Here's what's actually happening: {truth3}",
        "The data doesn't lie — {data_point}",
    ],
    "news_flash": [
        "Here's what just happened with {topic}",
        "The key detail everyone's missing is {point1}",
        "This affects {audience} because {point2}",
        "What this means going forward is {point3}",
        "I'll keep you updated — follow for the next development",
    ],
}

# ─── CTA TEMPLATES ───────────────────────────────────────────────────────────

CTA_TEMPLATES: Dict[str, List[str]] = {
    "explainer": [
        "Follow for more breakdowns like this",
        "Save this for later — you'll need it",
        "Share this with someone who needs to understand {topic}",
    ],
    "hot_take": [
        "Agree or disagree? Drop your take in the comments",
        "Tell me I'm wrong — I dare you 👇",
        "Follow for more honest takes the algorithm doesn't want you to see",
    ],
    "tutorial": [
        "Try this right now and comment your results",
        "Save this tutorial — you'll thank me later",
        "Follow for more step-by-step guides",
    ],
    "listicle": [
        "Which one was your favorite? Comment below",
        "Save this list before it gets buried in your feed",
        "Follow for more curated lists like this",
    ],
    "storytime": [
        "What do you think happens next? Follow for part 2",
        "Share this story — more people need to hear this",
        "Hit follow so you don't miss the next chapter",
    ],
    "comparison": [
        "Which side are you on? Comment your pick",
        "Share this with someone who's still deciding",
        "Follow for more honest comparisons",
    ],
    "myth_bust": [
        "Did any of these surprise you? Comment which one",
        "Share this with someone who still believes myth #1",
        "Follow for more truth bombs",
    ],
    "news_flash": [
        "Turn on notifications — this story is developing",
        "Follow for real-time updates on {topic}",
        "Share this before everyone else finds out",
    ],
}


# ─── SCORING WEIGHTS ─────────────────────────────────────────────────────────

SCRIPT_SCORE_WEIGHTS = {
    "hook_score":           0.25,  # Hook is king in short-form
    "trend_alignment":      0.20,  # Must match actual trend data
    "virality_potential":   0.20,  # Will people share this?
    "format_fit":           0.15,  # Right format for content type
    "engagement_forecast":  0.12,  # Predicted engagement rate
    "production_ease":      0.08,  # Lower barrier = faster to market
}


# ─── ANGLE SELECTION RULES ────────────────────────────────────────────────────
# Maps (tier, niche) combinations to preferred angles + their weights.

ANGLE_PRIORITY: Dict[str, Dict[str, List[Tuple[str, float]]]] = {
    "early": {
        "tech_ai": [
            ("explainer", 1.0), ("tutorial", 0.9), ("news_flash", 0.85),
            ("hot_take", 0.7), ("comparison", 0.6),
        ],
        "finance": [
            ("news_flash", 1.0), ("explainer", 0.9), ("hot_take", 0.8),
            ("tutorial", 0.7), ("myth_bust", 0.55),
        ],
        "entertainment": [
            ("news_flash", 1.0), ("hot_take", 0.9), ("storytime", 0.85),
            ("listicle", 0.7), ("comparison", 0.6),
        ],
        "_default": [
            ("explainer", 1.0), ("news_flash", 0.9), ("tutorial", 0.8),
            ("hot_take", 0.7), ("listicle", 0.6),
        ],
    },
    "emerging": {
        "tech_ai": [
            ("explainer", 1.0), ("tutorial", 0.95), ("comparison", 0.8),
            ("listicle", 0.7), ("myth_bust", 0.6),
        ],
        "finance": [
            ("explainer", 1.0), ("tutorial", 0.9), ("listicle", 0.8),
            ("hot_take", 0.75), ("comparison", 0.6),
        ],
        "entertainment": [
            ("hot_take", 1.0), ("listicle", 0.95), ("storytime", 0.85),
            ("comparison", 0.75), ("explainer", 0.6),
        ],
        "_default": [
            ("explainer", 1.0), ("tutorial", 0.9), ("listicle", 0.8),
            ("hot_take", 0.7), ("comparison", 0.6),
        ],
    },
    "trending": {
        "tech_ai": [
            ("hot_take", 1.0), ("comparison", 0.9), ("myth_bust", 0.85),
            ("tutorial", 0.7), ("listicle", 0.6),
        ],
        "finance": [
            ("myth_bust", 1.0), ("comparison", 0.9), ("hot_take", 0.85),
            ("tutorial", 0.7), ("explainer", 0.5),
        ],
        "entertainment": [
            ("storytime", 1.0), ("comparison", 0.95), ("hot_take", 0.85),
            ("listicle", 0.75), ("myth_bust", 0.6),
        ],
        "_default": [
            ("hot_take", 1.0), ("comparison", 0.9), ("myth_bust", 0.8),
            ("tutorial", 0.7), ("listicle", 0.6),
        ],
    },
}


# ─── DURATION TABLE ──────────────────────────────────────────────────────────

DURATION_MAP: Dict[str, str] = {
    "explainer":   "60s",
    "hot_take":    "30s",
    "tutorial":    "60s",
    "listicle":    "30s",
    "storytime":   "60s",
    "comparison":  "60s",
    "myth_bust":   "30s",
    "news_flash":  "15s",
}

FORMAT_TYPE_MAP: Dict[str, str] = {
    "explainer":   "talking-head",
    "hot_take":    "talking-head",
    "tutorial":    "screen-record",
    "listicle":    "carousel-video",
    "storytime":   "talking-head",
    "comparison":  "split-screen",
    "myth_bust":   "text-overlay",
    "news_flash":  "b-roll-voice",
}


# ─── GENERATOR ───────────────────────────────────────────────────────────────

class ScriptGenerator:
    """
    Generates multiple ranked video scripts per trend.
    Deterministic, no LLM dependency, high throughput.
    """

    def __init__(self):
        self._run_ts = datetime.now(timezone.utc).isoformat()

    def generate_for_trends(
        self,
        trends: list,
        niche: str,
        scripts_per_trend: int = 4,
    ) -> List[VideoScript]:
        """
        Generate scripts for a list of TrendCluster objects.

        Args:
            trends: Ranked TrendCluster list from Stage 01
            niche: Niche key (tech_ai, finance, entertainment)
            scripts_per_trend: Max scripts per trend (3-5)

        Returns:
            List of VideoScript objects, ranked globally.
        """
        all_scripts: List[VideoScript] = []

        for trend in trends:
            trend_dict = trend.to_dict() if hasattr(trend, "to_dict") else trend
            trend_scripts = self._generate_trend_scripts(
                trend_dict, niche, scripts_per_trend
            )
            all_scripts.extend(trend_scripts)

        # Score all scripts
        for script in all_scripts:
            self._score_script(script)

        # Rank within each trend
        by_trend: Dict[str, List[VideoScript]] = {}
        for s in all_scripts:
            by_trend.setdefault(s.trend_topic, []).append(s)
        for topic, scripts in by_trend.items():
            scripts.sort(key=lambda s: s.composite_script_score, reverse=True)
            for i, s in enumerate(scripts, 1):
                s.rank_in_trend = i

        # Global rank
        all_scripts.sort(key=lambda s: s.composite_script_score, reverse=True)
        for i, s in enumerate(all_scripts, 1):
            s.global_rank = i

        logger.info(
            f"[ScriptGen] Generated {len(all_scripts)} scripts "
            f"for {len(trends)} trends (niche={niche})"
        )
        return all_scripts

    def _generate_trend_scripts(
        self,
        trend: dict,
        niche: str,
        max_scripts: int,
    ) -> List[VideoScript]:
        """
        Generate scripts for a single trend using real content data.

        Content-aware: reads source_captions, mentioned_tools, key_claims,
        content_examples and engagement_stats from the enriched TrendCluster
        to produce scripts grounded in actual scraped data.
        """
        topic = trend.get("topic", "Unknown Trend")
        tier = trend.get("tier", "emerging")
        trend_score = trend.get("composite_score", 0.0)
        keywords = trend.get("keywords", [])
        entities = trend.get("entities", [])
        hashtags = trend.get("suggested_hashtags", [])
        source_urls = trend.get("source_urls", [])
        platforms = trend.get("platforms", [])
        summary = trend.get("summary", "")
        sentiment = trend.get("sentiment_score", 0.5)

        # ── NEW: Rich content analysis data ──────────────────────────────
        source_captions = trend.get("source_captions", [])
        mentioned_tools = trend.get("mentioned_tools", [])
        key_claims = trend.get("key_claims", [])
        content_examples = trend.get("content_examples", [])
        engagement_stats = trend.get("engagement_stats", {})
        top_comments = trend.get("top_comments_digest", [])
        sources_raw = trend.get("sources", [])

        # Build a context object with all real data for body generation
        content_ctx = {
            "topic": topic,
            "keywords": keywords,
            "entities": entities,
            "platforms": platforms,
            "summary": summary,
            "sentiment": sentiment,
            "captions": source_captions,
            "tools": mentioned_tools,
            "claims": key_claims,
            "examples": content_examples,
            "stats": engagement_stats,
            "comments": top_comments,
            "sources": sources_raw,
        }

        # Get the entity/keyword references
        entity = entities[0] if entities else (
            keywords[0] if keywords else topic[:30]
        )
        kw2 = keywords[1] if len(keywords) > 1 else "the industry"
        kw3 = keywords[2] if len(keywords) > 2 else "everyone"

        # Select angles by priority for this tier + niche
        tier_key = tier if tier in ANGLE_PRIORITY else "emerging"
        angles_with_weights = ANGLE_PRIORITY.get(
            tier_key, ANGLE_PRIORITY["emerging"]
        ).get(niche, ANGLE_PRIORITY[tier_key]["_default"])

        scripts: List[VideoScript] = []

        for angle_name, angle_weight in angles_with_weights[:max_scripts]:
            # ── Build hook (content-aware) ────────────────────────────────
            hook_templates = HOOK_TEMPLATES.get(angle_name, HOOK_TEMPLATES["explainer"])
            hook_idx = hash(f"{topic}_{angle_name}") % len(hook_templates)
            hook_raw = hook_templates[hook_idx]

            duration = DURATION_MAP.get(angle_name, "30s")
            short_topic = topic[:50] if len(topic) > 50 else topic

            # Use tools in hooks when available
            hook_entity = entity
            if mentioned_tools and angle_name in ("tutorial", "comparison", "listicle"):
                hook_entity = mentioned_tools[0]

            hook = hook_raw.format(
                topic=short_topic,
                entity=hook_entity,
                kw=kw2,
                stat=str(len(mentioned_tools) or len(platforms)),
                duration=duration,
            )

            # ── Build body points (content-aware) ─────────────────────────
            body_points = self._build_body_points(
                angle_name, content_ctx,
            )

            # ── Build CTA ────────────────────────────────────────────────
            cta_templates = CTA_TEMPLATES.get(angle_name, CTA_TEMPLATES["explainer"])
            cta_idx = hash(f"{topic}_{angle_name}_cta") % len(cta_templates)
            cta = cta_templates[cta_idx].format(topic=short_topic)

            # ── Full script assembly ──────────────────────────────────────
            full_script = f"[HOOK] {hook}\n\n"
            full_script += "[BODY]\n"
            for i, point in enumerate(body_points, 1):
                full_script += f"  {i}. {point}\n"
            full_script += f"\n[CTA] {cta}"

            # ── SEO title ────────────────────────────────────────────────
            seo_title = self._build_seo_title(angle_name, short_topic, entity)

            # ── Thumbnail text ───────────────────────────────────────────
            thumbnail_text = self._build_thumbnail_text(
                angle_name, short_topic, entity
            )

            # ── Content tags ─────────────────────────────────────────────
            content_tags = self._build_content_tags(
                niche, angle_name, keywords, tier
            )
            # Add tools as tags too
            for tool in mentioned_tools[:3]:
                tool_tag = tool.lower().replace(" ", "-")
                if tool_tag not in content_tags:
                    content_tags.append(tool_tag)

            # ── Script hashtags (trend hashtags + angle-specific) ─────────
            script_hashtags = list(hashtags[:8])
            # Add tool hashtags
            for tool in mentioned_tools[:3]:
                tag = f"#{tool.lower().replace(' ', '')}"
                if tag not in script_hashtags:
                    script_hashtags.append(tag)
            angle_tags = {
                "tutorial": ["#tutorial", "#howto", "#learnontiktok"],
                "hot_take": ["#hottake", "#unpopularopinion", "#debate"],
                "listicle": ["#top5", "#mustknow", "#savethis"],
                "news_flash": ["#breaking", "#news", "#update"],
                "myth_bust": ["#mythbusted", "#factcheck", "#truth"],
                "storytime": ["#storytime", "#themoreyouknow"],
                "comparison": ["#versus", "#comparison", "#review"],
                "explainer": ["#explained", "#breakdown", "#learnwitme"],
            }
            for at in angle_tags.get(angle_name, [])[:2]:
                if at not in script_hashtags:
                    script_hashtags.append(at)

            # Platform target based on duration
            if duration == "15s":
                platform_target = "reels"
            elif duration in ("30s", "60s"):
                platform_target = "both"  # reels + shorts
            else:
                platform_target = "shorts"

            # ── Build script ID ──────────────────────────────────────────
            script_id = hashlib.md5(
                f"{topic}::{angle_name}::{niche}::{self._run_ts}".encode()
            ).hexdigest()[:16]

            script = VideoScript(
                script_id=script_id,
                trend_topic=topic,
                trend_score=trend_score,
                trend_tier=tier,
                niche=niche,
                hook=hook,
                body_points=body_points,
                cta=cta,
                full_script=full_script,
                content_angle=angle_name,
                format_type=FORMAT_TYPE_MAP.get(angle_name, "talking-head"),
                duration=duration,
                platform_target=platform_target,
                hashtags=script_hashtags,
                content_tags=content_tags,
                seo_title=seo_title,
                thumbnail_text=thumbnail_text,
                keywords=keywords[:8],
                source_urls=source_urls[:5],
                generated_at=self._run_ts,
            )

            # Attach metadata for scoring
            script._angle_weight = angle_weight  # type: ignore
            script._content_ctx = content_ctx     # type: ignore
            scripts.append(script)

        return scripts

    # ─── CONTENT-AWARE BODY BUILDER ──────────────────────────────────────────

    def _build_body_points(
        self,
        angle: str,
        ctx: dict,
    ) -> List[str]:
        """
        Build script body points from REAL content data.

        Uses source_captions, mentioned_tools, key_claims, content_examples,
        and engagement_stats to produce body points grounded in actual
        scraped content rather than generic templates.
        """
        topic = ctx["topic"][:50]
        keywords = ctx.get("keywords", [])
        entities = ctx.get("entities", [])
        platforms = ctx.get("platforms", [])
        sentiment = ctx.get("sentiment", 0.5)
        captions = ctx.get("captions", [])
        tools = ctx.get("tools", [])
        claims = ctx.get("claims", [])
        examples = ctx.get("examples", [])
        stats = ctx.get("stats", {})
        comments = ctx.get("comments", [])
        sources = ctx.get("sources", [])

        # Derived values
        entity = entities[0] if entities else (keywords[0] if keywords else topic)
        kw2 = keywords[1] if len(keywords) > 1 else "the space"
        platform_str = ", ".join(
            p.replace("_", " ").title() for p in platforms[:3]
        ) or "social media"
        tools_str = ", ".join(tools[:4]) if tools else None
        total_views = stats.get("total_views", 0)
        total_likes = stats.get("total_likes", 0)

        # Format big numbers
        def _fmt(n: int) -> str:
            if n >= 1_000_000:
                return f"{n / 1_000_000:.1f}M"
            if n >= 1_000:
                return f"{n / 1_000:.0f}K"
            return str(n)

        # Extract a usable caption snippet (first meaningful one)
        best_caption = ""
        for cap in captions:
            if len(cap) >= 30 and not cap.startswith("http"):
                best_caption = cap[:150]
                break

        # ── EXPLAINER ────────────────────────────────────────────────────
        if angle == "explainer":
            points = []
            if tools_str:
                points.append(f"This trend is centered around {tools_str} — tools that are reshaping {kw2}")
            else:
                points.append(f"{topic} is gaining real traction across {platform_str}")

            if best_caption:
                points.append(f"One creator put it this way: \"{best_caption[:100]}\"")
            elif claims:
                points.append(f"Here's the key insight: {claims[0][:120]}")

            if total_views > 1000:
                points.append(f"Combined, the content around this has pulled {_fmt(total_views)} views and {_fmt(total_likes)} likes")

            if claims and len(claims) > 1:
                points.append(f"What the data shows: {claims[1][:120]}")
            else:
                points.append(f"The main keywords driving discovery: {', '.join(keywords[:4])}")

            if examples:
                points.append(f"Real example: {examples[0][:120]}")

            if comments:
                points.append(f"The audience reaction: \"{comments[0][:100]}\"")
            else:
                sent_read = "positive" if sentiment > 0.6 else "mixed" if sentiment > 0.4 else "controversial"
                points.append(f"The overall sentiment is {sent_read} — here's what to watch next")

            return points

        # ── HOT TAKE ─────────────────────────────────────────────────────
        elif angle == "hot_take":
            points = [f"So {topic} is everywhere right now — but here's my honest take"]

            if tools and len(tools) >= 2:
                points.append(f"Everyone's hyping {tools[0]} but sleeping on {tools[1]}")
            elif best_caption:
                points.append(f"People are saying: \"{best_caption[:80]}\" — but I think it's more nuanced")

            if claims:
                points.append(f"The claim is: {claims[0][:100]} — but let me challenge that")
            else:
                points.append(f"What nobody's mentioning is how {kw2} fits into the picture")

            if total_views > 5000:
                points.append(f"This already has {_fmt(total_views)} views — so clearly people care")

            if comments:
                points.append(f"Even the comments are saying: \"{comments[0][:80]}\"")

            sent_read = "overwhelmingly positive" if sentiment > 0.6 else "divided" if sentiment > 0.4 else "pushing back"
            points.append(f"The community is {sent_read} — and that tells you everything")
            return points

        # ── TUTORIAL ─────────────────────────────────────────────────────
        elif angle == "tutorial":
            points = [f"Let me show you exactly how to use {topic} right now"]

            if tools:
                for i, tool in enumerate(tools[:3], 1):
                    if examples and i <= len(examples):
                        points.append(f"Step {i}: Open {tool} — {examples[i-1][:80]}")
                    else:
                        points.append(f"Step {i}: Start with {tool}")
            else:
                points.append(f"Step 1: Understand what {entity} does and why it matters")
                points.append(f"Step 2: Look into {kw2} — that's where the practical value is")
                if examples:
                    points.append(f"Step 3: {examples[0][:100]}")
                else:
                    points.append(f"Step 3: Apply it to your own workflow and test the results")

            if claims:
                points.append(f"Pro tip from the source content: {claims[0][:100]}")
            else:
                points.append(f"Pro tip: the insiders are already using these keywords — {', '.join(keywords[:3])}")

            if total_views > 1000:
                points.append(f"This approach already has {_fmt(total_views)} views of validation behind it")

            return points

        # ── LISTICLE ─────────────────────────────────────────────────────
        elif angle == "listicle":
            points = [f"Here are the top things about {topic} you need to know"]

            # Use tools as list items when available
            if tools:
                for i, tool in enumerate(tools[:4], 1):
                    points.append(f"#{i}: {tool} — a key player in {topic}")
                if claims:
                    points.append(f"Bonus: {claims[0][:100]}")
            # Otherwise use claims/captions
            elif claims:
                for i, claim in enumerate(claims[:4], 1):
                    points.append(f"#{i}: {claim[:100]}")
            else:
                for i, kw in enumerate(keywords[:4], 1):
                    points.append(f"#{i}: {kw.title()} — a critical piece of the puzzle")

            if total_views > 1000:
                points.append(f"This content has {_fmt(total_views)} views — save this while it's fresh")

            return points

        # ── STORYTIME ────────────────────────────────────────────────────
        elif angle == "storytime":
            points = [f"Here's the story behind {topic} that nobody's telling you"]

            if best_caption:
                points.append(f"It started with this: \"{best_caption[:100]}\"")
            else:
                points.append(f"It started when {entity} caught everyone's attention")

            if tools:
                points.append(f"Then {tools[0]} entered the picture and changed everything")

            if claims:
                points.append(f"The turning point: {claims[0][:100]}")

            points.append(f"Now it's trending across {platform_str}")

            if comments:
                points.append(f"And people are reacting: \"{comments[0][:80]}\"")
            else:
                points.append(f"We're still early — {topic} is just getting started")

            return points

        # ── COMPARISON ───────────────────────────────────────────────────
        elif angle == "comparison":
            if tools and len(tools) >= 2:
                a, b = tools[0], tools[1]
            else:
                a = entity
                b = kw2 if kw2 != "the space" else (keywords[2] if len(keywords) > 2 else "alternatives")

            points = [f"Let's compare the key players in {topic}"]
            points.append(f"On one side: {a}")
            points.append(f"On the other: {b}")

            if claims:
                points.append(f"The data says: {claims[0][:100]}")

            if total_views > 1000:
                points.append(f"Combined creator content: {_fmt(total_views)} views — this matters to people")

            sent_read = "favoring " + a if sentiment > 0.6 else "split" if sentiment > 0.4 else "leaning toward " + b
            points.append(f"The community verdict is {sent_read}")

            return points

        # ── MYTH BUST ────────────────────────────────────────────────────
        elif angle == "myth_bust":
            points = []

            if claims and len(claims) >= 2:
                points.append(f"Myth 1: \"{claims[0][:80]}\" — here's what's ACTUALLY happening")
                points.append(f"Myth 2: Only {entity} matters — WRONG, look at {kw2}")
                points.append(f"Myth 3: It's too late — NO, {_fmt(total_views)} views proves we're still early")
            else:
                points.append(f"Myth 1: {topic} is overhyped — FALSE, the data says otherwise")
                points.append(f"Myth 2: Only {entity} matters — WRONG, {kw2} is just as important")
                points.append(f"Myth 3: It's too late to jump on {topic} — NO, we're still in the early window")

            if tools:
                points.append(f"The tools actually driving this: {', '.join(tools[:3])}")

            if comments:
                points.append(f"Even users are pushing back: \"{comments[0][:80]}\"")

            points.append(f"Don't fall for the noise — now you know the truth")
            return points

        # ── NEWS FLASH ───────────────────────────────────────────────────
        elif angle == "news_flash":
            points = [f"BREAKING: {topic} just went viral across {platform_str}"]

            if claims:
                points.append(f"The key detail: {claims[0][:120]}")
            else:
                points.append(f"The key detail: {entity} is at the center of this")

            if tools:
                points.append(f"Tools involved: {', '.join(tools[:3])}")

            if total_views > 1000:
                points.append(f"Already {_fmt(total_views)} views and counting")

            sent_read = "positive" if sentiment > 0.6 else "mixed" if sentiment > 0.4 else "heated"
            points.append(f"Early reaction: {sent_read} — I'll keep you posted")
            return points

        # ── FALLBACK ─────────────────────────────────────────────────────
        else:
            return [
                f"{topic} is trending right now",
                f"Key players: {entity}, {kw2}",
                f"Platforms: {platform_str}",
                f"Tools: {', '.join(tools[:3]) if tools else 'N/A'}",
            ]

    # ─── SEO & THUMBNAIL ─────────────────────────────────────────────────────

    @staticmethod
    def _build_seo_title(angle: str, topic: str, entity: str) -> str:
        """Optimized title for search and algorithm discovery."""
        templates = {
            "explainer": f"{topic} Explained — What You Need to Know in 2026",
            "hot_take": f"My Honest Take on {topic} (You Won't Agree)",
            "tutorial": f"How to {topic} — Step by Step Guide (2026)",
            "listicle": f"Top 5 Facts About {topic} You Didn't Know",
            "storytime": f"The Story Behind {topic} That Nobody Tells",
            "comparison": f"{entity} vs Everyone Else — Who Wins at {topic}?",
            "myth_bust": f"3 Myths About {topic} DEBUNKED",
            "news_flash": f"BREAKING: {topic} — What It Means For You",
        }
        return templates.get(angle, f"{topic} — Everything You Need to Know")

    @staticmethod
    def _build_thumbnail_text(angle: str, topic: str, entity: str) -> str:
        """Short, punchy text for video thumbnail overlay."""
        short = topic[:25]
        templates = {
            "explainer": f"{short} EXPLAINED",
            "hot_take": f"HOT TAKE: {short}",
            "tutorial": f"HOW TO: {short}",
            "listicle": f"TOP 5: {short}",
            "storytime": f"THE STORY OF {short}",
            "comparison": f"{entity[:15]} vs ???",
            "myth_bust": f"MYTHS BUSTED: {short}",
            "news_flash": f"🚨 {short}",
        }
        return templates.get(angle, short.upper())

    @staticmethod
    def _build_content_tags(
        niche: str, angle: str, keywords: List[str], tier: str
    ) -> List[str]:
        """Build internal content taxonomy tags."""
        tags = [niche, angle, tier]
        for kw in keywords[:3]:
            tag = kw.lower().replace(" ", "-")
            if len(tag) >= 3 and tag not in tags:
                tags.append(tag)
        return tags

    # ─── SCORING ENGINE ──────────────────────────────────────────────────────

    def _score_script(self, script: VideoScript) -> None:
        """
        Score a VideoScript on 6 dimensions and compute composite score.

        Scoring dimensions:
          1. Hook Score — pattern strength × keyword density
          2. Trend Alignment — how well script matches trend signals
          3. Virality Potential — trend velocity × cross-platform × tier
          4. Format Fit — angle appropriateness for niche + tier
          5. Engagement Forecast — predicted comment/share rate
          6. Production Ease — how quickly this can be filmed
        """
        # 1. Hook Score
        #    Longer hooks with keywords score higher. Questions score highest.
        hook = script.hook.lower()
        hook_len_score = min(len(hook) / 80, 1.0)  # Ideal hook = 60-80 chars
        has_question = 1.0 if "?" in hook else 0.0
        has_number = 1.0 if any(c.isdigit() for c in hook) else 0.0
        has_power_word = 1.0 if any(
            w in hook for w in [
                "secret", "nobody", "truth", "mistake", "hack",
                "insane", "breaking", "wrong", "free", "stop",
                "before", "need", "must", "blow", "mind",
            ]
        ) else 0.0
        kw_in_hook = sum(1 for kw in script.keywords[:5] if kw.lower() in hook)
        kw_density = min(kw_in_hook / max(len(script.keywords[:5]), 1), 1.0)

        # Bonus: tools in hook (makes it more specific)
        ctx = getattr(script, "_content_ctx", {})
        tools_in_hook = sum(
            1 for t in ctx.get("tools", [])[:5]
            if t.lower() in hook
        )
        tool_bonus = min(tools_in_hook * 0.15, 0.3)

        script.hook_score = min(1.0, (
            hook_len_score * 0.15 +
            has_question * 0.15 +
            has_number * 0.10 +
            has_power_word * 0.25 +
            kw_density * 0.15 +
            tool_bonus +
            0.2  # Base — every hook gets some credit
        ))

        # 2. Trend Alignment + Content Richness
        #    How much real content data made it into the script
        topic_words = set(script.trend_topic.lower().split()[:8])
        script_words = set(script.full_script.lower().split())
        overlap = len(topic_words & script_words)
        base_alignment = min(
            overlap / max(len(topic_words), 1), 1.0
        ) * 0.4 + (script.trend_score * 0.3)

        # Content richness bonus — scripts grounded in real data score higher
        richness = 0.0
        if ctx.get("tools"):
            richness += 0.08  # Used real tool names
        if ctx.get("claims"):
            richness += 0.06  # Used real claims/facts
        if ctx.get("captions"):
            richness += 0.06  # Referenced real captions
        if ctx.get("comments"):
            richness += 0.05  # Used audience feedback
        if ctx.get("stats", {}).get("total_views", 0) > 1000:
            richness += 0.05  # Had real engagement data

        script.trend_alignment = min(1.0, base_alignment + richness)

        # 3. Virality Potential
        #    Based on parent trend strength + angle weight
        angle_weight = getattr(script, "_angle_weight", 0.7)
        tier_boost = {"early": 1.0, "emerging": 0.8, "trending": 0.6}.get(
            script.trend_tier, 0.5
        )
        script.virality_potential = min(1.0, (
            script.trend_score * 0.4 +
            angle_weight * 0.3 +
            tier_boost * 0.3
        ))

        # 4. Format Fit
        #    Niche-angle match quality
        niche_angle_fit = {
            "tech_ai":       {"explainer": 0.95, "tutorial": 0.92, "comparison": 0.85, "hot_take": 0.78, "news_flash": 0.80, "listicle": 0.75, "myth_bust": 0.70, "storytime": 0.60},
            "finance":       {"news_flash": 0.95, "explainer": 0.90, "tutorial": 0.85, "myth_bust": 0.82, "hot_take": 0.78, "listicle": 0.72, "comparison": 0.70, "storytime": 0.55},
            "entertainment": {"hot_take": 0.95, "storytime": 0.92, "listicle": 0.88, "comparison": 0.82, "news_flash": 0.78, "explainer": 0.65, "tutorial": 0.55, "myth_bust": 0.60},
        }
        fit_table = niche_angle_fit.get(script.niche, niche_angle_fit["tech_ai"])
        script.format_fit = fit_table.get(script.content_angle, 0.6)

        # 5. Engagement Forecast
        #    Angles that provoke responses score higher + content richness boost
        engagement_by_angle = {
            "hot_take": 0.92,   # Controversy = comments
            "comparison": 0.85, # "Which side?" = comments
            "myth_bust": 0.82,  # "Really?!" = shares
            "tutorial": 0.78,   # Saves + shares
            "listicle": 0.75,   # Saves
            "news_flash": 0.72, # Shares
            "storytime": 0.70,  # Watch time
            "explainer": 0.68,  # Saves + watch time
        }
        base_engagement = engagement_by_angle.get(script.content_angle, 0.6)
        # Boost for early tier (novelty drives engagement)
        tier_engagement_boost = {"early": 0.08, "emerging": 0.04, "trending": 0.0}
        boost = tier_engagement_boost.get(script.trend_tier, 0.0)
        # Content richness engagement boost
        content_boost = min(richness * 0.5, 0.1)  # Rich content = more engaging
        script.engagement_forecast = min(1.0, base_engagement + boost + content_boost)

        # 6. Production Ease
        #    How quickly can this be filmed and published?
        production_scores = {
            "talking-head":    0.95,  # Just talk to camera
            "text-overlay":    0.90,  # Screen + text
            "b-roll-voice":    0.75,  # Need B-roll footage
            "carousel-video":  0.70,  # Need multiple shots
            "screen-record":   0.85,  # Just screen record
            "split-screen":    0.65,  # Complex editing
        }
        script.production_ease = production_scores.get(script.format_type, 0.7)

        # ── Composite Score (weighted sum) ────────────────────────────────
        script.composite_script_score = (
            script.hook_score      * SCRIPT_SCORE_WEIGHTS["hook_score"] +
            script.trend_alignment * SCRIPT_SCORE_WEIGHTS["trend_alignment"] +
            script.virality_potential * SCRIPT_SCORE_WEIGHTS["virality_potential"] +
            script.format_fit      * SCRIPT_SCORE_WEIGHTS["format_fit"] +
            script.engagement_forecast * SCRIPT_SCORE_WEIGHTS["engagement_forecast"] +
            script.production_ease * SCRIPT_SCORE_WEIGHTS["production_ease"]
        )


# ─── EXPORTER ────────────────────────────────────────────────────────────────

class ScriptExporter:
    """
    Exports generated scripts to JSON, CSV, and archive files.
    """

    @staticmethod
    def export_all(
        scripts: List[VideoScript],
        niche: str,
        output_dir: str = "output",
    ) -> Dict[str, str]:
        """
        Export scripts to multiple formats.

        Returns:
            Dict mapping format → file path
        """
        os.makedirs(output_dir, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        paths: Dict[str, str] = {}

        # ── 1. Full JSON (all scripts, all data) ─────────────────────────
        json_path = os.path.join(
            output_dir, f"veloci_scripts_{niche}_{ts}.json"
        )
        json_data = {
            "veloci_version": "2.0",
            "stage": "02_script_generation",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "niche": niche,
            "total_scripts": len(scripts),
            "scripts_per_trend": {},
            "all_scripts": [s.to_dict() for s in scripts],
        }

        # Group by trend for the per-trend view
        by_trend: Dict[str, list] = {}
        for s in scripts:
            by_trend.setdefault(s.trend_topic, []).append(s.to_dict())
        json_data["scripts_per_trend"] = by_trend

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2, default=str, ensure_ascii=False)
        paths["json"] = json_path

        # ── 2. CSV (flat, for spreadsheets) ──────────────────────────────
        csv_path = os.path.join(
            output_dir, f"veloci_scripts_{niche}_{ts}.csv"
        )
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(VideoScript.csv_header())
            for s in scripts:
                writer.writerow(s.to_csv_row())
        paths["csv"] = csv_path

        # ── 3. Top Scripts (best script per trend, master list) ──────────
        top_path = os.path.join(
            output_dir, f"veloci_top_scripts_{niche}_{ts}.json"
        )
        top_scripts = []
        seen_trends: set = set()
        for s in scripts:  # Already sorted by global rank
            if s.trend_topic not in seen_trends:
                seen_trends.add(s.trend_topic)
                top_scripts.append(s.to_dict())

        top_data = {
            "veloci_version": "2.0",
            "stage": "02_top_scripts",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "niche": niche,
            "description": "Best script per trend — production priority list",
            "total_top_scripts": len(top_scripts),
            "top_scripts": top_scripts,
        }
        with open(top_path, "w", encoding="utf-8") as f:
            json.dump(top_data, f, indent=2, default=str, ensure_ascii=False)
        paths["top_scripts"] = top_path

        # ── 4. Script Archive (append-only log of all generated scripts) ──
        archive_path = os.path.join(output_dir, f"script_archive_{niche}.jsonl")
        with open(archive_path, "a", encoding="utf-8") as f:
            for s in scripts:
                entry = s.to_dict()
                entry["_archived_at"] = datetime.now(timezone.utc).isoformat()
                f.write(json.dumps(entry, default=str, ensure_ascii=False) + "\n")
        paths["archive"] = archive_path

        logger.info(
            f"[ScriptExporter] Exported {len(scripts)} scripts for {niche}:\n"
            f"  JSON:        {json_path}\n"
            f"  CSV:         {csv_path}\n"
            f"  Top Scripts: {top_path}\n"
            f"  Archive:     {archive_path}"
        )

        return paths

    @staticmethod
    def print_top_scripts(scripts: List[VideoScript], max_show: int = 10) -> None:
        """Pretty-print top scripts to console."""
        print(f"\n{'━' * 70}")
        print(f"  🎬 VELOCI SCRIPT GENERATOR — Top {min(max_show, len(scripts))} Scripts")
        print(f"{'━' * 70}")

        for s in scripts[:max_show]:
            tier_emoji = {
                "early": "🟢", "emerging": "🟡",
                "trending": "🟠", "saturated": "🔴",
            }.get(s.trend_tier, "⚪")

            angle_emoji = {
                "explainer": "📖", "hot_take": "🔥", "tutorial": "🎓",
                "listicle": "📋", "storytime": "📕", "comparison": "⚖️",
                "myth_bust": "💥", "news_flash": "🚨",
            }.get(s.content_angle, "📝")

            print(f"\n  #{s.global_rank:2d} {angle_emoji} [{s.content_angle.upper()}]  "
                  f"Score: {s.composite_script_score:.3f}")
            print(f"      {tier_emoji} Trend: {s.trend_topic[:65]}")
            print(f"      🎣 Hook: \"{s.hook[:90]}\"")
            print(f"      ⏱️  {s.duration}  |  📱 {s.platform_target}  |  "
                  f"🎬 {s.format_type}")
            print(f"      📊 Hook:{s.hook_score:.2f}  "
                  f"Align:{s.trend_alignment:.2f}  "
                  f"Viral:{s.virality_potential:.2f}  "
                  f"Fit:{s.format_fit:.2f}  "
                  f"Engage:{s.engagement_forecast:.2f}")
            print(f"      🏷️  {' '.join(s.hashtags[:6])}")

        print(f"\n{'━' * 70}")
        print(f"  Total: {len(scripts)} scripts generated")
        print(f"{'━' * 70}\n")
