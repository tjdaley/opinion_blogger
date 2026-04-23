import re
from typing import Any, Optional, Union
import json
import time

from agents.opinion_tagger_agent import get_opinion_tagger_agent, user_prompt as tagger_prompt
from db.connection import court_opinion_repo
from db.supabasemanager import SupabaseManager

supabase_manager = SupabaseManager()

def extract_case_summary(blog_post: str) -> str:
    """
    Extracts the Case Summary section from the blog post.
    Returns only the content between ## Case Summary 
    and the next ## header.
    """
    pattern = r'(## Case Summary.*?)(?=\n## |\Z)'
    match = re.search(pattern, blog_post, re.DOTALL)
    
    if match:
        return match.group(1).strip()
    
    # Fallback: return full blog post if structure unexpected
    return blog_post

async def run_backfill(dry_run: bool = False, limit: Optional[int] = None):
    agent = get_opinion_tagger_agent()
    condition: dict[str, Any] = {
        "tags_top_k": "{}",
        "opinion_tracking.is_family_law": True,
    }
    selection = "*, opinion_tracking!inner(is_family_law)"
    if limit:
        opinions, _ = court_opinion_repo.select_many(condition=condition, selection=selection, start=0, end=limit)
    else:
        opinions, _ = court_opinion_repo.select_many(condition=condition, selection=selection)

    print(f"Found {len(opinions)} untagged opinions")

    success_count = 0
    failed: list[dict[str, Union[int, str]]] = []
    success: list[dict[str, Union[int, str]]] = []

    for i, opinion in enumerate(opinions):
        case_name = opinion.case_name
        print(f"[{i+1}/{len(opinions)}] {case_name}...", end=" ")

        if not opinion.blog_post:
            print("SKIP — no blog_post")
            continue

        try:
            text_to_agent = extract_case_summary(opinion.blog_post)
            result = await agent.run(tagger_prompt.format(blog_post=text_to_agent))
            tags = result.output
            opinion.tags_top_k = tags.tags_top_k
            opinion.tags_discarded = tags.tags_discarded
            opinion.tag_rationale = tags.tag_rationale

            if not dry_run:
                court_opinion_repo.update(opinion.id, **opinion.model_dump(mode="json"))
            else:
                log_json = opinion.model_dump(mode="json")
                log_json["text_passed_to_agent"] = text_to_agent
                success.append(log_json)

            print(f"OK — {sorted(tags.tags_top_k)}")
            success_count += 1

        except Exception as e:
            print(f"FAILED — {e}")
            failed.append({"id": opinion.id, "case_name": case_name, "error": str(e)})

        # Rate limit courtesy pause
        time.sleep(0.5)

    print(f"\nDone. {success_count} tagged, {len(failed)} failed.")
    if failed:
        print("Failed cases:")
        for f in failed:
            print(f"  [{f['id']}] {f['case_name']}: {f['error']}")

    if dry_run and success:
        with open("dry_run_success.json", "w", encoding="utf-8") as f:
            json.dump(success, f, ensure_ascii=False, indent=2)


