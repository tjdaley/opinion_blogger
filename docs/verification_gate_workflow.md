# Opinion Blogger Workflow (with Verification Gate)

End-to-end flow from a court releasing an opinion to that opinion appearing on
txfamlaw.com. Highlights the verification gate, the WordPress human-review
branch, and the revert-loop backstop introduced by the integration patches.

## Pipeline

```mermaid
flowchart TD
    START([Timer: 'scraper_job all'<br/>or operator command]) --> SCRAPE[scrape<br/>SCOTX + COA]
    SCRAPE --> OT[("opinion_tracking<br/>status=pending-analysis")]
    OT --> CLASSIFY[classify<br/>family-law + metadata]
    CLASSIFY --> ANALYZE[analyze<br/>generate blog post<br/>+ Q&A]
    ANALYZE --> GATE{{verification gate<br/>independent LLM<br/>vs. opinion text}}

    GATE -->|passed=true<br/>no high-severity flags| GP[("opinion_tracking<br/>gate_passed=true")]
    GATE -->|passed=false<br/>flags found| GF[("opinion_tracking<br/>gate_passed=false<br/>gate_flags<br/>gate_report_html")]
    GATE -->|exception<br/>fail-SAFE| GF

    GP --> SEO[seo-titles<br/>backfill]
    GF --> SEO
    SEO --> UPLOAD[upload to WordPress]

    UPLOAD -->|gate_passed=true| WPDRAFT[/"WP post<br/>status=draft<br/>tag=ok_to_publish"/]
    UPLOAD -->|gate_passed=false| WPREVIEW[/"WP post<br/>status=pending<br/>tag=needs-human-review<br/>+ review callout prepended"/]

    WPDRAFT --> HUMAN1{{Human reviews draft}}
    WPREVIEW --> HUMAN2{{Human addresses flags<br/>removes review tag<br/>adds ok_to_publish<br/>deletes callout}}

    HUMAN1 -->|publishes| WPPUB[/"WP post<br/>status=publish<br/>tag=ok_to_publish"/]
    HUMAN2 -->|publishes| WPPUB
    HUMAN2 -.->|skipped clean-up| WPACCIDENT[/"WP post<br/>status=publish<br/>STILL tag=needs-human-review"/]

    WPPUB --> PROMOTE([promote-to-branding<br/>timer or Telegram PROMOTE])
    WPACCIDENT --> PROMOTE

    PROMOTE --> REVERT[revert-loop<br/>any publish+review-tag<br/>→ status=pending]
    REVERT -.->|catches accident| WPREVIEW

    REVERT --> MIGRATE[for each post:<br/>tag=ok_to_publish<br/>status=publish]
    MIGRATE --> SKIP{{skip checks<br/>error tag?<br/>review tag?<br/>already in court_opinions?}}
    SKIP -->|skip| WPERR[/"WP post<br/>tag=publication_failed"/]
    SKIP -->|proceed| EXTRACT[migration agent<br/>extracts category, slug, citation]
    EXTRACT --> CO[("court_opinions<br/>needs_review=true<br/>seo_title carried over")]
    EXTRACT --> WPSUCCESS[/"WP post<br/>tag=published_to_landing_pages"/]
    EXTRACT --> GOOGLE[Trigger Google indexing]

    CO --> APPROVE([Operator: 'approve' command])
    APPROVE --> CO2[("court_opinions<br/>needs_review=false")]
    CO2 --> TXFAMLAW[/"Published to<br/>txfamlaw.com landing pages"/]
```

## Key states & guarantees

### `opinion_tracking.gate_passed`

- **`true`**  — gate ran and found no high-severity or policy-violation flags. Post goes to the normal draft track.
- **`false`** — gate flagged the draft OR the gate failed to run. Post goes to the pending-review track with a red callout block prepended to the body.
- **default** for new rows is `false`, so anything that bypasses the gate (e.g. partial pipeline run) routes to review by construction.

### WordPress post states

| State | Status | Tags | Meaning |
|---|---|---|---|
| Fresh draft, gate cleared | `draft` | `ok_to_publish` | Awaiting routine human review |
| Fresh draft, gate flagged | `pending` | `needs-human-review` | Awaiting human reconciliation against the gate's flags |
| Cleared & live | `publish` | `ok_to_publish` | Eligible for migration to `court_opinions` |
| Successfully migrated | `publish` | `published_to_landing_pages` | Already in `court_opinions`; will be skipped on next migrate pass |
| Migration error | (any) | `publication_failed` | Skip-check trips; surfaces to operator for investigation |
| Accidentally published while flagged | `publish` | `needs-human-review` | The revert-loop will yank back to `pending` on the next `process_workflow` call |

### Two human gates

1. **WordPress review** — the human reads the draft (and the gate callout if present), fixes anything, and publishes.
2. **`approve` command** — flips `court_opinions.needs_review` from `true` → `false`, exposing the post on txfamlaw.com landing pages.

### Backstop

The revert-loop runs at the **top** of every `process_workflow` invocation (timer-driven `promote-to-branding` and Telegram PROMOTE share this code path). Any post that is `status=publish` but still carries `needs-human-review` gets demoted back to `pending`. Protects against absent-minded publishes of a still-flagged draft.

## What's running where

| Component | Runs as | Triggers `process_workflow` |
|---|---|---|
| `scraper_job all` | systemd timer | Yes (terminal step) |
| `scraper_job promote-to-branding` | manual CLI | Yes |
| Telegram `promote` command | `opinion-blogger-webhook.service` (uvicorn) | Yes |

Note: the Telegram webhook is a separate long-lived process. After deploying changes to `post_migrator.py`, restart `opinion-blogger-webhook.service` so the new module gets loaded.
