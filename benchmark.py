"""
court.benchmark — 入口函数：启动审判、统计结果、输出 DPO 数据集。
"""

import json
import time

from .config import BASE_API_URL, MODEL_INSTANCES
from .trial import run_trial


def start_benchmark():
    print(f"目标: {BASE_API_URL}")
    print(f"模式: 法庭完整审判 (Judge + Jury + Attorneys + Witnesses)")
    print(f"优化: requests.Session 连接池 (pool=16, keep-alive)")
    print("-" * 80)

    start_wall_time = time.perf_counter()

    try:
        result = run_trial()
    except Exception as e:
        print(f"\n[FATAL] Trial failed: {e}")
        return

    end_wall_time = time.perf_counter()

    # --- 最终汇总统计 ---
    all_stats_list = result.get("all_stats", [])
    total_tps = sum(st.get("tokens_per_second", 0.0) for st in all_stats_list)
    avg_tps = total_tps / len(MODEL_INSTANCES) if MODEL_INSTANCES else 0
    total_duration = end_wall_time - start_wall_time

    # --- 审判结果统计 ---
    print(f"\n{'─' * 80}")
    print(f"  审判结果")
    print(f"  最终判决: {'原告胜诉 (PLAINTIFF)' if result['final_verdict'] == 'plaintiff' else '被告胜诉 (DEFENDANT)'}")
    print(f"  陪审团投票: 原告 {result['jury_tally']['plaintiff']} — 被告 {result['jury_tally']['defendant']}")
    print(f"  原告总 tokens: {result['plaintiff_tokens']}  得分: {result['p_score']:.4f}")
    print(f"  被告总 tokens: {result['defense_tokens']}  得分: {result['d_score']:.4f}")
    print(f"  审判耗时: {result['trial_duration']:.2f}s")
    print(f"{'─' * 80}")

    # --- DPO 数据收集 ---
    winner = result["final_verdict"]
    p_args = result["collected_arguments"]["plaintiff"]
    d_args = result["collected_arguments"]["defense"]

    if winner == "plaintiff":
        chosen_args = p_args
        rejected_args = d_args
        chosen_score = result["p_score"]
        rejected_score = result["d_score"]
    else:
        chosen_args = d_args
        rejected_args = p_args
        chosen_score = result["d_score"]
        rejected_score = result["p_score"]

    def _format_structured(args_list):
        """将收集的论点列表转为结构化格式：按角色分组。"""
        by_role = {}
        for a in args_list:
            role = a["role"]
            by_role.setdefault(role, []).append(a["content"])
        return [
            {"role": role, "statements": stmts}
            for role, stmts in by_role.items()
        ]

    dpo_record = {
        # ── 标准 DPO 三元组 ──
        "prompt": result["case_background"],
        "chosen": [
            {"role": a["role"], "content": a["content"]}
            for a in chosen_args
        ],
        "rejected": [
            {"role": a["role"], "content": a["content"]}
            for a in rejected_args
        ],
        # ── 分数 ──
        "chosen_score": round(chosen_score, 6),
        "rejected_score": round(rejected_score, 6),
        # ── 元数据 ──
        "metadata": {
            "verdict": winner,
            "jury_tally": result["jury_tally"],
            "jury_votes": result["jury_votes"],
            "judicial_commentary": result["judicial_commentary"],
            "damages_or_relief": result["damages"],
            "plaintiff_tokens": result["plaintiff_tokens"],
            "defense_tokens": result["defense_tokens"],
            "trial_duration": round(result["trial_duration"], 2),
            "avg_tps": round(result["avg_tps"], 2),
        },
        # ── 结构化论点（按角色分组，便于训练时灵活切片） ──
        "chosen_structured": _format_structured(chosen_args),
        "rejected_structured": _format_structured(rejected_args),
    }

    with open("dpo_dataset.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(dpo_record, ensure_ascii=False) + "\n")

    print(f"\n[DPO] 已追加 1 条完整审判记录到 dpo_dataset.jsonl")
