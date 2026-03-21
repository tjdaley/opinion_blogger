"""
Court Opinion Q&A Clustering Pipeline
======================================
Extracts questions from court_opinions.q_and_a, embeds them,
clusters by semantic similarity, and generates canonical questions
using an LLM. Outputs results for human review before DB commit.

Requirements:
    pip install supabase openai anthropic scikit-learn numpy rich

Usage:
    # Step 1: Extract, embed, and cluster (outputs review file)
    python cluster_questions.py cluster --threshold 0.20

    # Step 2: After reviewing/editing the JSON, commit to database
    python cluster_questions.py commit --file cluster_review.json
"""

import argparse
import json
import re

import numpy as np
from openai import OpenAI
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics.pairwise import cosine_distances
from rich.console import Console
from rich.table import Table

from agents.canonical_question_agent import (
    get_canonical_question_agent,
    CanonicalQuestion,
    user_prompt as canonical_question_user_prompt,
)
from db.connection import (
    court_opinion_repo,
    canonical_question_subject_repo,
    canonical_question_repo,
    opinion_question_mapping_repo,
)
from db.models.canonical_question import (
    ExtractedQuestion,
    ClusterMember,
    ClusterReviewEntry,
)
from util.settings import settings

# ── Configuration ────────────────────────────────────────────────────────────
if settings.llm_embedding_vendor not in ("openai", "gemini"):
    raise ValueError(f"Unsupported LLM vendor for embeddings: {settings.llm_embedding_vendor}")

EMBEDDING_LLM_API_KEY = settings.getattr(f"{settings.llm_embedding_vendor}_api_key")
EMBEDDING_MODEL = settings.getattr(f"{settings.llm_embedding_vendor}_embedding_model")
EMBEDDING_BATCH_SIZE = settings.llm_embedding_batch_size

# Cosine distance threshold for clustering.
# cosine_distance = 1 - cosine_similarity
# 0.15 ≈ 0.85 similarity (tight clusters, fewer false merges)
# 0.20 ≈ 0.80 similarity (moderate — good starting point)
# 0.25 ≈ 0.75 similarity (looser, more aggressive grouping)

# Test results:
#  - .20 created over 900 clusters but many were clearly related questions that should be together
#  - .40 tightened down to about 260 clusters with reasonable grouping. Manually editied down to to about 150
#  - .60 got down to about 45 clusters but it was too aggressive — many unrelated questions got merged together, and the canonical questions were less useful for SEO since they had to be so broad.
DEFAULT_DISTANCE_THRESHOLD = 0.50

console = Console()


# ── Step 1: Extract all questions from court opinions ────────────────────────

def fetch_questions() -> list[ExtractedQuestion]:
    """
    Pull all q_and_a entries from court_opinions.
    Returns a flat list of ExtractedQuestion models.
    """
    console.print("[bold blue]Fetching court opinions with Q&A data...[/]")

    opinions = court_opinion_repo.get_opinions_with_qa()
    all_questions: list[ExtractedQuestion] = []

    for opinion in opinions:
        if not opinion.q_and_a:
            continue
        for idx, qa in enumerate(opinion.q_and_a):
            question = qa.question.strip()
            if question:
                all_questions.append(ExtractedQuestion(
                    court_opinion_id=opinion.id,
                    question_index=idx,
                    question_text=question,
                    answer_text=qa.answer.strip(),
                    case_name=opinion.case_name,
                    slug=opinion.slug,
                ))

    console.print(f"  Extracted [green]{len(all_questions)}[/] questions from "
                  f"[green]{len(opinions)}[/] opinions.")
    return all_questions


# ── Step 2: Generate embeddings ──────────────────────────────────────────────

