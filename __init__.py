"""
court — 美式法庭多 Agent 审判模拟系统。

用法:
    python -m court          # 作为模块运行
    python court/main.py     # 直接运行入口脚本
"""

from .benchmark import start_benchmark
from .trial import run_trial

__all__ = ["start_benchmark", "run_trial"]
