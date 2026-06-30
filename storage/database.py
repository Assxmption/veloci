"""
storage/database.py

Async SQLite storage for trends, signals, and channel performance.

Tables:
  trends       — ranked TrendCluster records per cycle
  signals      — individual RawSignal records (for velocity history)
  channel_perf — post performance per channel (feed for RL agent)
  content_log  — what content was generated and published

We use aiosqlite for non-blocking DB access (doesn't stall the scraper loop).
"""

from __future__ import annotations

import json
from datetime import datetime
from datetime import timezone
from typing import List, Optional

import aiosqlite
from loguru import logger

from config import DATABASE_PATH
from pipeline.nlp_processor import TrendCluster


CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS trends (
    id              TEXT PRIMARY KEY,
    niche           TEXT NOT NULL,
    topic           TEXT NOT NULL,
    keywords        TEXT,           -- JSON array
    entities        TEXT,           -- JSON array
    platforms       TEXT,           -- JSON array
    summary         TEXT,
    composite_score REAL,
    velocity_score  REAL,
    cross_platform_score REAL,
    novelty_score   REAL,
    sentiment_score REAL,
    tier            TEXT,
    content_angles  TEXT,           -- JSON array
    source_count    INTEGER,
    scraped_at      TEXT,
    first_seen      TEXT,
    embedding       BLOB            -- Numpy array as bytes (optional)
);

CREATE TABLE IF NOT EXISTS signals (
    id              TEXT PRIMARY KEY,
    trend_id        TEXT,
    platform        TEXT,
    source_id       TEXT,
    url             TEXT,
    title           TEXT,
    score           INTEGER,
    views           INTEGER,
    comments        INTEGER,
    niche           TEXT,
    published_at    TEXT,
    scraped_at      TEXT,
    raw_data        TEXT            -- JSON
);

CREATE TABLE IF NOT EXISTS channel_perf (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id      TEXT NOT NULL,
    niche           TEXT,
    post_id         TEXT,
    platform        TEXT,
    trend_id        TEXT,
    posted_at       TEXT,
    views_1h        INTEGER DEFAULT 0,
    views_24h       INTEGER DEFAULT 0,
    likes           INTEGER DEFAULT 0,
    comments        INTEGER DEFAULT 0,
    watch_time_pct  REAL DEFAULT 0,
    velocity_score  REAL DEFAULT 0,    -- First-hour velocity (RL reward signal)
    updated_at      TEXT
);

CREATE TABLE IF NOT EXISTS content_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trend_id        TEXT,
    channel_id      TEXT,
    niche           TEXT,
    angle           TEXT,              -- broad / deep_dive / reaction / data
    script          TEXT,
    caption         TEXT,
    hashtags        TEXT,              -- JSON
    video_path      TEXT,
    thumbnail_path  TEXT,
    engagement_pred REAL,             -- Pre-publish predicted score
    status          TEXT DEFAULT 'pending',  -- pending / published / failed
    created_at      TEXT,
    published_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_trends_niche ON trends (niche, scraped_at);