def embed_questions(questions: list[ExtractedQuestion], llm_client: OpenAI) -> np.ndarray:
    """
    Embed all question texts using OpenAI's embedding model.
    Returns an (N, dim) numpy array of embeddings.
    """
    console.print(f"[bold blue]Generating embeddings for {len(questions)} questions...[/]")
    texts = [q.question_text for q in questions]
    all_embeddings = []

    for i in range(0, len(texts), EMBEDDING_BATCH_SIZE):
        batch = texts[i : i + EMBEDDING_BATCH_SIZE]
        response = llm_client.embeddings.create(
            model=EMBEDDING_MODEL,  # type: ignore
            input=batch,
        )
        batch_embeddings = [item.embedding for item in response.data]
        all_embeddings.extend(batch_embeddings)  # type: ignore
        console.print(f"  Embedded batch {i // EMBEDDING_BATCH_SIZE + 1} "
                      f"({min(i + EMBEDDING_BATCH_SIZE, len(texts))}/{len(texts)})")

    return np.array(all_embeddings)  # type: ignore


# ── Step 3: Cluster by semantic similarity ───────────────────────────────────

def cluster_questions(
    embeddings: np.ndarray,
    distance_threshold: float = DEFAULT_DISTANCE_THRESHOLD,
) -> np.ndarray:
    """
    Agglomerative clustering with cosine distance.
    Returns an array of cluster labels (one per question).

    Questions that don't match anything get their own singleton cluster,
    which is fine — they'll become standalone canonical questions or get
    flagged for review.
    """
    console.print(f"[bold blue]Clustering with distance threshold {distance_threshold}...[/]")

    # Compute full cosine distance matrix
    dist_matrix = cosine_distances(embeddings)

    clustering = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=distance_threshold,
        metric="precomputed",
        linkage="average",  # average linkage works well for semantic clusters
    )
    labels = clustering.fit_predict(dist_matrix)

    n_clusters = len(set(labels))
    singletons = sum(1 for l in set(labels) if list(labels).count(l) == 1)
    multi = n_clusters - singletons

    console.print(f"  Found [green]{n_clusters}[/] clusters: "
                  f"[green]{multi}[/] multi-question groups, "
                  f"[yellow]{singletons}[/] singletons.")
    return labels


# ── Step 4: Generate canonical questions via LLM ─────────────────────────────

def generate_canonical_question(questions: list[str]) -> CanonicalQuestion:
    """
    Given a list of semantically similar questions, generate a
    canonical question (SEO-optimized) and a subject label.
    """
    questions_block = "\n".join(f"  - {q}" for q in questions)
    prompt = canonical_question_user_prompt.format(questions_block=questions_block)
    result = get_canonical_question_agent().run_sync(user_prompt=prompt)
    return result.output


# ── Step 5: Assemble clusters and generate review file ───────────────────────

def build_review_output(
    questions: list[ExtractedQuestion],
    labels: np.ndarray,
    min_cluster_size: int = 1,
) -> list[ClusterReviewEntry]:
    """
    Assemble clusters, generate canonical questions, and produce a
    review-ready data structure.
    """
    # Group questions by cluster label
    clusters: dict[int, list[int]] = {}
    for idx, label in enumerate(labels):
        clusters.setdefault(int(label), []).append(idx)

    # Sort clusters: multi-question clusters first (descending by size),
    # then singletons
    sorted_labels = sorted(
        clusters.keys(),
        key=lambda l: (-len(clusters[l]), l),
    )

    review_data: list[ClusterReviewEntry] = []

    console.print(f"\n[bold blue]Generating canonical questions for "
                  f"{len(sorted_labels)} clusters...[/]")

    for i, label in enumerate(sorted_labels):
        member_indices = clusters[label]
        member_questions = [questions[idx] for idx in member_indices]
        question_texts = [q.question_text for q in member_questions]

        # Skip singletons below threshold if desired
        if len(member_questions) < min_cluster_size:
            continue

        # Generate canonical question (singletons also run through LLM for subject + clean phrasing)
        canonical = generate_canonical_question(question_texts)

        entry = ClusterReviewEntry(
            cluster_id=int(label),
            canonical_question=canonical.canonical_question,
            subject=canonical.subject,
            member_count=len(member_questions),
            members=[
                ClusterMember(
                    court_opinion_id=mq.court_opinion_id,
                    question_index=mq.question_index,
                    question_text=mq.question_text,
                    case_name=mq.case_name,
                    slug=mq.slug,
                )
                for mq in member_questions
            ],
        )
        review_data.append(entry)

        if (i + 1) % 10 == 0 or i == len(sorted_labels) - 1:
            console.print(f"  Processed {i + 1}/{len(sorted_labels)} clusters")

    return review_data


