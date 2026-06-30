# VELOCI — Full System Build Document

> **AI-Driven Multimodal System for Automated UGC Generation and Engagement Optimization**
> The machine that learns to go viral.

---

## 1. Project Vision

VELOCI is a **closed-loop autonomous content creation system** that:
1. **Detects trends** 12-72h before they peak on social media
2. **Generates short-form video content** (scripts, TTS, visuals, thumbnails)
3. **Predicts engagement** before publishing (multimodal gate)
4. **Auto-schedules** posts using RL (contextual bandit rewarded on first-hour velocity)
5. **Publishes** across 10-15 channels (3-4 niches × 3-4 angles each)
6. **Learns** from every result — retraining predictions and tuning generation
7. **Compounds revenue** — platform payouts, SaaS, B2B, affiliate

This is **not** a content generator. It's a **self-learning digital creator**.

---

## 2. The Problem We're Solving

| Pain Point | What Exists | What VELOCI Does |
|---|---|---|
| Late trend signals | Creators find trends after they peak | We scrape RISING signals 12-72h ahead via Reddit Rising, Google Trends RELATED RISING, GDELT global events |
| No pre-publish prediction | Failure visible only post-upload | Multimodal engagement gate (NAWP+ECR) blocks low-performers before they go live |
| No feedback loop | Every cycle starts from scratch | Live performance (views, watch time, drop-off) feeds back as training signal |
| Manual scheduling | Posting based on gut feel | RL contextual bandit learns per-channel optimal windows, rewarded on first-hour velocity |
| Fragmented tools | Analytics/scheduling/generation are separate | Unified pipeline — every module feeds the next, sharing state and learning |
| No behaviour modelling | No system models how visual+audio+text jointly drive retention | Cross-modal attention fusion (visual, audio, caption, metadata) models real engagement |

---

## 3. Research Foundation

### Core Papers

| Paper | Venue | Key Contribution | Our Adaptation |
|---|---|---|---|
| **Li et al.** "Delving Deep into Engagement Prediction of Short Videos" | CVPR 2024 | SnapUGC dataset (90K videos, 2K+ raters/video). VQA ≠ engagement. NAWP+ECR metrics | We adopt NAWP+ECR as primary metrics. Use cross-modal attention as a **generation gate**, not just scorer |
| **Sun et al.** "Engagement Prediction with Large Multimodal Models" | ICCV 2025 | VQualA Challenge winner. Ensemble VideoLLaMA2 + Qwen2.5-VL beats specialized models | Adapts LMM fusion for generative pipeline — model guides what gets **created** |
| **Zou et al.** "RL to Optimize Long-term User Engagement" (FeedRec) | KDD 2019 | Dual-network RL: Q-Network (LSTM) + S-Network environment simulator | Contextual bandit for scheduling — rewarded on first-hour velocity |
| **Gelli et al.** "Image Popularity Prediction using Sentiment+Context" | ACM MM 2015 | Multimodal outperforms unimodal for pre-publish prediction | Validates our pre-publish multimodal premise |
| **Mazloom et al.** "Multimodal Popularity Prediction of Brand-related Videos" | ACM MM 2016 | Sentiment in speech/captions is strong shareability predictor | Caption sentiment scoring in engagement predictor |
| **Zhang et al.** "Multi-task Learning for Short-Video Engagement Prediction" | WWW 2023 | Shared cross-modal representation generalises better across metrics | Multi-task head (views, likes, shares, comments) in our predictor |

### Novel Contributions (C1-C4)

1. **C1** — Pre-publish engagement prediction as a **generation gate** (not post-hoc evaluator)
2. **C2** — Closed-loop adaptive pipeline: Trend → Generate → Predict → Publish → Retrain (never static)
3. **C3** — Multimodal behaviour modelling guides **generation**, not just evaluation
4. **C4** — First-hour engagement velocity formalised as RL reward for scheduling

---

## 4. System Architecture — 7 Stages

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        CONTINUOUS FEEDBACK LOOP                             │
│                                                                             │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐  │
│  │ 01      │    │ 02      │    │ 03      │    │ 04      │    │ 05      │  │
│  │ TREND   │───▶│ CONTENT │───▶│ ENGAGE  │───▶│ RL      │───▶│ AUTO    │  │
│  │ INTEL   │    │ GEN     │    │ GATE    │    │ SCHED   │    │ PUBLISH │  │
│  └─────────┘    └─────────┘    └────┬────┘    └─────────┘    └────┬────┘  │
│       ▲              ▲              │              ▲              │        │
│       │              │        E < θ │ ───▶ REVISE  │              │        │
│       │              │              │              │              │        │
│       │         ┌────┴──────────────┴──────────────┴──────┐       │        │
│       │         │               06  FEEDBACK LOOP         │◀──────┘        │
│       │         │  views, watch time, drop-off, velocity  │               │
│       └─────────┤  retrain predictor · update RL policy   ├───────────────│
│                 │  drift: θ threshold adapts               │               │
│                 └─────────────────────────────────────────┘               │
│                                                                             │
│                 07  ANALYTICS DASHBOARD + REVENUE STREAMS                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Stage-by-Stage Breakdown

