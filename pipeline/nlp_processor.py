"""
pipeline/nlp_processor.py

NLP processing pipeline for raw signals.

This is where raw text from 8 sources becomes structured trend intelligence.

Pipeline:
  1. Clean & normalize text
  2. Extract named entities (people, orgs, products, events)
  3. Generate semantic embeddings (all-MiniLM-L6-v2, 384-dim)
  4. Cluster similar topics with DBSCAN (cosine distance)
  5. Extract keywords per cluster (TF-IDF)
  6. Score sentiment per cluster (VADER)
  7. Output: list of TrendCluster objects

Why DBSCAN:
  - No need to specify number of clusters upfront
  - Handles noise (outlier signals) gracefully
  - Cosine similarity works well with sentence embeddings
  - Can find clusters of any shape

Going beyond hashtags:
  Rather than grouping by hashtag co-occurrence, we embed the FULL TEXT
  of each signal into a semantic vector space. Signals about the same TOPIC
  (even if they use different keywords) will cluster together.
  This means "AI regulation", "OpenAI compliance", and "Anthropic EU rules"
  cluster as ONE topic even though they share no hashtags.
"""

from __future__ import annotations

import re
import string
from dataclasses import dataclass, field
from datetime import datetime
from datetime import timezone
from typing import List, Optional, Dict, Tuple

import numpy as np
from loguru import logger
from sentence_transformers import SentenceTransformer
from sklearn.cluster import DBSCAN
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from config import (
    EMBEDDING_MODEL, CLUSTERING_EPS, CLUSTERING_MIN_SAMPLES,
    MAX_KEYWORDS_PER_TREND, NICHES
)
from scrapers.base import RawSignal


# ─── STOPWORD LIST ─────────────────────────────────────────────────────────────
# Comprehensive blocklist: HTML fragments, CSS properties, platform noise,
# and generic filler words that pollute keyword extraction.
STOPWORDS = {
    # HTML / CSS / web scraping noise
    "class", "div", "span", "img", "src", "alt", "href", "http", "https",
    "style", "width", "height", "margin", "padding", "border", "auto",
    "font", "color", "size", "background", "display", "none", "block",
    "inline", "flex", "grid", "float", "left", "right", "top", "bottom",
    "center", "absolute", "relative", "position", "overflow", "hidden",
    "visible", "solid", "transparent", "bold", "italic", "normal",
    "family", "weight", "text", "align", "decoration", "transform",
    "transition", "opacity", "content", "cursor", "pointer", "wrapper",
    "container", "section", "header", "footer", "nav", "main", "aside",
    "article", "figure", "figcaption", "tbody", "thead", "table",
    "input", "button", "form", "label", "select", "option", "textarea",
    "post", "post thumbnail", "attachment", "wp", "wordpress",
    # Platform / scraping meta
    "type", "topic", "query", "rising", "rising related", "related",
    "autocomplete", "google autocomplete", "google", "youtube", "reddit",
    "instagram", "twitter", "tiktok", "platform", "trending", "rss",
    "feed", "posts", "active", "hashtag", "subscribe", "follow",
    "like", "share", "comment", "click", "read", "view", "views",
    "watch", "watching", "video", "photo", "image", "pic",
    # Time filler
    "just", "new", "now", "today", "yesterday", "latest", "recent",
    "2024", "2025", "2026", "2027",
    # Generic filler
    "one", "two", "three", "first", "second", "also", "get", "got",
    "make", "made", "making", "use", "using", "used", "way", "thing",
    "things", "know", "need", "want", "time", "day", "days", "year",
    "years", "people", "would", "could", "said", "says", "say",
    "really", "much", "many", "every", "even", "going", "come",
    "still", "back", "good", "best", "big", "high", "long", "take",
    "look", "think", "part",
}


# ─── OUTPUT SCHEMA ─────────────────────────────────────────────────────────────