def save_review_file(review_data: list[ClusterReviewEntry], filepath: str):
    """Save the review data as formatted JSON."""
    serialized = [entry.model_dump() for entry in review_data]
    with open(filepath, "w") as f:
        json.dump(serialized, f, indent=2, ensure_ascii=False)
    console.print(f"\n[bold green]Review file saved to: {filepath}[/]")
    console.print("Edit this file to:")
    console.print("  • Refine canonical questions and subjects")
    console.print("  • Set needs_review=false for approved clusters")
    console.print("  • Delete clusters that shouldn't become canonical questions")
    console.print("  • Move members between clusters if grouping is wrong")
    console.print(f"\nThen run: [bold]python cluster_questions.py commit --file {filepath}[/]")


# ── Step 6: Commit approved clusters to database ─────────────────────────────

def commit_to_database(filepath: str):
    """
    Read the reviewed JSON and write approved clusters to:
      - canonical_question_subjects table (get or create)
      - canonical_questions table
      - opinion_question_mapping table
    """
    with open(filepath) as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            console.print(f"[red]Error reading JSON file: {e}[/]")
            return
        review_entries = [ClusterReviewEntry(**c) for c in data]

    approved = [c for c in review_entries if not c.needs_review]

    if not approved:
        console.print("[yellow]No approved clusters found (needs_review must be false).[/]")
        return

    console.print(f"[bold blue]Committing {len(approved)} approved clusters...[/]")

    for cluster in approved:
        # 1. Get or create the subject
        subject = canonical_question_subject_repo.get_or_create_by_name(cluster.subject)

        # 2. Upsert the canonical question
        slug = _slugify(cluster.canonical_question)
        cq_record = canonical_question_repo.upsert_by_slug({
            "question": cluster.canonical_question,
            "subject_id": subject.id,
            "slug": slug,
        })

        # 3. Upsert opinion_question_mapping rows
        for member in cluster.members:
            opinion_question_mapping_repo.upsert_mapping({
                "canonical_question_id": cq_record.id,
                "court_opinion_id": member.court_opinion_id,
                "source_question_index": member.question_index,
                "source_question_text": member.question_text,
            })

        console.print(f"  ✓ [green]{cluster.canonical_question}[/] "
                      f"→ {len(cluster.members)} opinions linked")

    console.print(f"\n[bold green]Done. {len(approved)} canonical questions committed.[/]")


def _slugify(text: str) -> str:
    """Simple slug generator for canonical question URLs."""
    slug = text.lower().strip()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s-]+', '-', slug)
    return slug[:120]  # reasonable max length for a URL slug


# ── Diagnostics: Preview distance distribution ───────────────────────────────

def preview_distances(embeddings: np.ndarray):
    """
    Print distance distribution to help tune the threshold.
    Run this first if you're not sure what threshold to use.
    """
    console.print("[bold blue]Computing pairwise cosine distances...[/]")
    dist_matrix = cosine_distances(embeddings)

    # Only look at upper triangle (exclude diagonal)
    upper = dist_matrix[np.triu_indices_from(dist_matrix, k=1)]

    percentiles = [5, 10, 15, 20, 25, 50, 75, 90]
    table = Table(title="Cosine Distance Distribution (lower = more similar)")
    table.add_column("Percentile", style="cyan")
    table.add_column("Distance", style="green")
    table.add_column("≈ Similarity", style="yellow")

    for p in percentiles:
        val = np.percentile(upper, p)
        table.add_row(f"{p}th", f"{val:.4f}", f"{1 - val:.4f}")

    console.print(table)
    console.print("\n[bold]Interpretation:[/]")
    console.print("  • Your threshold should be near the lower percentiles")
    console.print("  • Start with 0.20 and adjust based on review quality")
    console.print("  • If you see too many bad merges, lower the threshold")
    console.print("  • If obvious matches are staying separate, raise it")