CREATE INDEX IF NOT EXISTS idx_signals_trend ON signals (trend_id);
CREATE INDEX IF NOT EXISTS idx_channel_perf_channel ON channel_perf (channel_id, posted_at);
"""


class Database:
    """Async SQLite database for VELOCI persistence."""

    def __init__(self, path: str = DATABASE_PATH):
        self.path = path
        self._db: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(CREATE_TABLES_SQL)
        await self._db.commit()
        logger.info(f"[DB] Connected to {self.path}")

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    async def save_trends(self, trends: List[TrendCluster]) -> None:
        """Upsert a list of TrendCluster objects."""
        if not self._db:
            raise RuntimeError("Database not connected")

        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for t in trends:
            rows.append((
                t.cluster_id,
                t.niche or "",
                t.topic,
                json.dumps(t.keywords),
                json.dumps(t.entities),
                json.dumps(t.platforms),
                t.summary,
                t.composite_score,
                t.velocity_score,
                t.cross_platform_score,
                t.novelty_score,
                t.sentiment_score,
                t.tier,
                json.dumps(t.content_angles),
                len(t.sources),
                now,
                t.first_seen.isoformat(),
            ))

        await self._db.executemany(
            """INSERT OR REPLACE INTO trends
               (id, niche, topic, keywords, entities, platforms, summary,
                composite_score, velocity_score, cross_platform_score,
                novelty_score, sentiment_score, tier, content_angles,
                source_count, scraped_at, first_seen)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            rows
        )
        await self._db.commit()
        logger.debug(f"[DB] Saved {len(trends)} trends")

    async def save_signals(self, trends: List[TrendCluster]) -> None:
        """Save RawSignals associated with trend clusters."""
        if not self._db:
            raise RuntimeError("Database not connected")

        rows = []
        for cluster in trends:
            for signal in cluster.sources[:10]:  # Save top 10 per cluster
                rows.append((
                    f"{cluster.cluster_id}_{signal.source_id}",
                    cluster.cluster_id,
                    signal.platform,
                    signal.source_id,
                    signal.url,
                    signal.title[:500],
                    signal.score,
                    signal.views,
                    signal.comments,
                    signal.niche or "",
                    signal.published_at.isoformat() if signal.published_at else None,
                    signal.scraped_at.isoformat(),
                    json.dumps(signal.raw_data),
                ))

        await self._db.executemany(
            """INSERT OR IGNORE INTO signals
               (id, trend_id, platform, source_id, url, title, score, views,
                comments, niche, published_at, scraped_at, raw_data)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            rows
        )
        await self._db.commit()

    async def get_recent_trends(
        self, niche: str, hours: int = 48
    ) -> List[dict]:
        """Fetch trends from the last N hours for a niche."""
        if not self._db:
            raise RuntimeError("Database not connected")
        cutoff = (
            datetime.now(timezone.utc).replace(microsecond=0) -
            __import__("datetime").timedelta(hours=hours)
        ).isoformat()
        async with self._db.execute(
            """SELECT * FROM trends
               WHERE niche = ? AND scraped_at >= ?
               ORDER BY composite_score DESC""",
            (niche, cutoff)
        ) as cursor:
            rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def update_channel_performance(
        self,
        channel_id: str,
        post_id: str,
        platform: str,
        trend_id: str,
        niche: str,
        views_1h: int = 0,
        views_24h: int = 0,
        likes: int = 0,
        comments: int = 0,
        watch_time_pct: float = 0.0,
    ) -> None:
        """Update post-publish performance data for the RL feedback loop."""
        if not self._db:
            raise RuntimeError("Database not connected")

        velocity_score = min(views_1h / max(views_24h, 1), 1.0)
        now = datetime.now(timezone.utc).isoformat()

        await self._db.execute(
            """INSERT INTO channel_perf
               (channel_id, niche, post_id, platform, trend_id,
                views_1h, views_24h, likes, comments, watch_time_pct,
                velocity_score, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(post_id) DO UPDATE SET
                views_1h=excluded.views_1h, views_24h=excluded.views_24h,
                likes=excluded.likes, comments=excluded.comments,
                watch_time_pct=excluded.watch_time_pct,
                velocity_score=excluded.velocity_score,
                updated_at=excluded.updated_at""",
            (channel_id, niche, post_id, platform, trend_id,
             views_1h, views_24h, likes, comments, watch_time_pct,
             velocity_score, now)
        )
        await self._db.commit()

    async def get_channel_performance_history(
        self, channel_id: str, limit: int = 100
    ) -> List[dict]:
        """Fetch performance history for a channel (for RL training)."""
        if not self._db:
            raise RuntimeError("Database not connected")
        async with self._db.execute(
            """SELECT * FROM channel_perf
               WHERE channel_id = ?
               ORDER BY posted_at DESC LIMIT ?""",
            (channel_id, limit)
        ) as cursor:
            rows = await cursor.fetchall()
        return [dict(row) for row in rows]
