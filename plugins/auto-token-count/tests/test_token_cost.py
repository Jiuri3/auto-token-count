import json
import os
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]  # 测试中的插件根目录
FIXTURE_PATH = PLUGIN_ROOT / "tests" / "fixtures" / "session.jsonl"  # 脱敏会话夹具
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from token_cost import (
    RequestUsage,
    Usage,
    calculate_request_cost,
    calculate_transcript_turn,
    format_turn_summary,
    load_config,
    parse_turns,
)


# 验证 token 解析与费用公式。
class TokenCostTests(unittest.TestCase):
    # 每个测试使用独立配置副本。
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temp_dir.name) / "config.json"
        self.config = load_config(self.config_path)

    # 清理临时配置目录。
    def tearDown(self):
        self.temp_dir.cleanup()

    # 创建指定输入量的 Sol 请求。
    def make_sol_request(self, input_tokens, cached=0, cache_write=0, output=0, reasoning=0):
        return RequestUsage(
            "gpt-5.6-sol",
            Usage(input_tokens, cached, cache_write, output, reasoning),
        )

    # 验证普通输入、缓存、缓存写入和输出分别计费。
    def test_short_context_components(self):
        request = self.make_sol_request(100000, 20000, 10000, 1000, 200)
        cost = calculate_request_cost(request, self.config)
        self.assertFalse(cost.long_context)
        self.assertEqual(cost.official_usd, Decimal("0.4525"))
        self.assertEqual(cost.billed_usd, Decimal("0.054300"))
        self.assertEqual(cost.target_currency, Decimal("0.054300"))

    # 验证 272000 不触发长上下文，而 272001 会触发。
    def test_long_context_boundary(self):
        short_cost = calculate_request_cost(self.make_sol_request(272000), self.config)
        long_cost = calculate_request_cost(self.make_sol_request(272001), self.config)
        self.assertFalse(short_cost.long_context)
        self.assertTrue(long_cost.long_context)
        self.assertEqual(short_cost.official_usd, Decimal("1.36000"))
        self.assertEqual(long_cost.official_usd, Decimal("2.72001"))

    # 验证推理 token 已包含在输出中，不会重复收费。
    def test_reasoning_tokens_are_not_double_charged(self):
        without_reasoning = calculate_request_cost(self.make_sol_request(0, output=1000), self.config)
        with_reasoning = calculate_request_cost(
            self.make_sol_request(0, output=1000, reasoning=900),
            self.config,
        )
        self.assertEqual(without_reasoning.official_usd, with_reasoning.official_usd)

    # 验证脱敏日志能按 turn_id 归组多次请求。
    def test_parse_turns_and_legacy_cache_write(self):
        turns = parse_turns(FIXTURE_PATH)
        self.assertEqual(len(turns["turn-short-long"]), 2)
        self.assertEqual(len(turns["turn-legacy"]), 1)
        self.assertEqual(turns["turn-legacy"][0].usage.cache_write_input_tokens, 0)

    # 验证一轮中的普通和长上下文请求会分别计算后汇总。
    def test_transcript_turn_total(self):
        turn_cost = calculate_transcript_turn(
            FIXTURE_PATH,
            "turn-short-long",
            self.config,
        )
        self.assertEqual(len(turn_cost.requests), 2)
        self.assertEqual(turn_cost.long_context_requests(), 1)
        self.assertEqual(turn_cost.total_tokens(), 375001)
        self.assertEqual(turn_cost.official_usd, Decimal("2.614501"))

    # 验证倍率与汇率直接影响最终目标币种金额。
    def test_custom_multiplier_and_exchange_rate(self):
        self.config["billing_multiplier"] = "0.5"
        self.config["currency"]["usd_exchange_rate"] = "8"
        cost = calculate_request_cost(self.make_sol_request(100000), self.config)
        self.assertEqual(cost.official_usd, Decimal("0.50000"))
        self.assertEqual(cost.billed_usd, Decimal("0.250000"))
        self.assertEqual(cost.target_currency, Decimal("2.000000"))

    # 验证紧凑显示包含 token、人民币、美元和长上下文提示。
    def test_summary_format(self):
        turn_cost = calculate_transcript_turn(
            FIXTURE_PATH,
            "turn-short-long",
            self.config,
        )
        summary = format_turn_summary(turn_cost, self.config)
        self.assertIn("375,001 token", summary)
        self.assertIn("￥", summary)
        self.assertIn("US$", summary)
        self.assertIn("长上下文 1 次", summary)

    # 验证 Stop hook 只读取夹具并返回 continue=true。
    def test_stop_hook_without_model_request(self):
        hook_input = {
            "session_id": "session-test",
            "turn_id": "turn-short-long",
            "transcript_path": str(FIXTURE_PATH),
            "cwd": "/tmp/project",
            "hook_event_name": "Stop",
            "model": "gpt-5.6-sol",
            "permission_mode": "never",
            "stop_hook_active": False,
            "last_assistant_message": "已完成",
        }
        environment = os.environ.copy()
        environment["PLUGIN_ROOT"] = str(PLUGIN_ROOT)
        environment["CODEX_TOKEN_COST_CONFIG"] = str(self.config_path)
        completed = subprocess.run(
            [sys.executable, str(PLUGIN_ROOT / "hooks" / "stop.py")],
            input=json.dumps(hook_input),
            text=True,
            capture_output=True,
            check=True,
            env=environment,
        )
        output = json.loads(completed.stdout)
        self.assertTrue(output["continue"])
        self.assertIn("systemMessage", output)
        self.assertNotIn("decision", output)


if __name__ == "__main__":
    unittest.main()