### Stage 01 — Trend Intelligence Engine (THIS MODULE ✅)

**Status**: Code exists, needs restructuring and optimization.

**What it does**:
Scrapes 8 sources in parallel every 30 minutes, clusters signals semantically, scores them on velocity + cross-platform confirmation + novelty + sentiment, outputs ranked trend JSON.

**Sources** (scraped every 30 min):

| Source | Type | Why | Signal Lead Time |
|---|---|---|---|
| Reddit RISING | API (PRAW) | Rising posts = velocity signal 6-24h ahead of mainstream | 6-24h early |
| Google Trends RISING | Unofficial (pytrends) | Breakout queries (5000%+ growth) = best single predictor | 12-72h early |
| YouTube Trending + Autocomplete | API v3 | Trending = validation; autocomplete = pure intent signal | 2-12h early |
| Twitter/X Velocity | API v2 (free tier) | Real-time mention velocity (exploding = 10x in 1h vs 3h) | 0-6h early |
| NewsAPI | REST API | Keyword-specific breaking news cross-validation | 6-24h early |
| RSS (BBC, Reuters, NYT, etc.) | Feed parsing | Breaking news within minutes of publishing | 6-48h early |
| GDELT | REST (free/no key) | 100+ languages, 250+ countries, near-real-time global events | 24-72h early |
| TikTok Discover | Playwright (headless) | Validation layer — confirms what IS trending | 0-12h (lagging) |

**NLP Pipeline**:
```
Raw Signals → Clean → Embed (all-MiniLM-L6-v2, 384-dim) → DBSCAN Cluster
           → TF-IDF Keywords → NER (spaCy) → VADER Sentiment → TrendCluster
```

**Scoring** (composite weighted sum):
- **Velocity** (0.35) — rate of mention growth over last 1h vs 4h
- **Cross-platform** (0.25) — weighted count of distinct confirming platforms
- **Novelty** (0.20) — cosine distance from recently published content
- **Sentiment** (0.10) — positive = more shareable
- **Engagement potential** (0.10) — log-scaled aggregate engagement proxy

**Output**: Ranked JSON per niche with tier classification:
- 🟢 **Early** (0.70-1.00) — post in 2-6h, you're ahead of the curve
- 🟡 **Emerging** (0.50-0.70) — post within 24h, good window
- 🟠 **Trending** (0.35-0.50) — still viable but saturating
- 🔴 **Saturated** (<0.35) — skip

**Known Issues**:
1. Reddit API blocked — can't create app (Responsible Builder Policy)
2. All files are flat (no package structure, `sys.path.insert` hacks)
3. `.env` file contains shell script commands instead of proper dotenv
4. No tests, no CI/CD
5. TikTok Playwright selectors are fragile (DOM changes)
6. Twitter free tier is very restrictive (500K tweets/month cap)
7. Google Trends pytrends can 429 under load
8. No circuit breakers or proper retry backoff

---

### Stage 02 — Content Generation (TO BUILD)

**Input**: Ranked trend JSON from Stage 01

**Output per channel**: Script → TTS audio → diffusion visuals → assembled video → thumbnail → caption + hashtags

**Script Structure** (per-channel persona variation):
```
Hook (0-3s)     → Attention-grabbing opening
Info (3-30s)    → Core information delivery
Twist (30-45s)  → Unexpected angle / insight
CTA (45-60s)    → Call to action
```

**Per-niche channel angles** (3-4 niches × 3-4 channels = 10-15 channels):

| Niche | Broad Explainer | Deep-Dive | Reaction/Hot Take | Stats & Data |
|---|---|---|---|---|
| Tech & AI | "What is X?" | "Why X matters for..." | "My honest take on X" | "The numbers behind X" |
| Finance | Market overview | Deep fundamentals | Reaction to news | Charts & numbers |
| Entertainment | What happened | Behind the scenes | My opinion | Record-breaking data |

**Why 4 angles per niche**: Same trend → 4 different scripts, thumbnails, captions. Platform fingerprint defeated by audio+visual variation. Each channel builds a distinct audience — no self-competition.

**Components needed**:
- LLM script generator (GPT-4o / Claude / local LLM)
- TTS engine (ElevenLabs / Bark / local XTTS)
- Diffusion visual generator (SDXL / Flux)
- Video assembler (FFmpeg pipeline)
- Subtitle burn-in
- Thumbnail extraction + optimization
- Caption + hashtag generator (platform-specific)

