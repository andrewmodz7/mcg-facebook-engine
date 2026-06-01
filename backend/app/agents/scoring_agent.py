"""AI scoring agent for filtered Facebook posts.

Uses Claude Opus 4.7 to reason about each post and decide whether it
represents a path — direct or indirect — to a hard money loan for Marcus.
If yes, ranks the post by urgency (who should Marcus message first).

Architecture: one API call per post. Combined triage + ranking. Returns
structured JSON. Posts with is_lead=true become Lead rows; posts with
is_lead=false stay in raw_posts with score_status='scored_not_a_lead'
and the agent's reasoning preserved for audit.
"""

import json
import logging
import os
from typing import Optional

from anthropic import AsyncAnthropic
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from app.db import async_session
from app.models import Lead, RawPost, TargetGroup

logger = logging.getLogger(__name__)

MODEL = "claude-opus-4-7"
MAX_TOKENS = 1500

SYSTEM_PROMPT = """You are an analyst working for Marcus Carter, a 20-year Chicago hard money real estate lender.

Your job: read Facebook group posts and decide whether each post represents a real path — direct OR indirect — to Marcus eventually funding a hard money loan. Then for the ones that do, rank them by who Marcus should reach out to first.

## What Marcus does

Marcus brokers hard money loans to real estate investors in the Chicago area. Average funded deal nets him $7,500-$10,000 (2-3 points on $250K-$350K loans). His ideal borrower is doing fix-and-flips, wholesales, BRRRR, or buy-and-hold investing — has an actual deal in progress or imminent — and needs short-term capital to close. He works the Chicago, Cook County, IL/IN/WI region.

His edge: he's not transactional. He builds relationships. He'll meet for coffee, show up at someone's job site, refer business he can't help with. The system you're feeding into is about identifying people worth starting a relationship with — not just people explicitly asking for money right now.

## What you're looking for

Posts that represent a path to a loan. This includes the obvious:
- Investors explicitly asking for funding for a deal
- Investors describing a deal they're working on
- Investors looking for capital partners or private money

AND the non-obvious — which is most of the real value:
- Contractors mentioning they're working on a flip (the flipper is the borrower)
- Wholesalers marketing deals (the cash buyer is the borrower)
- Realtors discussing investor clients (the investor is the borrower)
- Anyone whose post reveals they're around investors and could refer Marcus into their network
- Active flippers posting about their current projects (relationship play — they'll need capital again)

## What you're cutting (is_lead: false)

- Vendors selling to investors (CRM tools, marketing services, painters, movers, junk haulers, photographers, lawyers, accountants) UNLESS they reveal investor relationships worth pursuing
- Pure self-promotion (realtors hunting buyers, generic educational content)
- Wholesalers marketing TO cash buyers when there's no clear path to the buyer's identity
- General industry chatter with no specific person to engage
- Spam, foreign-language posts you can't reason about, posts that are mostly hashtags/links
- Anything where the conversation would be a waste of Marcus's time

## Important strategic context

Posts that say "looking for funding" are often LOW quality — they attract every lender/broker in the comments and the poster is usually an unserious investor. A contractor casually mentioning they're "doing a flip in Englewood next month" is often a HIGHER quality lead because Marcus can be the first call.

Think like a 20-year operator. Would this conversation, if Marcus opened it well, plausibly lead to a relationship that leads to a funded deal? If yes, is_lead is true.

## Output format

Respond with ONLY a JSON object. No preamble, no explanation outside the JSON. Schema:

```json
{
  "is_lead": true | false,
  "urgency_score": 1-10 integer (REQUIRED if is_lead=true, omit if false),
  "lead_type": "fix_and_flip" | "wholesale" | "buy_and_hold" | "other" | null (only if is_lead=true; null if classification doesn't cleanly apply),
  "angle": "string — IF is_lead=true: the strategic reasoning for HOW Marcus could open this conversation. What's the path from this post to a funded deal? Be specific. 2-4 sentences.",
  "reasoning": "string — your reasoning for the decision. 2-4 sentences. For is_lead=false, explain why this is a wasted conversation."
}
```

## Urgency score rubric (1-10) — USE THE FULL SCALE

Score reflects who Marcus should reach out to FIRST, second, third — not absolute urgency. Use the full range. If every post you score gets 5-6, you're not ranking effectively.

- 9-10: Strongest opportunity in a typical batch. Active operator with revealed deal pipeline OR a wholesaler/agent/contractor with clearly visible volume. Specific deals named, specific numbers, recent activity. Marcus should reach out today.

- 7-8: Strong relationship play. Active in the market with specific evidence (recent deal, specific numbers, named property, named operator). Reach out this week.

- 5-6: Worthwhile relationship play but signal is softer — generic post, vague claims, or single-deal visibility without ongoing evidence. Reach out when higher-priority leads are worked.

- 3-4: Plausible but weak. Adjacent person with possible-but-unconfirmed investor access. Engage only if queue is light.

- 1-2: Technically passes triage but very thin signal. Don't reach out unless desperate for volume.

Calibration check: in a batch of 10 leads, you should produce a spread that looks roughly like 2-3 in the 7-9 range, 4-5 in the 5-6 range, 2-3 in the 3-4 range. If they all cluster at 5-6, you're not ranking — re-evaluate and commit to differentiated scores.
"""