@dataclass
class TrendCluster:
    """
    A group of signals that discuss the same underlying topic.
    This is the output unit of the NLP pipeline.
    """
    cluster_id: str
    topic: str                  # Human-readable topic label (best-fit title)
    keywords: List[str]         # TF-IDF extracted keywords
    entities: List[str]         # Named entities extracted from signals
    summary: str                # 1-sentence summary of the cluster

    sources: List[RawSignal]    # All raw signals in this cluster
    platforms: List[str]        # Unique platforms confirming this topic

    # Scores — computed downstream by ranker.py
    velocity_score: float = 0.0
    cross_platform_score: float = 0.0
    novelty_score: float = 0.0
    sentiment_score: float = 0.5  # 0=negative, 0.5=neutral, 1=positive
    engagement_potential: float = 0.0
    composite_score: float = 0.0

    # Metadata
    first_seen: datetime = field(default_factory=datetime.utcnow)
    niche: Optional[str] = None
    tier: str = "emerging"  # early / emerging / trending / saturated
    content_angles: List[str] = field(default_factory=list)

    # Content generation parameters (filled by _suggest_content_params)
    suggested_hashtags: List[str] = field(default_factory=list)
    suggested_hook: str = ""
    suggested_duration: str = "30s"   # "15s" / "30s" / "60s"
    suggested_format: str = "explainer"  # explainer / reaction / listicle / news
    platform_breakdown: Dict[str, int] = field(default_factory=dict)
    source_urls: List[str] = field(default_factory=list)

    # ── Content analysis (filled by _analyze_source_content) ─────────────────
    # These fields give Stage 02 (script generator) real data to work with.
    source_captions: List[str] = field(default_factory=list)       # Cleaned captions from top signals
    mentioned_tools: List[str] = field(default_factory=list)       # Products/tools mentioned (ChatGPT, Midjourney, etc.)
    key_claims: List[str] = field(default_factory=list)             # Core claims/facts extracted from signals
    top_comments_digest: List[str] = field(default_factory=list)    # Key observations from comment text
    content_examples: List[str] = field(default_factory=list)       # Specific examples/use-cases from signals
    engagement_stats: Dict[str, int] = field(default_factory=dict)  # Aggregate: total_views, total_likes, avg_comments

    # Embedding (kept for novelty comparison)
    centroid_embedding: Optional[np.ndarray] = None

    def to_dict(self) -> dict:
        return {
            "cluster_id": self.cluster_id,
            "topic": self.topic,
            "keywords": self.keywords,
            "entities": self.entities,
            "summary": self.summary,
            "platforms": self.platforms,
            "source_count": len(self.sources),
            # Scoring breakdown
            "velocity_score": round(self.velocity_score, 4),
            "cross_platform_score": round(self.cross_platform_score, 4),
            "novelty_score": round(self.novelty_score, 4),
            "sentiment_score": round(self.sentiment_score, 4),
            "engagement_potential": round(self.engagement_potential, 4),
            "composite_score": round(self.composite_score, 4),
            "tier": self.tier,
            "niche": self.niche,
            "first_seen": self.first_seen.isoformat(),
            # Content generation parameters
            "content_angles": self.content_angles,
            "suggested_hashtags": self.suggested_hashtags,
            "suggested_hook": self.suggested_hook,
            "suggested_duration": self.suggested_duration,
            "suggested_format": self.suggested_format,
            "platform_breakdown": self.platform_breakdown,
            "source_urls": self.source_urls,
            # Content analysis (for script generator)
            "source_captions": self.source_captions,
            "mentioned_tools": self.mentioned_tools,
            "key_claims": self.key_claims,
            "top_comments_digest": self.top_comments_digest,
            "content_examples": self.content_examples,
            "engagement_stats": self.engagement_stats,
            # Top 10 source signals (expanded for script gen)
            "sources": [s.to_dict() for s in self.sources[:10]],
        }


# ─── PROCESSOR ─────────────────────────────────────────────────────────────────

