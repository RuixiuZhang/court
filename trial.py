"""
court.trial — 主审判流程：法官 Agent 自主驱动完整美式法庭。
"""

import json
import time
import concurrent.futures

from .config import (
    ROLE_ASSIGNMENT,
    PLAINTIFF_SIDE_TARGETS,
    DEFENSE_SIDE_TARGETS,
    RESPONSE_EXCERPT_CHARS,
    MAX_JUDGE_TURNS,
)
from .api import send_chat_request
from .prompts import PARTICIPANT_PROFILES, JUDGE_AGENT_SYSTEM_PROMPT
from .utils import parse_json_response, truncate_bg, trim_context
from .examination import examination_loop
from .jury import juror_vote


def run_trial():
    """
    法官作为自主 Agent 驱动整场美式法庭审判。
    法官通过发出 JSON skill 指令来传唤证人、要求律师发言、
    指示陪审团、最终宣判。全流程由法官模型动态决定。
    """
    print("\n" + "█" * 80)
    print("  UNITED STATES DISTRICT COURT — TRIAL PROCEEDINGS")
    print("  Mode: Judge-Agent Autonomous Control")
    print("█" * 80)

    trial_start = time.perf_counter()
    all_stats = []
    plaintiff_tokens = 0
    defense_tokens = 0
    transcript_log = []
    collected_arguments = {
        "plaintiff": [],
        "defense": [],
    }

    R = ROLE_ASSIGNMENT

    # ── 预审：书记员立案（不归法官管辖） ──
    print("\n═══ PRE-TRIAL: CASE FILING ═══")
    case_background, _, s = send_chat_request(
        R["clerk"],
        "You are a court clerk filing a civil case in a US District Court. "
        "Generate a HIGHLY CONTROVERSIAL case with a genuine MORAL DILEMMA where "
        "both sides have strong, legitimate arguments. The case should involve "
        "themes like: AI accountability vs. innovation, whistleblower retaliation "
        "vs. trade secrets, patient autonomy vs. corporate liability, algorithmic "
        "discrimination vs. business efficiency, or environmental harm vs. economic "
        "survival. The facts must be AMBIGUOUS — reasonable people should disagree "
        "on who is right. Include: the parties involved, key contested facts, "
        "specific legal claims, and the core ethical tension. "
        "Keep it under 150 words.",
        "Please file the case."
    )
    all_stats.append(s)
    transcript_log.append({"speaker": "Clerk", "content": case_background})
    print(f"  [Clerk] Case filed:\n{case_background}")

    # ── 构建法官的初始上下文 ──
    case_header = (
        f"=== CASE FILED ===\n{case_background}\n\n"
        "=== TRIAL BEGINS ===\n"
        "The courtroom is in session. All participants are present:\n"
        "  - Plaintiff's Attorney (plaintiff_attorney)\n"
        "  - Defense Attorney (defense_attorney)\n"
        "  - Plaintiff Witness #1 (plaintiff_witness_1)\n"
        "  - Plaintiff Witness #2 / Expert (plaintiff_witness_2)\n"
        "  - Defense Witness #1 (defense_witness_1)\n"
        "  - Defense Witness #2 / Expert (defense_witness_2)\n"
        "  - 8 Jurors (polled via poll_jury)"
    )
    context_entries = [
        "Your Honor, please begin the proceedings by issuing your first action."
    ]

    # ── 法官 Agent 主循环 ──
    jury_tally = {"plaintiff": 0, "defendant": 0}
    jury_votes = []
    final_verdict = None
    judicial_commentary = ""
    damages = ""
    _call_history = []  # 记录 (action_type, target) 用于反循环检测

    for turn in range(1, MAX_JUDGE_TURNS + 1):
        # ── 硬性强制结案：turn 80 直接由代码终止 ──
        if turn >= 80:
            print(f"\n  ⚠ Hard limit reached at turn {turn}. Forcing verdict.")
            final_verdict = "defendant"
            judicial_commentary = "Trial terminated by court system — procedural time limit exceeded."
            damages = "None"
            transcript_log.append({
                "speaker": "Judge",
                "content": f"VERDICT: DEFENDANT (forced). {judicial_commentary}"
            })
            break

        # ── 反循环 & 超时强制推进 ──
        if turn >= 60:
            context_entries.append(
                "[SYSTEM URGENT] Turn 60+ reached. You MUST issue render_verdict NOW."
            )
        elif turn >= 40:
            context_entries.append(
                "[SYSTEM WARNING] Turn 40+ reached. Begin wrapping up — "
                "proceed to jury instructions, poll_jury, or render_verdict."
            )

        # 检测连续重复
        if len(_call_history) >= 3:
            last3 = _call_history[-3:]
            if last3[0] == last3[1] == last3[2]:
                context_entries.append(
                    f"[SYSTEM ERROR] You have repeated the SAME action 3 times in a row: "
                    f"{last3[0]}. This is FORBIDDEN. You MUST issue a DIFFERENT action now. "
                    f"Advance the trial to the next state."
                )

        running_context = trim_context(case_header, context_entries)
        judge_output, _, j_stats = send_chat_request(
            R["judge"],
            JUDGE_AGENT_SYSTEM_PROMPT,
            running_context
        )
        all_stats.append(j_stats)

        try:
            action = parse_json_response(judge_output)
        except (json.JSONDecodeError, ValueError, TypeError, AttributeError):
            action = {"action": "judge_statement", "statement": judge_output}

        action_type = action.get("action", "unknown")
        _call_history.append((action_type, action.get("target", "")))
        print(f"\n  [Turn {turn}] Judge action: {action_type}")

        # ── 处理各类 action ──

        if action_type == "call_to_speak":
            _handle_call_to_speak(
                action, R, case_background, transcript_log,
                context_entries, all_stats, collected_arguments,
                plaintiff_tokens, defense_tokens,
            )
            # 更新 mutable 返回的 token 计数
            plaintiff_tokens = _handle_call_to_speak.plaintiff_tokens
            defense_tokens = _handle_call_to_speak.defense_tokens

        elif action_type == "judge_statement":
            statement = action.get("statement", "")
            transcript_log.append({"speaker": "Judge", "content": statement})
            stmt_excerpt = statement[:RESPONSE_EXCERPT_CHARS] + ("..." if len(statement) > RESPONSE_EXCERPT_CHARS else "")
            context_entries.append(f"[Judge speaks to the court]: {stmt_excerpt}")
            print(f"    [Judge]:\n{statement}")

        elif action_type == "poll_jury":
            jury_tally, jury_votes = _handle_poll_jury(
                R, transcript_log, context_entries, all_stats
            )

        elif action_type == "render_verdict":
            final_verdict = action.get("verdict", "plaintiff")
            judicial_commentary = action.get("judicial_commentary", "")
            damages = action.get("damages_or_relief", "")

            transcript_log.append({
                "speaker": "Judge",
                "content": f"VERDICT: {final_verdict.upper()}. {judicial_commentary} Relief: {damages}"
            })

            print(f"\n  {'█' * 60}")
            print(f"  VERDICT: {'PLAINTIFF' if final_verdict == 'plaintiff' else 'DEFENDANT'} PREVAILS")
            print(f"  Commentary: {judicial_commentary}")
            if damages:
                print(f"  Relief: {damages}")
            print(f"  {'█' * 60}")
            break

        elif action_type == "direct_examine":
            tok_delta = _handle_direct_examine(
                action, R, case_background, transcript_log,
                context_entries, all_stats, collected_arguments,
                plaintiff_tokens, defense_tokens,
            )
            plaintiff_tokens = tok_delta["plaintiff_tokens"]
            defense_tokens = tok_delta["defense_tokens"]

        elif action_type == "cross_examine":
            tok_delta = _handle_cross_examine(
                action, R, case_background, transcript_log,
                context_entries, all_stats, collected_arguments,
                plaintiff_tokens, defense_tokens,
            )
            plaintiff_tokens = tok_delta["plaintiff_tokens"]
            defense_tokens = tok_delta["defense_tokens"]

        else:
            feedback = (
                f"[SYSTEM] Unknown action '{action_type}'. "
                "Available actions: call_to_speak, judge_statement, poll_jury, "
                "direct_examine, cross_examine, render_verdict"
            )
            context_entries.append(feedback)
            print(f"    ⚠ Unknown action: {action_type}")

    else:
        print(f"\n  ⚠ Trial reached maximum {MAX_JUDGE_TURNS} turns without verdict.")
        final_verdict = "defendant"
        judicial_commentary = "Trial ended due to procedural time limit. Case dismissed."
        damages = "None"

    # ── 软惩罚与奖励计算 ──
    import math

    def _verbosity_penalty(tokens):
        return min(0.1 * math.log1p(tokens / 500), 0.5)

    p_raw = (1.0 if final_verdict == "plaintiff" else -1.0) - _verbosity_penalty(plaintiff_tokens)
    d_raw = (1.0 if final_verdict == "defendant" else -1.0) - _verbosity_penalty(defense_tokens)
    p_score = max(-1.0, min(1.0, p_raw))
    d_score = max(-1.0, min(1.0, d_raw))

    trial_end = time.perf_counter()
    trial_duration = trial_end - trial_start

    total_tps_trial = sum(st.get("tokens_per_second", 0.0) for st in all_stats)
    avg_tps_trial = total_tps_trial / len(all_stats) if all_stats else 0.0

    combined_stats = {
        "tokens_per_second": avg_tps_trial,
        "steps_tps": [st.get("tokens_per_second", 0.0) for st in all_stats],
    }

    plaintiff_full_arg = "\n".join(
        f"[{a['role']}] {a['content']}" for a in collected_arguments["plaintiff"]
    )
    defense_full_arg = "\n".join(
        f"[{a['role']}] {a['content']}" for a in collected_arguments["defense"]
    )

    return {
        "stats": combined_stats,
        "all_stats": all_stats,
        "transcript_log": transcript_log,
        "case_background": case_background,
        "collected_arguments": collected_arguments,
        "plaintiff_full_arg": plaintiff_full_arg,
        "defense_full_arg": defense_full_arg,
        "plaintiff_tokens": plaintiff_tokens,
        "defense_tokens": defense_tokens,
        "p_score": p_score,
        "d_score": d_score,
        "jury_tally": jury_tally,
        "jury_votes": [
            {"juror_index": idx, "vote": v, "reasoning": r}
            for idx, v, r, _, _ in jury_votes
        ],
        "final_verdict": final_verdict,
        "judicial_commentary": judicial_commentary,
        "damages": damages,
        "trial_duration": trial_duration,
        "avg_tps": avg_tps_trial,
    }