# ── Incremental mode: Process only new/unmatched questions ───────────────────

def fetch_unmatched_questions() -> list[ExtractedQuestion]:
    """
    Fetch only questions that don't already have a canonical mapping.
    Useful for incremental runs as new court opinions are scraped.
    """
    console.print("[bold blue]Fetching unmapped questions...[/]")

    mapped_keys = opinion_question_mapping_repo.get_all_mapped_keys()
    all_questions = fetch_questions()
    unmatched = [
        q for q in all_questions
        if (q.court_opinion_id, q.question_index) not in mapped_keys
    ]

    console.print(f"  [green]{len(unmatched)}[/] unmapped questions "
                  f"(of {len(all_questions)} total)")
    return unmatched


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Cluster court opinion Q&A into canonical questions"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # cluster command
    cluster_parser = subparsers.add_parser(
        "cluster", help="Extract, embed, cluster, and generate review file"
    )
    cluster_parser.add_argument(
        "--threshold", type=float, default=DEFAULT_DISTANCE_THRESHOLD,
        help=f"Cosine distance threshold (default: {DEFAULT_DISTANCE_THRESHOLD})"
    )
    cluster_parser.add_argument(
        "--output", type=str, default="cluster_review.json",
        help="Output file path for review (default: cluster_review.json)"
    )
    cluster_parser.add_argument(
        "--min-cluster", type=int, default=1,
        help="Minimum cluster size to include (default: 1, i.e. include singletons)"
    )
    cluster_parser.add_argument(
        "--incremental", action="store_true",
        help="Only process questions not yet mapped to a canonical question"
    )
    cluster_parser.add_argument(
        "--preview-distances", action="store_true",
        help="Show distance distribution and exit (helps tune threshold)"
    )

    # commit command
    commit_parser = subparsers.add_parser(
        "commit", help="Commit reviewed clusters to database"
    )
    commit_parser.add_argument(
        "--file", type=str, required=True,
        help="Path to the reviewed JSON file"
    )

    args = parser.parse_args()

    if args.command == "cluster":
        openai_client = OpenAI(api_key=EMBEDDING_LLM_API_KEY)

        # Extract questions
        if args.incremental:
            questions = fetch_unmatched_questions()
        else:
            questions = fetch_questions()

        if not questions:
            console.print("[yellow]No questions found to cluster.[/]")
            return

        # Embed
        embeddings = embed_questions(questions, openai_client)

        # Optionally preview distances and exit
        if args.preview_distances:
            preview_distances(embeddings)
            return

        # Cluster
        labels = cluster_questions(embeddings, args.threshold)

        # Generate canonical questions and review file
        review_data = build_review_output(
            questions, labels, args.min_cluster
        )

        save_review_file(review_data, args.output)

        # Print summary table
        multi = [c for c in review_data if c.member_count > 1]
        if multi:
            table = Table(title=f"Top Clusters (multi-question, {len(multi)} total)")
            table.add_column("#", style="dim")
            table.add_column("Canonical Question", style="green", max_width=60)
            table.add_column("Subject", style="cyan")
            table.add_column("Members", style="yellow", justify="right")

            for i, c in enumerate(multi[:20], 1):
                table.add_row(
                    str(i), c.canonical_question,
                    c.subject, str(c.member_count)
                )
            console.print(table)

    elif args.command == "commit":
        commit_to_database(args.file)


if __name__ == "__main__":
    main()