class NLPProcessor:
    """
    Transforms a list of RawSignal objects into TrendCluster objects.
    Stateful — loads models once and reuses them across cycles.
    """

    def __init__(self):
        logger.info(f"[NLP] Loading embedding model: {EMBEDDING_MODEL}")
        self._embedder = SentenceTransformer(EMBEDDING_MODEL)
        self._sentiment = SentimentIntensityAnalyzer()
        self._tfidf = TfidfVectorizer(
            max_features=5000,
            ngram_range=(1, 2),
            stop_words="english",
            min_df=1,
        )
        self._spacy = None
        logger.info("[NLP] Models loaded.")

    def _get_spacy(self):
        """Lazy-load spaCy (larger model) on first use."""
        if self._spacy is None:
            import spacy
            try:
                self._spacy = spacy.load("en_core_web_sm")
            except OSError:
                logger.warning("[NLP] spaCy model not found. Run: python -m spacy download en_core_web_sm")
                self._spacy = None
        return self._spacy

    def process(
        self,
        signals: List[RawSignal],
        existing_embeddings: Optional[List[np.ndarray]] = None,
    ) -> List[TrendCluster]:
        """
        Main entry point. Takes raw signals, returns trend clusters.

        Args:
            signals: Raw signals from all scrapers
            existing_embeddings: Embeddings from recently published content
                                 Used for novelty scoring

        Returns:
            List of TrendCluster objects, ready for ranking
        """
        if not signals:
            logger.warning("[NLP] No signals to process.")
            return []

        logger.info(f"[NLP] Processing {len(signals)} signals...")

        # 1. Clean text
        texts = [self._clean_text(s.full_text) for s in signals]
        valid_mask = [bool(t.strip()) for t in texts]

        valid_signals = [s for s, v in zip(signals, valid_mask) if v]
        valid_texts = [t for t, v in zip(texts, valid_mask) if v]

        if not valid_signals:
            return []

        # 2. Generate embeddings
        embeddings = self._embedder.encode(
            valid_texts,
            batch_size=64,
            show_progress_bar=False,
            normalize_embeddings=True,  # Normalize for cosine distance
        )

        # 3. Cluster
        cluster_labels = self._cluster(embeddings)

        # 4. Build TrendCluster objects from clusters
        clusters = self._build_clusters(
            valid_signals, valid_texts, embeddings, cluster_labels
        )

        # 5. Score novelty against existing content
        if existing_embeddings:
            for cluster in clusters:
                if cluster.centroid_embedding is not None:
                    cluster.novelty_score = self._compute_novelty(
                        cluster.centroid_embedding, existing_embeddings
                    )
                else:
                    cluster.novelty_score = 1.0
        else:
            for cluster in clusters:
                cluster.novelty_score = 1.0  # Everything is novel if no history

        logger.info(f"[NLP] Produced {len(clusters)} trend clusters")

        # 6. Screen by niche (remove off-topic clusters)
        if signals and signals[0].niche:
            clusters = self._screen_by_niche(clusters, signals[0].niche)
            logger.info(f"[NLP] {len(clusters)} clusters after niche screening")

        # 7. Fill content-gen parameters
        for cluster in clusters:
            self._fill_content_params(cluster)

        return clusters

    def _clean_text(self, text: str) -> str:
        """Clean and normalize text for embedding."""
        if not text:
            return ""
        # Remove HTML tags completely
        text = re.sub(r"<[^>]+>", " ", text)
        # Remove URLs
        text = re.sub(r"http\S+|www\S+", " ", text)
        # Remove user mentions
        text = re.sub(r"@\w+", " ", text)
        # Remove HTML entities
        text = re.sub(r"&\w+;", " ", text)
        text = re.sub(r"&#\d+;", " ", text)
        # Remove CSS/style fragments (common in RSS scraping)
        text = re.sub(r"\b\d+px\b", " ", text)
        text = re.sub(r"#[0-9a-fA-F]{3,8}\b", " ", text)  # Hex colors
        text = re.sub(r"\b(margin|padding|border|width|height|font|color|display|position|overflow|float|background)\s*[:;]\s*[^;]+[;]", " ", text)
        # Remove image/media attributes
        text = re.sub(r'(class|style|alt|src|href|width|height)\s*=\s*"[^"]*"', " ", text)
        # Normalise hashtags: #MachineLearning → machine learning
        text = re.sub(r"#([A-Za-z]+)", lambda m: m.group(1), text)
        # Remove excessive whitespace
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _cluster(self, embeddings: np.ndarray) -> np.ndarray:
        """
        Cluster embeddings using DBSCAN with cosine distance.
        Returns array of cluster labels (-1 = noise/singleton).
        """
        if len(embeddings) < 2:
            return np.zeros(len(embeddings), dtype=int)

        # Convert to cosine distance (embeddings are L2-normalized, so dot = cosine sim)
        # distance = 1 - cosine_similarity
        sim_matrix = np.dot(embeddings, embeddings.T)
        dist_matrix = 1.0 - np.clip(sim_matrix, -1.0, 1.0)

        db = DBSCAN(
            eps=CLUSTERING_EPS,
            min_samples=CLUSTERING_MIN_SAMPLES,
            metric="precomputed",
        )
        labels = db.fit_predict(dist_matrix)
        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
        logger.debug(f"[NLP] DBSCAN: {n_clusters} clusters, {(labels == -1).sum()} noise")
        return labels

    def _build_clusters(
        self,
        signals: List[RawSignal],
        texts: List[str],
        embeddings: np.ndarray,
        labels: np.ndarray,
    ) -> List[TrendCluster]:
        """Build TrendCluster objects from DBSCAN output."""
        from collections import defaultdict
        import hashlib

        # Group by label
        groups: Dict[int, List[int]] = defaultdict(list)
        for idx, label in enumerate(labels):
            groups[label].append(idx)

        clusters: List[TrendCluster] = []

        for label, indices in groups.items():
            group_signals = [signals[i] for i in indices]
            group_texts = [texts[i] for i in indices]
            group_embeddings = embeddings[indices]

            # Singletons (noise) still become clusters — lone signals can still trend
            # They just get lower cross-platform scores downstream

            # Centroid embedding = mean of member embeddings
            centroid = group_embeddings.mean(axis=0)
            centroid = centroid / (np.linalg.norm(centroid) + 1e-10)

            # TF-IDF keywords
            keywords = self._extract_keywords(group_texts)

            # Named entities
            entities = self._extract_entities(
                " ".join(group_texts[:5])  # Top 5 signals for NER
            )

            # ── DISTILLED TOPIC (not raw caption) ────────────────────────
            # Build a clean, descriptive topic from entities + keywords.
            # Priority: named entities > top keywords > best signal title.
            topic = self._distill_topic(group_signals, keywords, entities, centroid, group_embeddings)

            # Sentiment (aggregate across signals)
            sentiment = self._aggregate_sentiment(group_texts)

            # Unique platforms
            platforms = list(set(s.platform for s in group_signals))

            # Summary
            summary = self._make_summary(topic, keywords, platforms)

            # Cluster ID
            cluster_id = hashlib.md5(
                (topic + "".join(sorted(platforms))).encode()
            ).hexdigest()[:12]

            # Content angles
            angles = self._generate_content_angles(topic, keywords, entities)

            niche = group_signals[0].niche if group_signals else None

            # ── CONTENT ANALYSIS ─────────────────────────────────────────
            # Extract real content from signal captions/bodies for script gen
            content_data = self._analyze_source_content(group_signals)

            cluster = TrendCluster(
                cluster_id=cluster_id,
                topic=topic,
                keywords=keywords[:MAX_KEYWORDS_PER_TREND],
                entities=entities[:8],
                summary=summary,
                sources=group_signals,
                platforms=platforms,
                sentiment_score=sentiment,
                first_seen=min(
                    (s.published_at or s.scraped_at for s in group_signals),
                    default=datetime.now(timezone.utc)
                ),
                niche=niche,
                centroid_embedding=centroid,
                content_angles=angles,
                source_captions=content_data["captions"],
                mentioned_tools=content_data["tools"],
                key_claims=content_data["claims"],
                top_comments_digest=content_data["comments"],
                content_examples=content_data["examples"],
                engagement_stats=content_data["stats"],
            )
            clusters.append(cluster)

        return clusters

    # ─── TOPIC DISTILLATION ──────────────────────────────────────────────────

    def _distill_topic(
        self,
        signals: list,
        keywords: List[str],
        entities: List[str],
        centroid: np.ndarray,
        embeddings: np.ndarray,
    ) -> str:
        """
        Create a clean, descriptive topic label from cluster data.

        Priority order:
         1. Named entities (e.g. "ChatGPT", "OpenAI", "Sundar Pichai")
         2. Top TF-IDF keywords combined into a phrase
         3. Closest-to-centroid signal title (cleaned) as last resort

        This ensures topics read like "AI Video Generation Tools" instead
        of raw captions like "Stop paying for AI subscriptions! 🛑💸".
        """
        # Clean keyword/entity candidates
        clean_kw = [
            kw for kw in keywords[:6]
            if kw.lower() not in STOPWORDS
            and len(kw) >= 3
            and not re.match(
                r'^(autocomplete|type\s|type$|google\s|topic\s|'
                r'family\s|mode\s|transport)',
                kw, re.I
            )
        ]
        _entity_noise = {
            'google autocomplete', 'autocomplete', 'topic', 'type',
            'technics', 'mode', 'transport', 'family', 'book',
        }
        clean_ent = [
            e for e in entities[:4]
            if len(e) >= 2
            and e.lower() not in STOPWORDS
            and e.lower() not in _entity_noise
        ]

        # Strategy 1: Entity + keyword combo (best for named topics)
        # e.g. "OpenAI GPT Models" or "Sundar Pichai AI Warning"
        if clean_ent and clean_kw:
            primary = clean_ent[0]
            # Find a keyword that isn't just the entity repeated
            supporting = [
                kw for kw in clean_kw
                if kw.lower() != primary.lower()
                and primary.lower() not in kw.lower()
            ][:2]
            if supporting:
                topic = f"{primary}: {' & '.join(w.title() for w in supporting)}"
                if len(topic) <= 80:
                    return topic

        # Strategy 2: Top 2-3 keywords as a descriptive phrase
        if len(clean_kw) >= 2:
            phrase_words = clean_kw[:3]
            topic = " ".join(w.title() for w in phrase_words)
            if len(topic) >= 6:
                return topic

        # Strategy 3: Best entity alone
        if clean_ent:
            return clean_ent[0]

        # Strategy 4: Closest-to-centroid signal title, cleaned
        if len(signals) > 0 and len(embeddings) > 0:
            sims = np.dot(embeddings, centroid)
            best_idx = int(np.argmax(sims))
            raw_title = signals[best_idx].title[:100]
            # Clean: remove emojis, hashtags, @mentions, excessive punctuation
            cleaned = re.sub(r'[#@]\w+', '', raw_title)
            cleaned = re.sub(r'[^\w\s\-\':,.]', '', cleaned)
            cleaned = re.sub(r'\s+', ' ', cleaned).strip()
            if len(cleaned) >= 10:
                return cleaned[:80]
            # If cleaned is too short, use raw
            return raw_title[:80]

        return keywords[0].title() if keywords else "Emerging Trend"

    # ─── CONTENT ANALYSIS ────────────────────────────────────────────────────

    # Known AI/tech tools, products, platforms for extraction
    _KNOWN_TOOLS = {
        "chatgpt", "gpt", "gpt-4", "gpt4", "claude", "gemini", "grok",
        "midjourney", "dall-e", "dalle", "stable diffusion", "runway",
        "openai", "anthropic", "google", "meta", "microsoft", "copilot",
        "notion", "figma", "canva", "invideo", "synthesia", "descript",
        "character ai", "perplexity", "deepseek", "leonardo", "ideogram",
        "veo", "veo3", "sora", "kling", "pika", "heygen", "hedra",
        "zapier", "make", "n8n", "framer", "gamma", "beautiful.ai",
        "coursera", "udemy", "jasper", "copy.ai", "grammarly",
        "photoshop", "premiere", "capcut", "tiktok", "instagram", "youtube",
        # Finance
        "robinhood", "zerodha", "groww", "coinbase", "binance",
        "stripe", "paypal", "razorpay", "upstox",
    }

    def _analyze_source_content(self, signals: list) -> dict:
        """
        Deep-analyze signal content for Stage 02 script generation.

        THREE CRITICAL FILTERS:
          1. Language gate  — reject non-English content (Hindi, CJK, Arabic chars)
          2. Relevance gate — only use captions from signals that share ≥2 keywords
                              with the cluster topic (prevents random trending noise)
          3. URL traceability — only attach URLs from signals that actually
                                contributed content to the script

        Returns dict with all extracted content + relevant_urls.
        """
        captions: List[str] = []
        tools_found: set = set()
        claims: List[str] = []
        examples: List[str] = []
        comments_digest: List[str] = []
        relevant_urls: List[str] = []  # URLs from contributing signals only

        total_views = 0
        total_likes = 0
        total_comments = 0
        signal_count = 0

        # Build a keyword set for relevance checking
        # Use all signal titles + bodies to extract topic-keywords
        all_words: set = set()
        for s in signals:
            for w in s.title.lower().split():
                if len(w) >= 3:
                    all_words.add(w)
        # Top keywords are the most frequent words across all signals
        from collections import Counter
        word_freq = Counter()
        for s in signals:
            words = set(s.title.lower().split() + s.body[:200].lower().split())
            for w in words:
                if len(w) >= 3 and w not in STOPWORDS:
                    word_freq[w] += 1
        # Cluster keywords = words that appear in ≥20% of signals (or ≥2 signals)
        min_freq = max(2, len(signals) * 0.2)
        cluster_kw = {w for w, c in word_freq.items() if c >= min_freq}
        # Fallback: if cluster is small, use top 15 most common
        if len(cluster_kw) < 5:
            cluster_kw = {w for w, _ in word_freq.most_common(15)}

        # Sort by engagement for priority
        sorted_sigs = sorted(
            signals,
            key=lambda s: s.engagement_score,
            reverse=True,
        )

        for signal in sorted_sigs[:20]:  # Check top 20 signals
            signal_count += 1
            total_views += signal.views
            total_likes += signal.score
            total_comments += signal.comments

            full = f"{signal.title} {signal.body}".strip()
            if not full or len(full) < 15:
                continue

            # ═══ FILTER 1: LANGUAGE GATE ═════════════════════════════════
            # Reject non-English content. Check character ratios.
            if not self._is_english_text(full):
                continue

            # ═══ FILTER 2: RELEVANCE GATE ════════════════════════════════
            # Skip signals from platforms that don't carry real content
            skip_platforms = {
                'google_trends_rising', 'youtube_autocomplete',
                'gdelt', 'google_trends',
            }
            has_real_content = signal.platform not in skip_platforms

            # Check keyword overlap between this signal and the cluster
            signal_words = set(full.lower().split())
            overlap = signal_words & cluster_kw
            is_relevant = len(overlap) >= 2

            if not has_real_content and not is_relevant:
                continue

            # ═══ CONTENT EXTRACTION (only from relevant signals) ═════════

            # ── Clean caption ────────────────────────────────────────────
            cleaned = re.sub(
                r'(?i)(follow\s*@\w+|comment\s+["\']?\w+["\']?|'
                r'link\s+in\s+bio|DM\s+me|subscribe|'
                r'tag\s+\d+\s+friends?|share\s+this)',
                '', full
            )
            cleaned = re.sub(r'@\w+', '', cleaned)
            cleaned = re.sub(r'(#\w+\s*){3,}$', '', cleaned)
            cleaned = re.sub(
                r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF'
                r'\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF'
                r'\U00002702-\U000027B0\U0001FA00-\U0001FA6F'
                r'\U0001FA70-\U0001FAFF\U00002600-\U000026FF'
                r'\U0000FE00-\U0000FE0F]+', ' ', cleaned
            )
            cleaned = re.sub(r'\s+', ' ', cleaned).strip()

            if len(cleaned) >= 20 and is_relevant:
                captions.append(cleaned[:300])
                # ═══ FILTER 3: URL TRACEABILITY ══════════════════════════
                # Only attach URL if this signal CONTRIBUTED content
                if (signal.url
                    and signal.url not in relevant_urls
                    and not signal.url.startswith('https://www.instagram.com/reel/')
                    and len(relevant_urls) < 8):
                    relevant_urls.append(signal.url)

            # ── Extract tools/products mentioned ─────────────────────────
            text_lower = full.lower()
            for tool in self._KNOWN_TOOLS:
                if tool in text_lower:
                    tools_found.add(tool.title())
            for tag in signal.hashtags:
                tag_lower = tag.lower().strip('#')
                for tool in self._KNOWN_TOOLS:
                    tool_clean = tool.replace(' ', '').replace('-', '')
                    if tag_lower == tool_clean or tag_lower == tool.replace(' ', ''):
                        tools_found.add(tool.title())

            # ── Extract key claims (only from relevant signals) ──────────
            if is_relevant:
                sentences = re.split(r'[.!?\n]', full)
                for sent in sentences:
                    sent = sent.strip()
                    if len(sent) < 15 or not self._is_english_text(sent):
                        continue
                    # Sentences with numbers/percentages = factual claims
                    if re.search(r'\d+[%xX]|\d{2,}|\$\d|billion|million|thousand', sent):
                        claim = re.sub(r'[#@]\w+', '', sent).strip()
                        if len(claim) >= 15 and claim not in claims:
                            claims.append(claim[:200])
                    elif re.search(
                        r'(?i)(will|could|must|should|need to|going to|'
                        r'replace|disrupt|transform|change|revolution|'
                        r'breakthrough|warning|danger|opportunity)',
                        sent
                    ):
                        claim = re.sub(r'[#@]\w+', '', sent).strip()
                        if len(claim) >= 20 and claim not in claims:
                            claims.append(claim[:200])

                # ── Extract content examples ─────────────────────────────
                for sent in sentences:
                    sent = sent.strip()
                    if re.search(
                        r'(?i)(for example|I tried|I tested|here\'s how|'
                        r'step \d|use case|you can|it lets you|'
                        r'creates?|generates?|produces?|makes?)',
                        sent
                    ) and len(sent) >= 20 and self._is_english_text(sent):
                        example = re.sub(r'[#@]\w+', '', sent).strip()
                        if len(example) >= 15 and example not in examples:
                            examples.append(example[:200])

            # ── Comment digest from raw_data ─────────────────────────────
            raw = signal.raw_data or {}
            first_comment = raw.get("firstComment", "") or raw.get("first_comment", "")
            if (first_comment and len(first_comment) >= 10
                    and self._is_english_text(first_comment)):
                comments_digest.append(first_comment[:150])

        # ── Aggregate stats ──────────────────────────────────────────────
        stats = {
            "total_views": total_views,
            "total_likes": total_likes,
            "total_comments": total_comments,
            "signal_count": signal_count,
            "avg_views": total_views // max(signal_count, 1),
            "avg_likes": total_likes // max(signal_count, 1),
        }

        return {
            "captions": captions[:10],
            "tools": sorted(tools_found)[:15],
            "claims": claims[:8],
            "examples": examples[:6],
            "comments": comments_digest[:5],
            "stats": stats,
            "relevant_urls": relevant_urls[:8],  # NEW: only contributing URLs
        }

    # ─── LANGUAGE DETECTION ──────────────────────────────────────────────────

    @staticmethod
    def _is_english_text(text: str) -> bool:
        """
        Fast language gate. Returns True if text is predominantly English.

        Uses character-ratio heuristics — no external dependency.
        Rejects text with >25% non-Latin characters (Hindi, CJK, Arabic, etc.)
        Also rejects text that's just URLs, hashtags, or gibberish.
        """
        if not text or len(text) < 10:
            return False

        # Strip URLs, hashtags, mentions for accurate char analysis
        clean = re.sub(r'https?://\S+', '', text)
        clean = re.sub(r'[#@]\w+', '', clean)
        clean = re.sub(r'\s+', ' ', clean).strip()

        if len(clean) < 10:
            return False

        # Count character types
        latin = 0
        non_latin = 0
        for ch in clean:
            cp = ord(ch)
            if cp < 128:  # ASCII (English letters, numbers, punctuation)
                latin += 1
            elif 0x0080 <= cp <= 0x024F:  # Extended Latin (accents)
                latin += 1
            elif cp > 0x024F and ch.isalpha():  # Non-Latin script
                non_latin += 1

        total_alpha = latin + non_latin
        if total_alpha == 0:
            return False

        non_latin_ratio = non_latin / total_alpha
        return non_latin_ratio < 0.25

    def _extract_keywords(self, texts: List[str]) -> List[str]:
        """Extract top TF-IDF keywords from a group of texts, with stopword filtering."""
        if not texts:
            return []
        combined = " ".join(texts)
        try:
            # Fit on all texts, transform combined
            self._tfidf.fit(texts)
            tfidf_vec = self._tfidf.transform([combined])
            feature_names = self._tfidf.get_feature_names_out()
            scores = tfidf_vec.toarray()[0]
            top_indices = scores.argsort()[::-1][:MAX_KEYWORDS_PER_TREND * 3]

            # Filter through stopwords + validate
            keywords: List[str] = []
            for i in top_indices:
                if scores[i] <= 0:
                    break
                kw = feature_names[i]
                # Skip stopwords
                if kw.lower() in STOPWORDS:
                    continue
                # Skip single chars
                if len(kw) < 2:
                    continue
                # Skip hex colors/numbers-only
                if re.match(r'^[0-9a-fA-F]+$', kw) or re.match(r'^\d+$', kw):
                    continue
                # Skip CSS-like patterns
                if any(c in kw for c in [':', ';', '=', '{', '}', '<', '>']):
                    continue
                keywords.append(kw)
                if len(keywords) >= MAX_KEYWORDS_PER_TREND:
                    break
            return keywords
        except Exception as e:
            logger.debug(f"[NLP] TF-IDF failed: {e}")
            # Fallback: simple word frequency
            words = combined.lower().split()
            freq: Dict[str, int] = {}
            for w in words:
                w = w.strip(string.punctuation)
                if len(w) > 3 and w not in STOPWORDS:
                    freq[w] = freq.get(w, 0) + 1
            return sorted(freq, key=lambda k: freq[k], reverse=True)[:MAX_KEYWORDS_PER_TREND]

    def _extract_entities(self, text: str) -> List[str]:
        """Extract named entities using spaCy."""
        nlp = self._get_spacy()
        if nlp is None:
            return []
        try:
            doc = nlp(text[:5000])  # Limit for speed
            entities = [
                ent.text.strip()
                for ent in doc.ents
                if ent.label_ in ("PERSON", "ORG", "PRODUCT", "EVENT", "GPE", "WORK_OF_ART")
                and len(ent.text.strip()) > 2
            ]
            # Deduplicate preserving order
            seen = set()
            unique_entities = []
            for e in entities:
                if e.lower() not in seen:
                    seen.add(e.lower())
                    unique_entities.append(e)
            return unique_entities[:10]
        except Exception as e:
            logger.debug(f"[NLP] NER failed: {e}")
            return []

    def _aggregate_sentiment(self, texts: List[str]) -> float:
        """
        Aggregate VADER sentiment across texts.
        Returns 0.0 (negative) to 1.0 (positive).
        """
        if not texts:
            return 0.5
        scores = []
        for text in texts[:10]:  # Sample for speed
            score = self._sentiment.polarity_scores(text)
            scores.append(score["compound"])  # -1 to +1
        avg = sum(scores) / len(scores) if scores else 0.0
        return (avg + 1) / 2  # Rescale to 0-1

    def _make_summary(
        self, topic: str, keywords: List[str], platforms: List[str]
    ) -> str:
        """Generate a 1-line trend summary."""
        kw_str = ", ".join(keywords[:3]) if keywords else ""
        platform_str = " + ".join(
            p.replace("_", " ").replace("rising", "").strip()
            for p in platforms[:3]
        )
        return f"{topic} — trending keywords: {kw_str}. Confirmed on: {platform_str}."

    def _generate_content_angles(
        self,
        topic: str,
        keywords: List[str],
        entities: List[str],
    ) -> List[str]:
        """
        Generate 8 content angles (expanded for multi-channel strategy):
          broad, deep-dive, reaction, data, trend-jack, myth-bust, tutorial, comparison
        """
        entity_str = entities[0] if entities else (keywords[0] if keywords else topic)
        kw2 = keywords[1] if len(keywords) > 1 else 'everyone'
        kw3 = keywords[2] if len(keywords) > 2 else 'the industry'
        short_topic = topic[:50] if len(topic) > 50 else topic
        return [
            f"Explainer: What is {short_topic}? — everything you need to know",
            f"Deep-dive: Why {entity_str} matters for {kw2}",
            f"Reaction: My honest take on {short_topic}",
            f"Data: The numbers behind {short_topic} that nobody talks about",
            f"Trend-jack: Why {short_topic} is about to change {kw3}",
            f"Myth-busting: 3 things everyone gets wrong about {entity_str}",
            f"Tutorial: How to take advantage of {short_topic} right now",
            f"Comparison: {entity_str} vs the competition — who wins?",
        ]

    def _compute_novelty(
        self,
        cluster_embedding: np.ndarray,
        existing_embeddings: List[np.ndarray],
    ) -> float:
        """
        Novelty = 1 - max(cosine similarity to any recently published content).
        Score of 1.0 = completely fresh. Score of 0.0 = we already covered this.
        """
        if not existing_embeddings:
            return 1.0
        existing = np.vstack(existing_embeddings)
        sims = np.dot(existing, cluster_embedding)
        max_sim = float(np.max(sims))
        return max(0.0, 1.0 - max_sim)

    # ─── NICHE SCREENING ──────────────────────────────────────────────────────

    def _screen_by_niche(
        self, clusters: List[TrendCluster], niche: str
    ) -> List[TrendCluster]:
        """
        Filter clusters that don't match the selected niche.

        Uses seed_keywords from config as a dictionary.
        Clusters with ZERO keyword overlap are dropped — they're off-topic
        (e.g., lifestyle/travel trends appearing in tech_ai niche).

        Clusters with at least 1 keyword match pass through.
        """
        niche_config = NICHES.get(niche, {})
        seed_keywords = set(
            kw.lower() for kw in niche_config.get("seed_keywords", [])
        )

        if not seed_keywords:
            return clusters  # No keywords to screen against

        # Also include Twitter queries and YouTube search terms as extra niche signals
        for q in niche_config.get("twitter_queries", []):
            seed_keywords.add(q.lower())
        for term in niche_config.get("youtube_search_terms", []):
            for word in term.lower().split():
                if len(word) >= 3:
                    seed_keywords.add(word)

        screened: List[TrendCluster] = []
        for cluster in clusters:
            # Check keyword overlap
            cluster_words = set()
            for kw in cluster.keywords:
                cluster_words.add(kw.lower())
            # Also check topic words
            for word in cluster.topic.lower().split():
                word = word.strip(".,!?:;()[]{}\"'")
                if len(word) >= 3:
                    cluster_words.add(word)
            # Also check entity words
            for ent in cluster.entities:
                cluster_words.add(ent.lower())
            # Check signal hashtags
            for signal in cluster.sources[:5]:
                for tag in signal.hashtags:
                    cluster_words.add(tag.lower())

            overlap = cluster_words & seed_keywords
            if overlap:
                screened.append(cluster)
            else:
                logger.debug(
                    f"[NLP] Niche screen dropped: '{cluster.topic[:50]}' "
                    f"(no overlap with {niche} keywords)"
                )

        return screened

    # ─── CONTENT GENERATION PARAMETERS ────────────────────────────────────────

    def _fill_content_params(self, cluster: TrendCluster) -> None:
        """
        Fill content generation parameters for a TrendCluster.

        These are consumed by Stage 02 (content generation) to:
          - Generate scripts with the right hook
          - Set video duration based on topic depth
          - Choose format (explainer vs reaction vs listicle)
          - Provide hashtags for captions
          - Give source URLs for fact-checking
        """
        # 1. Platform breakdown
        from collections import Counter
        platform_counts = Counter(s.platform for s in cluster.sources)
        cluster.platform_breakdown = dict(platform_counts)

        # 2. Source URLs (top 5 unique, highest-engagement first)
        seen_urls: set = set()
        source_urls: List[str] = []
        sorted_sources = sorted(
            cluster.sources,
            key=lambda s: s.engagement_score,
            reverse=True,
        )
        for s in sorted_sources:
            if s.url and s.url not in seen_urls and len(source_urls) < 5:
                seen_urls.add(s.url)
                source_urls.append(s.url)
        cluster.source_urls = source_urls

        # 3. Suggested hashtags (combine signal hashtags + keywords)
        # Validate: no hex colors, no CSS, no numbers-only, no platform noise
        hashtag_counter: Counter = Counter()
        _hashtag_noise = {
            'reels', 'reel', 'fyp', 'foryou', 'viral', 'trending',
            'follow', 'like', 'share', 'explore', 'post', 'posts',
            'content', 'video', 'instagram', 'youtube', 'tiktok',
        }
        for signal in cluster.sources:
            for tag in signal.hashtags:
                tag_clean = tag.lower().strip("#").replace(" ", "")
                if self._is_valid_hashtag(tag_clean, _hashtag_noise):
                    hashtag_counter[tag_clean] += 1
        # Add keywords as hashtags too (they've been stopword-filtered)
        for kw in cluster.keywords[:5]:
            kw_clean = kw.lower().replace(" ", "")
            if self._is_valid_hashtag(kw_clean, _hashtag_noise):
                hashtag_counter[kw_clean] += 1
        # Add niche-specific seed hashtags
        if cluster.niche:
            niche_cfg = NICHES.get(cluster.niche, {})
            for kw in niche_cfg.get("seed_keywords", [])[:5]:
                tag = kw.lower().replace(" ", "")
                if len(tag) >= 3:
                    hashtag_counter[tag] += 0.5  # Lower weight than natural tags

        cluster.suggested_hashtags = [
            f"#{tag}" for tag, _ in hashtag_counter.most_common(15)
        ]

        # 4. Suggested hook (attention-grabbing opening line)
        topic = cluster.topic[:60]
        tier = cluster.tier
        if tier == "early":
            cluster.suggested_hook = (
                f"Nobody's talking about this yet — {topic}"
            )
        elif tier == "emerging":
            cluster.suggested_hook = (
                f"This is about to blow up — {topic}"
            )
        elif tier == "trending":
            cluster.suggested_hook = (
                f"Everyone's talking about {topic} — here's what you need to know"
            )
        else:
            cluster.suggested_hook = f"The truth about {topic}"

        # 5. Suggested duration based on signal depth
        n_sources = len(cluster.sources)
        n_platforms = len(cluster.platforms)
        if n_sources >= 10 and n_platforms >= 3:
            cluster.suggested_duration = "60s"  # Deep topic, enough material
        elif n_sources >= 5 or n_platforms >= 2:
            cluster.suggested_duration = "30s"  # Moderate depth
        else:
            cluster.suggested_duration = "15s"  # Quick hit

        # 6. Suggested format
        sentiment = cluster.sentiment_score
        has_entities = bool(cluster.entities)
        niche = cluster.niche or ""

        if niche == "entertainment":
            if sentiment > 0.6:
                cluster.suggested_format = "reaction"
            else:
                cluster.suggested_format = "listicle"
        elif niche == "finance":
            if has_entities:
                cluster.suggested_format = "news"
            else:
                cluster.suggested_format = "explainer"
        elif niche == "tech_ai":
            if n_platforms >= 3:
                cluster.suggested_format = "explainer"
            else:
                cluster.suggested_format = "reaction"
        else:
            cluster.suggested_format = "explainer"

    @staticmethod
    def _is_valid_hashtag(tag: str, noise_set: set) -> bool:
        """
        Validate a hashtag candidate.
        Rejects: hex colors, numbers-only, CSS fragments, platform noise, too short.
        """
        if len(tag) < 3:
            return False
        if tag in noise_set:
            return False
        # Reject hex colors (e.g., 6f6f6f, fff, 21038)
        if re.match(r'^[0-9a-fA-F]{3,8}$', tag):
            return False
        # Reject pure numbers
        if re.match(r'^\d+$', tag):
            return False
        # Reject CSS-like tokens
        if any(c in tag for c in [':', ';', '=', '{', '}', '<', '>', '/', '*']):
            return False
        # Must contain at least one letter
        if not re.search(r'[a-zA-Z]', tag):
            return False
        return True