**Anti-Monetization Safeguards**:
- Content fingerprinting (perceptual hash: pHash + dHash)
- Copyright detection layer (audio fingerprint via acoustID, visual via reverse image search)
- Originality score threshold — reject if too similar to existing content
- Platform ToS compliance checker (no misleading claims, no copyrighted audio)
- Per-channel visual/audio variation to defeat duplicate detection algorithms

---

### Stage 03 — Multimodal Engagement Predictor (Publish Gate)

**Formula**: `E = f(video, audio, caption, metadata)`

**Decision Logic**:
- `E ≥ θ` → Pass to scheduler → Publish
- `E < θ` → Send back to Stage 02 with adjusted params → Regenerate

**Metrics** (from Li et al. CVPR 2024):
- **NAWP** (Normalised Average Watch Percentage) — controls for duration bias
- **ECR** (Engagement Continuation Rate) — do engaged viewers return?

**Model Architecture**:
- Visual encoder: ViT / VideoMAE (frame sampling)
- Audio encoder: AST / wav2vec2.0
- Text encoder: BERT / sentence-transformers
- Cross-modal attention fusion (not late fusion concatenation)
- Multi-task prediction heads: views, likes, shares, comments (Zhang et al. WWW 2023)

**Training Data**:
- SnapUGC dataset (90K videos, 2K+ annotators/video)
- Curated platform UGC corpus with engagement labels
- Our own historical data (once feedback loop is active)

**Threshold θ**:
- Cold-start: seeded manually at percentile-based value
- Drift: θ adapts based on observed performance distribution (moving average of top-quartile scores)

---

### Stage 04 — RL Contextual Bandit Scheduler

**Reward Signal**: First-hour engagement velocity (directly aligned with platform ranking mechanics)

**Architecture** (adapted from Zou et al. FeedRec, KDD 2019):
- Q-Network (LSTM) models time-series of engagement velocity per channel
- Cold-start: seeded on SproutSocial benchmark posting windows
- Per-channel window learning — each channel discovers its optimal windows
- Cross-channel deconfliction — prevents self-cannibalization

