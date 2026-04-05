"""
court.examination — 盘问微循环（direct / cross），严格 Ping-Pong 同步阻塞。
"""

from .api import send_chat_request
from .prompts import EXAM_PROMPTS
from .utils import truncate_bg, hard_truncate

# 角色劫持检测模式
ATTORNEY_HIJACK_PATTERNS = ["\nA:", "\nAnswer:", "\n["]
WITNESS_HIJACK_PATTERNS  = ["\nQ:", "\nQuestion:", "\n["]


def examination_loop(
    attorney_model_id,
    witness_model_id,
    attorney_label,
    witness_label,
    case_background,
    exam_type="cross",
    num_rounds=3,
):
    """
    统一的盘问「乒乓球」同步阻塞循环。
    exam_type="cross" → 交叉盘问（对抗质疑）
    exam_type="direct" → 直接主问（友好引导）

    共 num_rounds 轮：Q1->A1->Q2->A2->Q3->A3。

    双重防角色劫持：
      1) Prompt 层 —— System Prompt 中植入绝对禁令
      2) Python 层 —— 硬截断防角色劫持

    返回:
        qa_pairs: list[dict]  — [{"question": ..., "answer": ...}, ...]
        total_tokens: int
        all_stats: list[dict]
    """
    tmpl = EXAM_PROMPTS[exam_type]
    qa_pairs = []
    qa_lines = []
    total_tokens = 0
    all_stats = []

    print(f"\n    ┌─── {tmpl['label']}: {attorney_label} ⟶ {witness_label} ({num_rounds} rounds) ───┐")

    for r in range(1, num_rounds + 1):
        # ════════════════════════════════════════════
        # ① 律师提问
        # ════════════════════════════════════════════
        attorney_sys = tmpl["attorney_sys"].format(
            attorney_label=attorney_label, witness_label=witness_label
        )
        history_block = "\n".join(qa_lines) if qa_lines else "(No prior questions yet.)"
        attorney_input = (
            f"Case background: {truncate_bg(case_background)}\n\n"
            f"=== {tmpl['history_header']} ===\n{history_block}\n\n"
            f"Now ask your Round {r} question to {witness_label}."
        )

        print(f"      [Round {r}/{num_rounds}] {attorney_label} asks...")
        q_raw, q_tok, q_stats = send_chat_request(
            attorney_model_id, attorney_sys, attorney_input
        )
        all_stats.append(q_stats)
        total_tokens += q_tok

        # Python 硬截断：去除律师自行生成的回答
        q_text = hard_truncate(q_raw, ATTORNEY_HIJACK_PATTERNS)
        last_q = q_text.rfind("?")
        if last_q != -1 and last_q < len(q_text) - 1:
            q_text = q_text[:last_q + 1].strip()
            print(f"      ✂ Trimmed trailing content after final '?'")
        if not q_text:
            q_text = tmpl["fallback_q"]
            print(f"      ⚠ Empty question — injected fallback question")

        print(f"        Q{r}: {q_text}")

        # ════════════════════════════════════════════
        # ② 证人回答
        # ════════════════════════════════════════════
        witness_sys = tmpl["witness_sys"].format(
            witness_label=witness_label, q_text=q_text
        )
        witness_input = (
            f"Case background: {truncate_bg(case_background)}\n\n"
            f"{tmpl['witness_input_prefix']}: {q_text}\n\n"
            f"Answer the question now."
        )

        print(f"      [Round {r}/{num_rounds}] {witness_label} answers...")
        a_raw, a_tok, a_stats = send_chat_request(
            witness_model_id, witness_sys, witness_input
        )
        all_stats.append(a_stats)
        total_tokens += a_tok

        # Python 硬截断：去除证人自行生成的提问
        a_text = hard_truncate(a_raw, WITNESS_HIJACK_PATTERNS)
        if not a_text:
            a_text = tmpl["fallback_a"]
            print(f"      ⚠ Empty answer — injected fallback answer")

        print(f"        A{r}: {a_text}")

        qa_pairs.append({"question": q_text, "answer": a_text})
        qa_lines.append(f"Q{r}: {q_text}")
        qa_lines.append(f"A{r}: {a_text}")

    print(f"    └─── {tmpl['label']} complete ({num_rounds} rounds, {total_tokens} tokens) ───┘")

    return qa_pairs, total_tokens, all_stats