# ═══════════════════════════════════════════════════════════════════
# Action handlers（从主循环中拆出，保持可读性）
# ═══════════════════════════════════════════════════════════════════

def _handle_call_to_speak(
    action, R, case_background, transcript_log,
    context_entries, all_stats, collected_arguments,
    plaintiff_tokens, defense_tokens,
):
    target = action.get("target", "")
    instruction = action.get("instruction", "Speak.")

    _attorney_only = {"plaintiff_attorney", "defense_attorney"}
    if target not in _attorney_only:
        if target in PARTICIPANT_PROFILES:
            side = "plaintiff" if target.startswith("plaintiff_") else "defense"
            own_atty = f"{side}_attorney"
            feedback = (
                f'[SYSTEM] Cannot call_to_speak on witnesses. '
                f'Use "direct_examine" with attorney="{own_atty}" and '
                f'witness="{target}" to have the attorney question the witness.'
            )
        else:
            feedback = f"[SYSTEM] Invalid target '{target}'. Valid targets for call_to_speak: {sorted(_attorney_only)}"
        context_entries.append(feedback)
        transcript_log.append({"speaker": "System", "content": feedback})
        print(f"    ⚠ Redirected: {target} → use direct_examine/cross_examine")
        _handle_call_to_speak.plaintiff_tokens = plaintiff_tokens
        _handle_call_to_speak.defense_tokens = defense_tokens
        return

    model_id = R[target]
    sys_prompt = PARTICIPANT_PROFILES[target]

    participant_input = (
        f"Case background: {truncate_bg(case_background)}\n\n"
        f"The Judge instructs you: {instruction}\n\n"
        f"=== RECENT COURT PROCEEDINGS ===\n"
        + "\n".join(
            f"[{entry['speaker']}]: {entry['content'][:160]}"
            for entry in transcript_log[-5:]
        )
    )

    text, tok, p_stats = send_chat_request(model_id, sys_prompt, participant_input)
    all_stats.append(p_stats)

    if target in PLAINTIFF_SIDE_TARGETS:
        plaintiff_tokens += tok
        collected_arguments["plaintiff"].append(
            {"role": target, "content": text}
        )
    elif target in DEFENSE_SIDE_TARGETS:
        defense_tokens += tok
        collected_arguments["defense"].append(
            {"role": target, "content": text}
        )

    speaker_label = target.replace("_", " ").title()
    transcript_log.append({"speaker": speaker_label, "content": text})
    excerpt = text[:RESPONSE_EXCERPT_CHARS] + ("..." if len(text) > RESPONSE_EXCERPT_CHARS else "")
    feedback = f"[{speaker_label} responds] ({tok} tokens):\n{excerpt}"
    context_entries.append(feedback)
    print(f"    [{speaker_label}] spoke ({tok} tokens):\n{text}")

    _handle_call_to_speak.plaintiff_tokens = plaintiff_tokens
    _handle_call_to_speak.defense_tokens = defense_tokens


