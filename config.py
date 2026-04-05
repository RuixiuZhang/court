"""
court.config — 全局配置：API 地址、模型实例、角色分配、上下文窗口限制。
"""

BASE_API_URL = "http://192.168.2.1:1234/api/v1/chat"

MODEL_INSTANCES = [
    "qwen/qwen3-4b-2507",
    "qwen3.5-27b-claude-4.6-opus-reasoning-distilled",
    "qwen/qwen3-4b-2507:2",
    "qwen/qwen3-4b-2507:3",
    "qwen/qwen3-4b-2507:4",
    "qwen/qwen3-4b-2507:5",
    "qwen/qwen3-4b-2507:6",
    "qwen/qwen3-4b-2507:7",
    "qwen/qwen3-4b-2507:8",
    "qwen/qwen3-4b-2507:9",
    "qwen/qwen3-4b-2507:10",
    "qwen/qwen3-4b-2507:11",
    "qwen/qwen3-4b-2507:12",
    "qwen/qwen3-4b-2507:13",
    "qwen/qwen3-4b-2507:14",
    "qwen/qwen3-4b-2507:15",
]

# ═══════════════════════════════════════════════════════════════════
# 角色分配 —— 严格美式法庭（1 组，16 个模型实例各司其职）
# ═══════════════════════════════════════════════════════════════════
ROLE_ASSIGNMENT = {
    "clerk":              MODEL_INSTANCES[0],      # 书记员：生成案件
    "judge":              MODEL_INSTANCES[1],      # 法官
    "plaintiff_attorney": MODEL_INSTANCES[2],      # 原告律师
    "defense_attorney":   MODEL_INSTANCES[3],      # 被告律师
    "plaintiff_witness_1": MODEL_INSTANCES[4],     # 原告证人 1
    "plaintiff_witness_2": MODEL_INSTANCES[5],     # 原告证人 2
    "defense_witness_1":  MODEL_INSTANCES[6],      # 被告证人 1
    "defense_witness_2":  MODEL_INSTANCES[7],      # 被告证人 2
    "jurors": MODEL_INSTANCES[8:16],               # 8 名陪审员
}

# ═══════════════════════════════════════════════════════════════════
# 法官上下文窗口管理参数
# ═══════════════════════════════════════════════════════════════════
MAX_CONTEXT_CHARS = 3200
RESPONSE_EXCERPT_CHARS = 320
MAX_CASE_BG_CHARS = 1200

# 法官最大回合数
MAX_JUDGE_TURNS = 100

# 哪些 target 的 token 计入原告方
PLAINTIFF_SIDE_TARGETS = {
    "plaintiff_attorney", "plaintiff_witness_1", "plaintiff_witness_2"
}
# 哪些 target 的 token 计入被告方
DEFENSE_SIDE_TARGETS = {
    "defense_attorney", "defense_witness_1", "defense_witness_2"
}
