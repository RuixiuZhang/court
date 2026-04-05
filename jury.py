"""
court.jury — 单个陪审员投票逻辑（供线程池并发调用）。
"""

import json

from .api import send_chat_request
from .prompts import JUROR_PERSONALITIES


def juror_vote(juror_model_id, juror_index, case_packet):
    """
    单个陪审员独立审议并投票。
    每个陪审员拥有独特的性格偏见，确保陪审团多样性。
    返回 (juror_index, vote, reasoning, token_count, stats)。
    """
    personality = JUROR_PERSONALITIES[juror_index % len(JUROR_PERSONALITIES)]
    sys_prompt = (
        f"You are Juror #{juror_index + 1} in a United States civil court. "
        f"{personality} "
        "You have listened to the full trial proceedings including opening statements, "
        "witness testimonies, cross-examinations, and closing arguments from both sides. "
        "Based on the evidence and arguments presented, filtered through YOUR personal "
        "perspective and values, you must render your independent verdict. "
        "You must output ONLY valid JSON in this exact format: "
        '{"vote": "plaintiff" or "defendant", "reasoning": "your brief reasoning"}. '
        "Do not output any markdown or extra text."
    )
    text, tokens, stats = send_chat_request(juror_model_id, sys_prompt, case_packet)

    vote = "plaintiff"
    reasoning = ""
    try:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.strip()
        parsed = json.loads(cleaned)
        vote = parsed.get("vote", "plaintiff")
        reasoning = parsed.get("reasoning", "")
    except (json.JSONDecodeError, AttributeError):
        reasoning = f"[JSON parse failed] {text[:200]}"

    return juror_index, vote, reasoning, tokens, stats