def _handle_poll_jury(R, transcript_log, context_entries, all_stats):
    print("\n  ═══ JURY DELIBERATION (8 jurors, 2 batches × 4) ═══")

    full_case_packet = "\n\n".join(
        f"[{entry['speaker']}]: {entry['content'][:400]}"
        for entry in transcript_log[-16:]
    )

    juror_models = R["jurors"]
    jury_votes = []
    batch_size = 4

    for batch_idx in range(0, len(juror_models), batch_size):
        batch = juror_models[batch_idx:batch_idx + batch_size]
        batch_num = batch_idx // batch_size + 1
        print(f"\n    ── Batch {batch_num}/2 (jurors {batch_idx+1}-{batch_idx+len(batch)}) ──")

        with concurrent.futures.ThreadPoolExecutor(max_workers=batch_size) as executor:
            futures = {
                executor.submit(
                    juror_vote, batch[j], batch_idx + j, full_case_packet
                ): j
                for j in range(len(batch))
            }
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                jury_votes.append(result)
                idx, vote, reasoning, tok, st = result
                all_stats.append(st)
                print(f"    [Juror #{idx + 1}] Vote: {vote} — {reasoning}")

    p_votes = sum(1 for _, v, _, _, _ in jury_votes if v == "plaintiff")
    d_votes = sum(1 for _, v, _, _, _ in jury_votes if v == "defendant")
    jury_tally = {"plaintiff": p_votes, "defendant": d_votes}

    print(f"    │  JURY TALLY: Plaintiff {p_votes} — {d_votes} Defendant  │")

    jury_result_text = (
        f"[JURY VERDICT RETURNED] Plaintiff: {p_votes} votes, "
        f"Defendant: {d_votes} votes. "
        f"Majority favors: {'plaintiff' if p_votes > d_votes else 'defendant'}."
    )
    transcript_log.append({"speaker": "Jury Foreperson", "content": jury_result_text})
    context_entries.append(f"{jury_result_text}\n\nPlease now render_verdict.")

    return jury_tally, jury_votes