USER_PROMPT_TEMPLATE = """Analyze this Facebook post:

Group: {group_name}
Author: {author_name}
Posted: {posted_at}
Reactions: {reactions_count} | Comments: {comments_count}
Post text:
{post_text}

Return the JSON object only."""


async def score_post(
    post_text: str,
    author_name: Optional[str],
    group_name: Optional[str],
    posted_at: Optional[str],
    reactions_count: int,
    comments_count: int,
    client: AsyncAnthropic,
) -> dict:
    """Call Claude Opus 4.7 to score a single post.

    Returns the parsed JSON dict. Raises on API error or JSON parse failure.
    """
    user_prompt = USER_PROMPT_TEMPLATE.format(
        group_name=group_name or "<unknown>",
        author_name=author_name or "<unknown>",
        posted_at=posted_at or "<unknown>",
        reactions_count=reactions_count,
        comments_count=comments_count,
        post_text=post_text,
    )

    response = await client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw_text = response.content[0].text.strip()

    # Strip markdown code fences if Opus wraps the JSON.
    if raw_text.startswith("```"):
        lines = raw_text.split("\n")
        raw_text = "\n".join(
            lines[1:-1] if lines[-1].startswith("```") else lines[1:]
        )

    return json.loads(raw_text)


async def score_pending_posts(batch_size: int = 50) -> dict:
    """Score all raw_posts where filter_status='passed' AND score_status IS NULL.

    Sequential (not parallel) for v1 — keeps cost visible per post and
    makes failure isolation clean. Parallelize later if needed.

    Returns summary: {
        "total_evaluated": int,
        "is_lead": int,
        "not_a_lead": int,
        "errors": int,
    }
    """
    api_key = os.environ["ANTHROPIC_API_KEY"]
    client = AsyncAnthropic(api_key=api_key)

    summary = {"total_evaluated": 0, "is_lead": 0, "not_a_lead": 0, "errors": 0}

    while True:
        # Fetch a batch of posts ready for scoring, plus their group names.
        async with async_session() as session:
            stmt = (
                select(RawPost)
                .where(RawPost.filter_status == "passed")
                .where(RawPost.score_status.is_(None))
                .order_by(RawPost.scraped_at.asc())
                .limit(batch_size)
            )
            result = await session.execute(stmt)
            posts = result.scalars().all()

            if not posts:
                break

            # Pre-fetch the group names in one query.
            group_ids = list({p.group_id for p in posts})
            group_result = await session.execute(
                select(TargetGroup.id, TargetGroup.name).where(
                    TargetGroup.id.in_(group_ids)
                )
            )
            group_names = {row.id: row.name for row in group_result}

        # Score each post (own session per post for clean transaction isolation).
        for post in posts:
            summary["total_evaluated"] += 1
            try:
                result_dict = await score_post(
                    post_text=post.post_text,
                    author_name=post.author_name,
                    group_name=group_names.get(post.group_id),
                    posted_at=post.posted_at.isoformat()
                    if post.posted_at
                    else None,
                    reactions_count=post.reactions_count or 0,
                    comments_count=post.comments_count or 0,
                    client=client,
                )
            except Exception as exc:  # noqa: BLE001 — isolate one post's failure
                logger.exception("Scoring failed for post %s", post.id)
                async with async_session() as session:
                    await session.execute(
                        update(RawPost),
                        [
                            {
                                "id": post.id,
                                "score_status": "score_error",
                                "score_reasoning": f"Agent error: {str(exc)[:500]}",
                            }
                        ],
                    )
                    await session.commit()
                summary["errors"] += 1
                continue

            is_lead = bool(result_dict.get("is_lead"))
            reasoning = result_dict.get("reasoning", "")

            async with async_session() as session:
                if is_lead:
                    # Insert the Lead row.
                    lead_values = {
                        "raw_post_id": post.id,
                        "urgency_score": int(result_dict.get("urgency_score", 5)),
                        "lead_type": result_dict.get("lead_type") or "other",
                        # v1 placeholder — Marcus decides the actual action.
                        "recommended_action": "comment",
                        "angle": result_dict.get("angle", ""),
                        "reasoning": reasoning,
                        "stage": "new",
                    }
                    stmt = (
                        insert(Lead)
                        .values(**lead_values)
                        .on_conflict_do_nothing(index_elements=["raw_post_id"])
                    )
                    await session.execute(stmt)

                    # Mark the raw_post as scored.
                    await session.execute(
                        update(RawPost),
                        [
                            {
                                "id": post.id,
                                "score_status": "scored_is_lead",
                                "score_reasoning": reasoning,
                            }
                        ],
                    )
                    summary["is_lead"] += 1
                else:
                    await session.execute(
                        update(RawPost),
                        [
                            {
                                "id": post.id,
                                "score_status": "scored_not_a_lead",
                                "score_reasoning": reasoning,
                            }
                        ],
                    )
                    summary["not_a_lead"] += 1

                await session.commit()

        if len(posts) < batch_size:
            break

    return summary
