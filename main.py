"""
main.py — VELOCI Trend Intelligence Engine

Entry point. Runs the full scrape → NLP → rank pipeline on a 30-minute
schedule for all configured niches. Saves results to SQLite and prints
the top trends to console.

Usage:
  # Set up env vars (or edit config.py directly):
  export REDDIT_CLIENT_ID="..."
  export REDDIT_CLIENT_SECRET="..."
  export YOUTUBE_API_KEY="..."
  export TWITTER_BEARER_TOKEN="..."
  export NEWS_API_KEY="..."

  # Install dependencies:
  pip install -r requirements.txt
  python -m spacy download en_core_web_sm
  playwright install chromium

  # Run:
  python main.py

  # Run once (no scheduler):
  python main.py --once

  # Run for a specific niche:
  python main.py --niche tech_ai

Output:
  Console: ranked trend list per niche
  veloci.db: SQLite database with all trends and performance data
  veloci_scraper.log: Full log
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
from datetime import datetime, timezone
from typing import List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from config import NICHES, SCRAPE_INTERVAL_MINUTES, LOG_FILE, LOG_LEVEL
from pipeline.aggregator import TrendAggregator
from pipeline.nlp_processor import TrendCluster
from pipeline.script_generator import ScriptGenerator, ScriptExporter
from storage.database import Database


# ─── LOGGING SETUP ───────────────────────────────────────────────────────────

logger.remove()
logger.add(sys.stderr, level=LOG_LEVEL, colorize=True,
           format="<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | {message}")
logger.add(LOG_FILE, level="DEBUG", rotation="50 MB", retention="7 days")


# ─── GLOBALS ─────────────────────────────────────────────────────────────────

aggregator = TrendAggregator()
db = Database()


# ─── CORE CYCLE ──────────────────────────────────────────────────────────────

async def run_scrape_cycle(niche: Optional[str] = None) -> dict:
    """
    Run one full scrape cycle.

    Args:
        niche: If given, run only this niche. Otherwise run all.

    Returns:
        dict mapping niche → list of ranked TrendClusters
    """
    logger.info(f"{'='*60}")
    logger.info(f"VELOCI cycle started at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
    logger.info(f"{'='*60}")

    if niche:
        results = {niche: await aggregator.run_cycle(niche)}
    else:
        results = await aggregator.run_all_niches()

    # Persist to DB
    all_trends: List[TrendCluster] = []
    for niche_trends in results.values():
        all_trends.extend(niche_trends)

    if all_trends:
        await db.save_trends(all_trends)
        await db.save_signals(all_trends)

    # Print results
    _print_results(results)

    return results


def _print_results(results: dict) -> None:
    """Pretty-print ranked trends to console."""
    for niche, trends in results.items():
        niche_info = NICHES.get(niche, {})
        display_name = niche_info.get("display_name", niche)

        print(f"\n{'─'*60}")
        print(f"  {display_name.upper()} — Top Trends")
        print(f"{'─'*60}")

        if not trends:
            print("  No trends found this cycle.")
            continue

        for i, cluster in enumerate(trends[:10], 1):
            tier_emoji = {"early": "🟢", "emerging": "🟡", "trending": "🟠", "saturated": "🔴"}.get(cluster.tier, "⚪")
            print(f"\n  {i:2}. {tier_emoji} [{cluster.tier.upper()}] Score: {cluster.composite_score:.3f}")
            print(f"      Topic:     {cluster.topic[:70]}")
            print(f"      Keywords:  {', '.join(cluster.keywords[:5])}")
            print(f"      Platforms: {' · '.join(cluster.platforms[:4])}")
            print(f"      Velocity:  {cluster.velocity_score:.2f}  "
                  f"Cross-platform: {cluster.cross_platform_score:.2f}  "
                  f"Novelty: {cluster.novelty_score:.2f}")
            if cluster.content_angles:
                print(f"      Angle A:   {cluster.content_angles[0]}")

    print(f"\n{'='*60}")
    print(f"  Cycle complete. {sum(len(v) for v in results.values())} total trends.")
    print(f"{'='*60}\n")


async def export_trends_json(niche: str, output_path: str = "trends.json") -> None:
    """Export current ranked trends to JSON (for downstream modules)."""
    results = await run_scrape_cycle(niche)
    trends = results.get(niche, [])
    data = {
        "niche": niche,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "trends": [t.to_dict() for t in trends],
    }
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    logger.info(f"Exported {len(trends)} trends to {output_path}")


async def export_trends_csv(niche: str, output_path: str = "trends.csv") -> None:
    """
    Export current ranked trends to CSV.
    One row per trend with ALL fields needed for Stage 02 content generation.
    """
    results = await run_scrape_cycle(niche)
    trends = results.get(niche, [])

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "rank", "tier", "composite_score", "topic", "summary",
            "keywords", "entities", "platforms", "platform_breakdown",
            "velocity", "cross_platform", "novelty",
            "sentiment", "engagement_potential", "signal_count",
            "suggested_hook", "suggested_duration", "suggested_format",
            "suggested_hashtags", "content_angles",
            "source_urls", "niche", "first_seen", "generated_at"
        ])
        for i, t in enumerate(trends, 1):
            writer.writerow([
                i,
                t.tier,
                round(t.composite_score, 4),
                t.topic[:120],
                t.summary[:200],
                "|".join(t.keywords[:8]),
                "|".join(t.entities[:5]),
                "|".join(t.platforms[:6]),
                json.dumps(t.platform_breakdown),
                round(t.velocity_score, 4),
                round(t.cross_platform_score, 4),
                round(t.novelty_score, 4),
                round(t.sentiment_score, 4),
                round(t.engagement_potential, 4),
                len(t.sources),
                t.suggested_hook,
                t.suggested_duration,
                t.suggested_format,
                "|".join(t.suggested_hashtags[:10]),
                "|".join(t.content_angles[:4]) if t.content_angles else "",
                "|".join(t.source_urls[:5]),
                niche,
                t.first_seen.isoformat() if t.first_seen else "",
                datetime.now(timezone.utc).isoformat()
            ])

    logger.info(f"Exported {len(trends)} trends to CSV: {output_path}")


async def export_trends_full(
    niche: str, output_dir: str = "output"
) -> None:
    """
    Export trends into BOTH JSON and CSV formats globally per niche.
    """
    results = await run_scrape_cycle(niche)
    trends = results.get(niche, [])

    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    # ── JSON (full detail) ──────────────────────────────────────────────────
    json_path = os.path.join(output_dir, f"veloci_trends_{niche}_{ts}.json")
    output_data = {
        "veloci_version": "2.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "niche": niche,
        "niche_display": NICHES.get(niche, {}).get("display_name", niche),
        "total_trends": len(trends),
        "trends": [t.to_dict() for t in trends],
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, default=str, ensure_ascii=False)

    # ── CSV (flat for spreadsheets / pandas) ────────────────────────────────
    csv_path = os.path.join(output_dir, f"veloci_trends_{niche}_{ts}.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "rank", "tier", "composite_score", "topic", "summary",
            "keywords", "entities", "platforms", "platform_breakdown",
            "velocity", "cross_platform", "novelty",
            "sentiment", "engagement_potential", "signal_count",
            "suggested_hook", "suggested_duration", "suggested_format",
            "suggested_hashtags", "content_angles",
            "source_urls", "niche", "first_seen"
        ])
        for i, t in enumerate(trends, 1):
            writer.writerow([
                i, t.tier, round(t.composite_score, 4),
                t.topic[:120], t.summary[:200],
                "|".join(t.keywords[:8]),
                "|".join(t.entities[:5]),
                "|".join(t.platforms[:6]),
                json.dumps(t.platform_breakdown),
                round(t.velocity_score, 4),
                round(t.cross_platform_score, 4),
                round(t.novelty_score, 4),
                round(t.sentiment_score, 4),
                round(t.engagement_potential, 4),
                len(t.sources),
                t.suggested_hook,
                t.suggested_duration,
                t.suggested_format,
                "|".join(t.suggested_hashtags[:10]),
                "|".join(t.content_angles[:4]) if t.content_angles else "",
                "|".join(t.source_urls[:5]),
                niche,
                t.first_seen.isoformat() if t.first_seen else "",
            ])

    logger.info(f"Exported {niche}: {json_path} + {csv_path} ({len(trends)} trends)")


# ─── STAGE 02: SCRIPT GENERATION ─────────────────────────────────────────────

async def generate_scripts_for_niche(
    niche: str, output_dir: str = "output", scripts_per_trend: int = 4
) -> None:
    """
    Full pipeline: Scrape → NLP → Rank → Generate Scripts → Export.
    
    Runs Stage 01 (trend detection) then Stage 02 (script generation)
    in one shot. Exports trends AND scripts to output_dir.
    """
    # Stage 01: Get ranked trends
    results = await run_scrape_cycle(niche)
    trends = results.get(niche, [])

    if not trends:
        logger.warning(f"[Scripts] No trends found for {niche} — cannot generate scripts")
        return

    # Stage 02: Generate scripts
    gen = ScriptGenerator()
    scripts = gen.generate_for_trends(trends, niche, scripts_per_trend)

    if not scripts:
        logger.warning(f"[Scripts] Script generation returned 0 scripts for {niche}")
        return

    # Export everything
    os.makedirs(output_dir, exist_ok=True)

    # Export trends (Stage 01 output)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    trend_json = os.path.join(output_dir, f"veloci_trends_{niche}_{ts}.json")
    trend_data = {
        "veloci_version": "2.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "niche": niche,
        "niche_display": NICHES.get(niche, {}).get("display_name", niche),
        "total_trends": len(trends),
        "trends": [t.to_dict() for t in trends],
    }
    with open(trend_json, "w", encoding="utf-8") as f:
        json.dump(trend_data, f, indent=2, default=str, ensure_ascii=False)
    logger.info(f"[Scripts] Trends saved: {trend_json}")

    # Export scripts (Stage 02 output)
    paths = ScriptExporter.export_all(scripts, niche, output_dir)

    # Print top scripts to console
    ScriptExporter.print_top_scripts(scripts, max_show=12)

    logger.info(
        f"[Scripts] Pipeline complete for {niche}: "
        f"{len(trends)} trends → {len(scripts)} scripts"
    )


# ─── ENTRY POINT ─────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="VELOCI Trend Intelligence Engine")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    parser.add_argument("--niche", type=str, default=None,
                        help=f"Run single niche: {list(NICHES.keys())}")
    parser.add_argument("--health", action="store_true", help="Run health checks only")
    parser.add_argument("--export", type=str, default=None,
                        help="Export trends JSON to this path")
    parser.add_argument("--csv", type=str, default=None,
                        help="Export trends CSV to this path")
    parser.add_argument("--output", type=str, default=None,
                        help="Export JSON + CSV to this directory (for Stage 02 pipeline)")
    parser.add_argument("--scripts", type=str, default=None,
                        help="Generate video scripts and export to this directory")
    parser.add_argument("--scripts-per-trend", type=int, default=4,
                        help="Number of scripts to generate per trend (default: 4)")
    parser.add_argument("--status", action="store_true",
                        help="Show per-scraper health status table")
    args = parser.parse_args()

    # Connect DB
    await db.connect()

    if args.health:
        logger.info("Running health checks on all scrapers...")
        health = await aggregator.check_all_health()
        for scraper, status in health.items():
            icon = "✓" if status == "OK" else "✗"
            print(f"  {icon} {scraper:20s} {status}")
        await db.close()
        return

    if args.export:
        await export_trends_json(args.niche or "tech_ai", args.export)
        await db.close()
        return

    if args.csv:
        await export_trends_csv(args.niche or "tech_ai", args.csv)
        await db.close()
        return

    if args.output:
        niches_to_run = [args.niche] if args.niche else list(NICHES.keys())
        for n in niches_to_run:
            await export_trends_full(n, args.output)
        await db.close()
        return

    if args.scripts:
        niches_to_run = [args.niche] if args.niche else list(NICHES.keys())
        for n in niches_to_run:
            await generate_scripts_for_niche(
                n, args.scripts, args.scripts_per_trend
            )
        await db.close()
        return

    if args.status:
        logger.info("Checking scraper status...")
        health = await aggregator.check_all_health()
        print(f"\n{'─'*50}")
        print(f"  VELOCI Scraper Status")
        print(f"{'─'*50}")
        for scraper, status in health.items():
            icon = "✅" if status == "OK" else "❌"
            print(f"  {icon}  {scraper:25s}  {status}")
        print(f"{'─'*50}\n")
        await db.close()
        return

    if args.once:
        await run_scrape_cycle(args.niche)
        await db.close()
        return

    # Scheduled mode: run every SCRAPE_INTERVAL_MINUTES
    logger.info(
        f"Starting VELOCI scheduler. "
        f"Cycle every {SCRAPE_INTERVAL_MINUTES} minutes. "
        f"Niches: {args.niche or list(NICHES.keys())}"
    )

    async def auto_cycle(n):
        if args.output:
            niches_to_run = [n] if n else list(NICHES.keys())
            for current_niche in niches_to_run:
                # Fully autonomous: generates exports to output/ AND dumps to DB
                await export_trends_full(current_niche, args.output or "output")
        else:
            await run_scrape_cycle(n)

    # Run immediately, then schedule
    await auto_cycle(args.niche)

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        auto_cycle,
        "interval",
        minutes=SCRAPE_INTERVAL_MINUTES,
        args=[args.niche],
        id="main_cycle",
        max_instances=1,
    )
    scheduler.start()

    try:
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down VELOCI...")
        scheduler.shutdown()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