def _handle_direct_examine(
    action, R, case_background, transcript_log,
    context_entries, all_stats, collected_arguments,
    plaintiff_tokens, defense_tokens,
):
    atty_target = action.get("attorney", "")
    wit_target = action.get("witness", "")

    valid_pairs = {
        ("plaintiff_attorney", "plaintiff_witness_1"),
        ("plaintiff_attorney", "plaintiff_witness_2"),
        ("defense_attorney", "defense_witness_1"),
        ("defense_attorney", "defense_witness_2"),
    }

    if (atty_target, wit_target) not in valid_pairs:
        feedback = (
            f"[SYSTEM] Invalid direct_examine params. "
            f"Attorney can only direct-examine their OWN witnesses. "
            f"Valid pairs: plaintiff_attorney→plaintiff_witness_*, "
            f"defense_attorney→defense_witness_*. "
            f"Got attorney='{atty_target}', witness='{wit_target}'."
        )
        context_entries.append(feedback)
        transcript_log.append({"speaker": "System", "content": feedback})
        print(f"    ⚠ Invalid direct_examine: {atty_target} → {wit_target}")
        return {"plaintiff_tokens": plaintiff_tokens, "defense_tokens": defense_tokens}

    atty_model = R[atty_target]
    wit_model = R[wit_target]
    atty_label = atty_target.replace("_", " ").title()
    wit_label = wit_target.replace("_", " ").title()

    print(f"\n  ═══ DIRECT EXAMINATION: {atty_label} ⟶ {wit_label} ═══")
    qa_pairs, de_tokens, de_stats = examination_loop(
        attorney_model_id=atty_model,
        witness_model_id=wit_model,
        attorney_label=atty_label,
        witness_label=wit_label,
        case_background=case_background,
        exam_type="direct",
        num_rounds=3,
    )
    all_stats.extend(de_stats)

    if atty_target in PLAINTIFF_SIDE_TARGETS:
        plaintiff_tokens += de_tokens
    else:
        defense_tokens += de_tokens

    de_summary_parts = []
    for i, pair in enumerate(qa_pairs, 1):
        de_summary_parts.append(f"Q{i} ({atty_label}): {pair['question']}")
        de_summary_parts.append(f"A{i} ({wit_label}): {pair['answer']}")
    de_summary = "\n".join(de_summary_parts)

    transcript_log.append({
        "speaker": "Direct Examination",
        "content": f"{atty_label} examines {wit_label}:\n{de_summary}"
    })

    for pair in qa_pairs:
        side = "plaintiff" if atty_target in PLAINTIFF_SIDE_TARGETS else "defense"
        collected_arguments[side].append(
            {"role": atty_target, "content": pair["question"]}
        )
        collected_arguments[side].append(
            {"role": wit_target, "content": pair["answer"]}
        )

    de_excerpt = de_summary[:RESPONSE_EXCERPT_CHARS] + ("..." if len(de_summary) > RESPONSE_EXCERPT_CHARS else "")
    feedback = (
        f"[Direct Examination Complete] {atty_label} ⟶ {wit_label} "
        f"(3 rounds, {de_tokens} tokens):\n{de_excerpt}"
    )
    context_entries.append(feedback)

    opposing_attorney = (
        "defense_attorney" if atty_target == "plaintiff_attorney" else "plaintiff_attorney"
    )
    procedural_hint = (
        f'[SYSTEM HINT] Direct examination of {wit_label} is complete. '
        f'You SHOULD now use the "cross_examine" action with '
        f'attorney="{opposing_attorney}" and witness="{wit_target}" '
        f'to let the opposing side challenge this testimony.'
    )
    context_entries.append(procedural_hint)

    return {"plaintiff_tokens": plaintiff_tokens, "defense_tokens": defense_tokens}


