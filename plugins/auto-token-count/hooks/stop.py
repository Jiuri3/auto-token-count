#!/usr/bin/env python3

import json
import os
import sys
from pathlib import Path


PLUGIN_ROOT = Path(os.environ.get("PLUGIN_ROOT", Path(__file__).resolve().parents[1]))  # 插件根目录
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from token_cost import calculate_transcript_turn, format_turn_summary, load_config


# 输出不会触发模型续写的 Stop hook 结果。
def emit_message(message):
    result = {
        "continue": True,
        "systemMessage": message,
    }
    print(json.dumps(result))


# 读取当前轮次并输出自动费用信息。
def main():
    try:
        request = json.load(sys.stdin)  # Stop hook 输入
        transcript_path = request.get("transcript_path")
        turn_id = request.get("turn_id")
        model = request.get("model")
        if not transcript_path or not turn_id:
            raise ValueError("Stop hook 未提供会话日志或 turn_id")
        config = load_config()
        turn_cost = calculate_transcript_turn(transcript_path, turn_id, config, model)
        emit_message(format_turn_summary(turn_cost, config))
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        emit_message(f"本轮费用暂不可用：{error}")


if __name__ == "__main__":
    main()