**Context Features**:
- Time of day (UTC + local timezone)
- Day of week
- Channel-specific engagement history
- Trend tier and velocity
- Niche saturation level
- Competing posts in the same window
- Platform-specific algorithm behaviour patterns (e.g., TikTok's FYP push timing)

**Output**: Optimal publish timestamp per channel per post

---

### Stage 05 — Auto-Publish Layer (10-15 channels)

**Platform APIs**:
- TikTok Content Posting API
- YouTube Data API v3 (upload)
- Instagram Graph API (Reels)

**Per-upload delivery**:
- Caption + hashtag attach (platform-optimized)
- Thumbnail attach (A/B if platform supports)
- Content fingerprint variation per channel (defeat duplicate detection)
- Staggered release windows (cross-channel deconfliction)

**Channel Strategy** (3-4 niches × 3-4 channels):
- Same trend → different persona/angle per channel
- Different tone, visual style, hook approach
- Staggered timing — never cannibalize your own views

---

### Stage 06 — Feedback Learning Loop

**Data Collection** (per post, 1h / 6h / 24h / 7d):
- Views
- Watch time (average + curves)
- Drop-off curves (where do viewers leave?)
- Likes, comments, shares
- First-hour velocity (RL reward signal)

**Model Updates**:
- **Engagement predictor**: Retrain with new (content, engagement) pairs
- **RL policy**: Update bandit weights with new (time, velocity) observations
- **θ threshold**: Drift — adapts to observed performance distribution
- **Score weights**: Adjust velocity/cross-platform/novelty/sentiment weights based on which signals predicted success

**Channel Performance Isolation**:
- Each channel's performance tracked independently
- Cross-channel learning shared (what worked on channel A may inform B)
- Per-niche model fine-tuning

---

### Stage 07 — Analytics Dashboard & Revenue

**Revenue Streams**:
1. **Platform payouts** — YouTube Partner Program, TikTok Creator Fund, IG Bonuses
2. **Subscription SaaS** — Creator analytics copilot (Free / Pro $29/mo / Agency $149/mo)
3. **B2B Ad Generation** — Automated short-form ad creatives for brands
4. **Affiliate Content** — Trend-matched product promotion at high volume

**Dashboard Features**:
- Live trend feed with tier classification
- Pre-upload engagement scores
- Historical performance analytics
- Channel health monitoring
- Revenue tracking per channel/niche

---

## 6. Evaluation Metrics

| Metric | Type | What It Measures |
|---|---|---|
| MAE | Regression | Primary metric for engagement score prediction |
| F1 Score | Classification | Viral vs. non-viral accuracy (binary gate) |
| NAWP | Engagement | Duration-normalized watch percentage |
| ECR | Engagement | Do viewers return for related content? |
| Watch Time Uplift | A/B | % improvement vs. unfiltered baseline over 30 days |
| CTR Uplift | A/B | AI titles/thumbnails vs. human-authored |

**Experimental Design**:
- Unimodal baselines: visual-only CNN, audio-only CRNN, text-only BERT
- Multimodal baseline: late fusion (no attention) vs. our cross-modal attention
- RL baseline: static SproutSocial heuristics vs. trained contextual bandit
- Ablation: each module removed one at a time

---

## 7. Security & Safeguards

### Content Protection
- **Fingerprinting**: pHash + dHash per video frame, acoustID for audio
- **Originality threshold**: reject if cosine similarity > 0.85 to any known content
- **Platform ToS monitor**: automated compliance check before publish

### Anti-Monetization Defence
- **Copyright detection**: audio fingerprint (Shazam/acoustID), visual reverse search
- **DMCA pre-check**: scan title/description for flagged terms
- **Fair use compliance**: transformative content score
- **Per-channel variation**: unique audio/visual fingerprint to avoid cross-channel strikes

### API Security
- **Credential rotation**: automated key refresh
- **Rate limit respect**: per-platform token bucket with adaptive backoff
- **Proxy rotation**: for browser-based scraping (TikTok/Playwright)
- **Secrets management**: no keys in source code, env-only

---

## 8. Why These Choices

### Why DBSCAN over K-means?
K-means requires specifying K upfront. Trends per cycle are unpredictable. DBSCAN discovers clusters organically and marks true outliers as noise.

### Why RISING not HOT?
Reddit's "rising" sort shows posts gaining velocity RIGHT NOW. "Hot" shows posts that already have votes. The delta = your lead time.

### Why GDELT?
100+ languages, 250+ countries, near-real-time. A protest in Brazil or a product launch in Korea appears 12-48h before it trends in English social media.

### Why Google Trends RELATED RISING?
"Breakout" queries (5000%+ growth) predict what people will actively search on YouTube/IG next within 24-72h.

### Why Sentence Embeddings over Hashtags?
Hashtags are incomplete and inconsistent. Sentence embeddings cluster by MEANING — "AI regulation", "OpenAI compliance", and "Anthropic EU rules" cluster as ONE topic despite sharing zero hashtags.

### Why First-Hour Velocity as RL Reward?
Platform algorithms (TikTok, YT Shorts, IG Reels) make their ranking decision in the first 60 minutes. Optimizing for first-hour velocity is directly aligned with how platforms decide to amplify content.

### Why 4 Channels Per Niche?
Same trend → 4 scripts/thumbnails/captions. Platform fingerprint defeated. Each channel builds distinct audience → no self-competition + 4x coverage of the same trend.

---

## 9. Reddit API Workaround

Reddit's Responsible Builder Policy currently blocks new app creation. Alternatives:

1. **Pushshift via API** — Use the Pullpush.io mirror (free, no auth, historical + recent data)
2. **Old Reddit HTML scraping** — `old.reddit.com` is much simpler DOM, parse with BeautifulSoup (less fragile than Playwright but check ToS)
3. **Reddit RSS feeds** — `reddit.com/r/{subreddit}/.rss` feeds exist (very limited but zero auth)
4. **Manual app creation retry** — Reddit sometimes requires account age 30d+ and 100+ karma. Try with an older account.
5. **Third-party aggregators** — Use services like RedditStats or Subreddit Stats for trending detection

**Recommendation**: Start with Reddit RSS feeds (`.rss` endpoint) for basic signal, fall back to Pushshift/Pullpush for deeper data. Mark Reddit scraper as `degraded` mode.

---

## 10. Channel Strategy Recommendation

For 10-15 channels, use this matrix:

| Niche | Broad | Deep Dive | Hot Take | Data/Stats | Total |
|---|---|---|---|---|---|
| **Tech & AI** | 1 channel | 1 channel | 1 channel | 1 channel | 4 |
| **Finance** | 1 channel | 1 channel | 1 channel | 1 channel | 4 |
| **Entertainment** | 1 channel | 1 channel | 1 channel | — | 3 |
| **Lifestyle/Health** | 1 channel | 1 channel | — | 1 channel | 3 |
| **Total** | | | | | **14** |

**Why this split**:
- Tech + Finance have the highest RPM (revenue per mille) — more channels here
- Entertainment is volume-based — broader but lower RPM, 3 channels enough
- Lifestyle/Health is evergreen — fewer channels but consistent views

**Same content across channels**: Yes, but with different persona/angle/tone/visual. Platform algorithms detect exact duplicates, not topical overlap. As long as hook, visuals, and audio differ, each channel is treated independently.

**Genre-specific vs. same genre**: Mix both. Start with genre-specific (higher algorithmic consistency per channel) and add cross-genre channels later once the RL scheduler has learned enough about per-channel audience behaviour.