def _handle_cross_examine(
    action, R, case_background, transcript_log,
    context_entries, all_stats, collected_arguments,
    plaintiff_tokens, defense_tokens,
):
    atty_target = action.get("attorney", "")
    wit_target = action.get("witness", "")

    valid_attorneys = {"plaintiff_attorney", "defense_attorney"}
    valid_witnesses = {
        "plaintiff_witness_1", "plaintiff_witness_2",
        "defense_witness_1", "defense_witness_2",
    }

    if atty_target not in valid_attorneys or wit_target not in valid_witnesses:
        feedback = (
            f"[SYSTEM] Invalid cross_examine params. "
            f"attorney must be one of {sorted(valid_attorneys)}, "
            f"witness must be one of {sorted(valid_witnesses)}. "
            f"Got attorney='{atty_target}', witness='{wit_target}'."
        )
        context_entries.append(feedback)
        transcript_log.append({"speaker": "System", "content": feedback})
        print(f"    ⚠ Invalid cross_examine: {atty_target} vs {wit_target}")
        return {"plaintiff_tokens": plaintiff_tokens, "defense_tokens": defense_tokens}

    atty_model = R[atty_target]
    wit_model = R[wit_target]
    atty_label = atty_target.replace("_", " ").title()
    wit_label = wit_target.replace("_", " ").title()

    print(f"\n  ═══ CROSS-EXAMINATION: {atty_label} ⟶ {wit_label} ═══")
    qa_pairs, ce_tokens, ce_stats = examination_loop(
        attorney_model_id=atty_model,
        witness_model_id=wit_model,
        attorney_label=atty_label,
        witness_label=wit_label,
        case_background=case_background,
        exam_type="cross",
        num_rounds=3,
    )
    all_stats.extend(ce_stats)

    if atty_target in PLAINTIFF_SIDE_TARGETS:
        plaintiff_tokens += ce_tokens
    else:
        defense_tokens += ce_tokens

    ce_summary_parts = []
    for i, pair in enumerate(qa_pairs, 1):
        ce_summary_parts.append(f"Q{i} ({atty_label}): {pair['question']}")
        ce_summary_parts.append(f"A{i} ({wit_label}): {pair['answer']}")
    ce_summary = "\n".join(ce_summary_parts)

    transcript_log.append({
        "speaker": "Cross-Examination",
        "content": f"{atty_label} cross-examines {wit_label}:\n{ce_summary}"
    })

    for pair in qa_pairs:
        if atty_target in PLAINTIFF_SIDE_TARGETS:
            collected_arguments["plaintiff"].append(
                {"role": atty_target, "content": pair["question"]}
            )
        else:
            collected_arguments["defense"].append(
                {"role": atty_target, "content": pair["question"]}
            )
        if wit_target in PLAINTIFF_SIDE_TARGETS:
            collected_arguments["plaintiff"].append(
                {"role": wit_target, "content": pair["answer"]}
            )
        elif wit_target in DEFENSE_SIDE_TARGETS:
            collected_arguments["defense"].append(
                {"role": wit_target, "content": pair["answer"]}
            )

    ce_excerpt = ce_summary[:RESPONSE_EXCERPT_CHARS] + ("..." if len(ce_summary) > RESPONSE_EXCERPT_CHARS else "")
    feedback = (
        f"[Cross-Examination Complete] {atty_label} ⟶ {wit_label} "
        f"(3 rounds, {ce_tokens} tokens):\n{ce_excerpt}"
    )
    context_entries.append(feedback)

    return {"plaintiff_tokens": plaintiff_tokens, "defense_tokens": defense_tokens}
