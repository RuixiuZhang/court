"""
court.utils — JSON 解析、上下文裁剪、文本截断等辅助函数。
"""

import json
import re

from .config import MAX_CONTEXT_CHARS, MAX_CASE_BG_CHARS


# ═══════════════════════════════════════════════════════════════════
# JSON 解析辅助
# ═══════════════════════════════════════════════════════════════════
def parse_json_response(text):
    """尝试从模型输出中提取 JSON 对象，容错 markdown 代码块和 <think> 标签。"""
    if not isinstance(text, str):
        text = str(text)
    cleaned = text.strip()
    # 去掉 qwen3 <think>...</think> 思考块
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
    if cleaned.endswith("```"):
        cleaned = cleaned.rsplit("```", 1)[0]
    cleaned = cleaned.strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start:end + 1]
    parsed = json.loads(cleaned)
    # 处理 LM Studio 嵌套 {"type":"message","content":"..."} 包装
    if "action" not in parsed and "content" in parsed:
        inner = parsed["content"]
        if isinstance(inner, str):
            inner = inner.strip()
            if inner.startswith("{"):
                parsed = json.loads(inner)
    return parsed


# ═══════════════════════════════════════════════════════════════════
# 文本截断
# ═══════════════════════════════════════════════════════════════════
def truncate_bg(text, max_chars=MAX_CASE_BG_CHARS):
    """Truncate case background to stay within token budget."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + " [...]"


def hard_truncate(text, cut_patterns):
    """
    物理硬截断：在 text 中找到任何 cut_patterns 中的子串，
    取最早出现的那个位置并截断，只保留前面的有效内容。
    """
    earliest = len(text)
    for pat in cut_patterns:
        idx = text.find(pat)
        if idx != -1 and idx < earliest:
            earliest = idx
    truncated = text[:earliest].strip()
    if earliest < len(text):
        print(f"      ✂ Hard truncation activated at char {earliest} (pattern match)")
    return truncated


# ═══════════════════════════════════════════════════════════════════
# 法官上下文窗口管理
# ═══════════════════════════════════════════════════════════════════
def trim_context(case_header, entries):
    """
    保持 case_header 不变，从 entries（list[str]）尾部开始，
    尽量多保留最近条目，总字符数不超过 MAX_CONTEXT_CHARS。
    """
    budget = MAX_CONTEXT_CHARS - len(case_header)
    kept = []
    used = 0
    for entry in reversed(entries):
        if used + len(entry) + 2 > budget:
            break
        kept.append(entry)
        used += len(entry) + 2  # \n\n
    kept.reverse()
    if len(kept) < len(entries):
        kept.insert(0, f"[... earlier {len(entries) - len(kept)} exchanges omitted ...]")
    return case_header + "\n\n" + "\n\n".join(kept)
