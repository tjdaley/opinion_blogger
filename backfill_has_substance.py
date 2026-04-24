"""
backfill_has_substance.py

Retroactively classifies existing court_opinions records for substance.
Runs against the summary field as a proxy for opinion text.
Records failing the substance test are flagged has_substance=False
and excluded from the tagging backfill.
"""

import asyncio
import logging
from anthropic import AsyncAnthropic
import json
from supabase import create_client
from util.settings import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SUPABASE_URL = settings.supabase_url
SUPABASE_KEY = settings.supabase_service_role_key
ANTHROPIC_KEY = settings.anthropic_api_key

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
client = AsyncAnthropic(api_key=ANTHROPIC_KEY)

SUBSTANCE_PROMPT = """You are an elite Texas Appellate Attorney reviewing 
a summary of a Texas family law appellate opinion.

Determine whether this opinion contains substantive legal analysis 
worth indexing in a practitioner research database.

Answer false if the opinion is primarily:
- Dismissed for want of prosecution or failure to file a brief
- Voluntarily dismissed or withdrawn by the parties
- A mandamus denial concluding only that relator failed to meet 
  the burden, with no analysis of what conduct does or does not 
  constitute a clear abuse of discretion
- A dismissal for purely administrative default with no legal 
  rule of practical consequence to practitioners

Answer true if the opinion contains any:
- Substantive holding on a legal question
- Analysis of what conduct does or does not meet a legal standard
- A procedural rule with practical consequence to practitioners

Return JSON only. No preamble. No markdown fences.
Format: {"has_substance": true} or {"has_substance": false}
{"rationale": "one sentence explaining the determination having a mx of 15 words"}
"""


async def classify_summary(summary: str) -> dict:
    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=150,  # up from 100 — rationale needs room
        system=SUBSTANCE_PROMPT,
        messages=[{"role": "user", "content": summary}]
    )
    
    raw = response.content[0].text.strip()
    logger.debug("Raw LLM response: %s", raw)
    
    # Strip markdown fences defensively — model ignores the instruction sometimes
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    
    return json.loads(raw)

async def process_batch(batch: list, semaphore: asyncio.Semaphore, 
                        dry_run: bool) -> tuple[int, int, int]:
    """Process a batch. Returns (transitioned, skipped, failed)."""
    
    async def classify_one(row: dict) -> tuple[str, bool, str]:
        async with semaphore:
            try:
                result = await classify_summary(row["body"])
                return row["id"], result["has_substance"], result.get("rationale", "")
            except Exception as e:
                logger.error("Classification failed for id=%s: %s", row["id"], e)
                return row["id"], None, str(e)

    tasks = [classify_one(row) for row in batch]
    results = await asyncio.gather(*tasks)

    transitioned = skipped = failed = 0

    for opinion_id, has_substance, rationale in results:
        if has_substance is None:
            failed += 1
            continue

        case_name = next(r["case_name"] for r in batch if r["id"] == opinion_id)
        status = "✓ substance" if has_substance else "✗ no-substance"
        logger.info("[%s] id=%s | %s | %s", status, opinion_id, case_name, rationale)

        if not dry_run:
            try:
                supabase.table("opinion_tracking").update({
                    "has_substance": has_substance
                }).eq("id", opinion_id).execute()
                transitioned += 1
            except Exception as e:
                logger.error("DB update failed for id=%s: %s", opinion_id, e)
                failed += 1
        else:
            transitioned += 1

        if not has_substance:
            skipped += 1

    return transitioned, skipped, failed


async def run_backfill(dry_run: bool = True, batch_size: int = 50, 
                       concurrency: int = 10, limit: int | None = None):
    """
    Main backfill runner.
    
    Args:
        dry_run: If True, classify but don't write to DB
        batch_size: Records per DB fetch
        concurrency: Max simultaneous Claude calls
        limit: Cap total records processed (None = all)
    """
    logger.info("Starting substance backfill (dry_run=%s)", dry_run)

    # Fetch only records where has_substance is null (not yet classified)
    query = (
        supabase.table("opinion_tracking")
        .select("id, case_name, body")
        .neq("status", "rejected")
        .is_("has_substance", "null")
        .order("created_at")
    )
    if limit:
        query = query.limit(limit)

    rows = query.execute().data
    total = len(rows)
    logger.info("Found %d unclassified records", total)

    if not rows:
        logger.info("Nothing to process.")
        return

    semaphore = asyncio.Semaphore(concurrency)
    all_transitioned = all_skipped = all_failed = 0

    # Process in batches to avoid memory pressure
    for i in range(0, total, batch_size):
        batch = rows[i:i + batch_size]
        logger.info("Processing batch %d-%d of %d", i + 1, min(i + batch_size, total), total)

        t, s, f = await process_batch(batch, semaphore, dry_run)
        all_transitioned += t
        all_skipped += s
        all_failed += f

    logger.info(
        "Backfill complete. Processed=%d | No-substance=%d | Failed=%d",
        all_transitioned, all_skipped, all_failed
    )
    
    if dry_run:
        logger.info("DRY RUN — no database writes were made.")


if __name__ == "__main__":
    # Friday pass 1: dry run on 50 to calibrate
    # asyncio.run(run_backfill(dry_run=True, limit=50))

    # Friday pass 2: full backfill live
    asyncio.run(run_backfill(dry_run=False, limit=None))
