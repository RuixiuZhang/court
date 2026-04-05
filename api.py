"""
court.api — HTTP 连接池与通用聊天请求函数。
"""

import requests
import requests.adapters

from .config import BASE_API_URL

# ═══════════════════════════════════════════════════════════════════
# HTTP 连接池优化 —— requests.Session + HTTPAdapter
# 16 并发匹配：pool_connections=16, pool_maxsize=16
# keep-alive 复用 TCP 连接，避免每次请求重新握手
# ═══════════════════════════════════════════════════════════════════
_session = requests.Session()
_adapter = requests.adapters.HTTPAdapter(
    pool_connections=16,
    pool_maxsize=16,
    max_retries=requests.adapters.Retry(
        total=2,
        backoff_factor=0.5,
        status_forcelist=[502, 503, 504],
    ),
)
_session.mount("http://", _adapter)
_session.mount("https://", _adapter)


def send_chat_request(model_id, sys_prompt, user_input):
    """
    复用 Session 连接池的 requests.post 逻辑，严格 LM Studio payload 格式。
    返回 (output_text, token_count, stats)；失败则抛异常。
    """
    payload = {
        "model": model_id,
        "system_prompt": sys_prompt,
        "input": user_input,
    }

    response = _session.post(BASE_API_URL, json=payload, timeout=300)

    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code}")

    res_json = response.json()
    raw_output = res_json.get("output", "")

    # ── 提取纯 message 文本（跳过 reasoning 内部推理） ──────────
    if isinstance(raw_output, list):
        msg_parts = [
            item.get("content", "")
            for item in raw_output
            if isinstance(item, dict) and item.get("type") == "message"
        ]
        if not msg_parts:
            msg_parts = [
                item.get("content", "") if isinstance(item, dict) else str(item)
                for item in raw_output
            ]
        output_text = "".join(msg_parts)
    elif isinstance(raw_output, dict):
        output_text = raw_output.get("content", str(raw_output))
    else:
        output_text = str(raw_output) if raw_output else ""

    # ── 提取 token 数量（兼容新旧字段名） ────────────────────
    stats = res_json.get("stats", {})
    token_count = (
        stats.get("total_output_tokens", 0)
        or stats.get("predicted_tokens_count", 0)
        or stats.get("completion_tokens", 0)
        or res_json.get("usage", {}).get("completion_tokens", 0)
        or 0
    )
    return output_text, token_count, stats
