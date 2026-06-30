# VELOCI — Progress Tracker

> **Last Updated**: 2026-03-30T22:03 IST

---

## Overall System Status

| Stage | Name | Status | Notes |
|---|---|---|---|
| 01 | Trend Intelligence | 🟡 Draft Code Exists | Flat structure, needs restructure + Reddit fix |
| 02 | Content Generation | 🔴 Not Started | LLM scripts + TTS + diffusion + assembly |
| 03 | Engagement Predictor | 🔴 Not Started | Multimodal gate (NAWP+ECR) |
| 04 | RL Scheduler | 🔴 Not Started | Contextual bandit + LSTM time-series |
| 05 | Auto-Publish | 🔴 Not Started | Platform API integration |
| 06 | Feedback Loop | 🔴 Not Started | Performance → retrain → policy update |
| 07 | Analytics Dashboard | 🔴 Not Started | Revenue tracking + live trends |

---

## Stage 01 — Trend Intelligence Engine

### Scrapers

| Scraper | File | API Status | Health | Notes |
|---|---|---|---|---|
| Reddit (PRAW) | `reddit_scraper.py` | ❌ API blocked | ❌ Fail | Responsible Builder Policy blocks app creation. Need workaround (RSS/Pushshift) |
| YouTube (Data API v3) | `youtube_scraper.py` | ✅ Key present | ⏳ Untested | `AIzaSyDLreqllRrxnI8y2-MSA_Ct7D5UA8ZlrQY` in .env |
| Google Trends | `google_trends_scraper.py` | ✅ No key needed | ⏳ Untested | pytrends unofficial, watch for 429s |
| Twitter/X (v2) | `twitter_scraper.py` | ✅ Token present | ⏳ Untested | Free tier, 500K tweets/month cap |
| NewsAPI | `news_scraper.py` | ✅ Key present | ⏳ Untested | Free tier, 100 req/day |
| RSS Feeds | `news_scraper.py` | ✅ No key needed | ⏳ Untested | 10+ feeds configured |
| GDELT | `news_scraper.py` | ✅ No key needed | ⏳ Untested | 15-min update cycle |
| TikTok (Playwright) | `tiktok_scraper.py` | ✅ No key needed | ⏳ Untested | Fragile CSS selectors, DOM changes |

### Pipeline Components

| Component | File | Status | Notes |
|---|---|---|---|
| Base schema + scraper ABC | `base.py` | ✅ Complete | `RawSignal` + `BaseScraper` |
| NLP Processor | `nlp_processor.py` | ✅ Complete | Embed → DBSCAN → TF-IDF → NER → VADER |
| Trend Ranker | `ranker.py` | ✅ Complete | Velocity + cross-platform + novelty + sentiment |
| Aggregator | `aggregator.py` | ✅ Complete | Parallel scrape → dedup → filter → NLP → rank |
| Database | `database.py` | ✅ Complete | Async SQLite: trends, signals, channel_perf, content_log |
| Config | `config.py` | ✅ Complete | 3 niches × 4 channel angles, scoring weights |
| Main entry point | `main.py` | ✅ Complete | APScheduler 30-min cycles |

### Infrastructure Issues

- [ ] **P0**: `.env` file contains bash commands — needs to be proper dotenv
- [ ] **P0**: All files flat in root — need `scrapers/`, `pipeline/`, `storage/` packages
- [ ] **P0**: `sys.path.insert(0, ...)` hacks in aggregator, nlp_processor, ranker, database, all scrapers
- [ ] **P1**: Reddit scraper non-functional (API blocked)
- [ ] **P1**: No test suite at all
- [ ] **P1**: No circuit breakers or proper error recovery
- [ ] **P2**: No API key validation on startup
- [ ] **P2**: No structured logging (loguru is good but no structured JSON output)
- [ ] **P3**: No Docker/containerization
- [ ] **P3**: No CI/CD pipeline

---

## Crash Testing Pipeline

### Test Categories

#### A. Scraper Resilience Tests
| Test ID | Description | Expected Behaviour |
|---|---|---|
| CT-S01 | Kill network mid-scrape | Each scraper returns `[]`, aggregator continues with others |
| CT-S02 | API key invalid/expired | Health check fails, scraper marked degraded, pipeline continues |
| CT-S03 | Rate limit hit (429/Too Many Requests) | Backoff + retry (tenacity), then graceful skip |
| CT-S04 | TikTok DOM change (CSS selectors break) | XHR intercept fallback activates |
| CT-S05 | API returns malformed JSON | Signal parsing returns `None`, no crash |
| CT-S06 | All scrapers fail simultaneously | Pipeline returns empty results, logs warning, schedules retry |
| CT-S07 | Scraper takes >30s (hangs) | Timeout fires, scraper killed, pipeline continues |

#### B. NLP Pipeline Tests
| Test ID | Description | Expected Behaviour |
|---|---|---|
| CT-N01 | Zero signals input | Returns `[]`, no crash |
| CT-N02 | All signals identical (extreme dedup) | 1 cluster output |
| CT-N03 | spaCy model not installed | NER returns `[]`, pipeline continues |
| CT-N04 | Single signal input | Produces 1 cluster (DBSCAN min_samples=2 → noise → still returned) |
| CT-N05 | 10,000+ signals (stress test) | Memory stays <2GB, embedding batch processing handles it |
| CT-N06 | Non-English text majority | Embeddings still work (MiniLM is multilingual-ish), but quality degrades |

#### C. Database Tests
| Test ID | Description | Expected Behaviour |
|---|---|---|
| CT-D01 | SQLite file locked (concurrent access) | aiosqlite handles with WAL mode |
| CT-D02 | Disk full | Write fails gracefully, logs error, pipeline continues in-memory |
| CT-D03 | Corrupt database file | Detected on connect, auto-recreate or backup |
| CT-D04 | Insert duplicate trend IDs | `INSERT OR REPLACE` handles correctly |

#### D. Integration/Pipeline Tests
| Test ID | Description | Expected Behaviour |
|---|---|---|
| CT-I01 | Full cycle with all APIs live | Complete ranked JSON output in <60s |
| CT-I02 | Full cycle with only RSS + GDELT (no auth APIs) | Degraded but functional output |
| CT-I03 | Scheduler runs 48h continuously | No memory leak, consistent cycle times |
| CT-I04 | Export to JSON with 0 trends | Valid JSON with empty `trends: []` |
| CT-I05 | Two niches running concurrently | No state contamination between niches |

---

## Milestones

- [ ] **M1**: Restructured project runs `python main.py --health` without errors
- [ ] **M2**: At least 4/8 scrapers pass health check
- [ ] **M3**: Full cycle (`--once`) produces ranked JSON output
- [ ] **M4**: 48h continuous run with no crashes
- [ ] **M5**: Crash test suite passes 80%+
- [ ] **M6**: Stage 02 (Content Gen) prototype operational
- [ ] **M7**: Stage 03 (Engagement Gate) PoC with mock data
- [ ] **M8**: End-to-end pipeline: trend → content → score → publish
