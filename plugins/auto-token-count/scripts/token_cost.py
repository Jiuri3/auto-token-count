#!/usr/bin/env python3

import argparse
import json
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


MILLION = Decimal("1000000")  # 每百万 token 的计费基数
PLUGIN_ROOT = Path(__file__).resolve().parents[1]  # 插件根目录
DEFAULT_CONFIG_PATH = PLUGIN_ROOT / "config" / "default.json"  # 内置价格配置


# 保存一次模型请求的 token 用量。
@dataclass(frozen=True)
class Usage:
    input_tokens: int
    cached_input_tokens: int
    cache_write_input_tokens: int
    output_tokens: int
    reasoning_output_tokens: int

    # 返回本次请求用于展示的 token 总数。
    def total_tokens(self):
        return self.input_tokens + self.output_tokens


# 保存一次模型请求及其模型信息。
@dataclass(frozen=True)
class RequestUsage:
    model: str
    usage: Usage


# 保存一次请求的费用结果。
@dataclass(frozen=True)
class RequestCost:
    request: RequestUsage
    long_context: bool
    official_usd: Decimal
    billed_usd: Decimal
    target_currency: Decimal


# 保存一轮对话的汇总结果。
@dataclass(frozen=True)
class TurnCost:
    requests: tuple
    official_usd: Decimal
    billed_usd: Decimal
    target_currency: Decimal

    # 汇总本轮所有模型请求的 token。
    def total_tokens(self):
        return sum(item.request.usage.total_tokens() for item in self.requests)

    # 统计本轮触发长上下文价格的请求数。
    def long_context_requests(self):
        return sum(1 for item in self.requests if item.long_context)


# 返回插件的可写配置目录。
def get_data_dir():
    return Path.home() / ".codex" / "token-cost"


# 返回用户配置路径。
def get_user_config_path():
    configured_path = os.environ.get("CODEX_TOKEN_COST_CONFIG")
    if configured_path:
        return Path(configured_path)
    return get_data_dir() / "config.json"


# 读取 JSON 文件。
def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


# 初始化并读取用户配置。
def load_config(path=None):
    config_path = Path(path) if path else get_user_config_path()  # 实际使用的配置路径
    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    return read_json(config_path)


# 将 JSONL 会话日志解析为事件列表。
def read_events(transcript_path):
    events = []  # 有效的会话事件
    with Path(transcript_path).open(encoding="utf-8") as transcript:
        for line in transcript:
            stripped = line.strip()
            if stripped:
                events.append(json.loads(stripped))
    return events


# 从 token_count 事件中读取单次请求用量。
def usage_from_event(event):
    payload = event.get("payload", {})
    if event.get("type") != "event_msg" or payload.get("type") != "token_count":
        return None
    usage = payload.get("info", {}).get("last_token_usage")
    if not usage:
        return None
    return Usage(
        input_tokens=int(usage.get("input_tokens", 0)),
        cached_input_tokens=int(usage.get("cached_input_tokens", 0)),
        cache_write_input_tokens=int(usage.get("cache_write_input_tokens", 0)),
        output_tokens=int(usage.get("output_tokens", 0)),
        reasoning_output_tokens=int(usage.get("reasoning_output_tokens", 0)),
    )


# 按 turn_id 收集每轮中的模型请求。
def parse_turns(transcript_path, fallback_model=None):
    turns = {}  # turn_id 到请求列表的映射
    current_turn_id = None  # 当前正在解析的轮次
    current_model = fallback_model  # 当前轮次使用的模型
    for event in read_events(transcript_path):
        if event.get("type") == "turn_context":
            payload = event.get("payload", {})
            current_turn_id = payload.get("turn_id")
            current_model = payload.get("model") or fallback_model
            if current_turn_id:
                turns.setdefault(current_turn_id, [])
            continue
        usage = usage_from_event(event)
        if usage and current_turn_id:
            turns[current_turn_id].append(RequestUsage(current_model or "unknown", usage))
    return turns


# 按模型名称或别名查找价格配置。
def resolve_model_config(config, model):
    for configured_model, model_config in config["models"].items():
        aliases = model_config.get("aliases", [])  # 当前模型配置的别名
        if model == configured_model or model in aliases:
            return model_config
    raise ValueError(f"未配置模型价格：{model}")


# 计算一次模型请求的费用。
def calculate_request_cost(request, config):
    model_config = resolve_model_config(config, request.model)
    threshold = int(model_config["long_context_threshold"])  # 长上下文阈值
    long_context = request.usage.input_tokens > threshold
    price_key = "long_context" if long_context else "short_context"
    prices = model_config[price_key]  # 本次请求采用的价格表
    cached_tokens = request.usage.cached_input_tokens
    cache_write_tokens = request.usage.cache_write_input_tokens
    uncached_tokens = request.usage.input_tokens - cached_tokens - cache_write_tokens
    official_usd = (
        Decimal(uncached_tokens) * Decimal(prices["input"])
        + Decimal(cached_tokens) * Decimal(prices["cached_input"])
        + Decimal(cache_write_tokens) * Decimal(prices["cache_write_input"])
        + Decimal(request.usage.output_tokens) * Decimal(prices["output"])
    ) / MILLION
    multiplier = Decimal(config["billing_multiplier"])  # 渠道计费倍率
    exchange_rate = Decimal(config["currency"]["usd_exchange_rate"])  # 美元兑换目标币种汇率
    billed_usd = official_usd * multiplier
    return RequestCost(
        request=request,
        long_context=long_context,
        official_usd=official_usd,
        billed_usd=billed_usd,
        target_currency=billed_usd * exchange_rate,
    )


# 汇总一轮对话中的全部请求费用。
def calculate_turn_cost(requests, config):
    costs = tuple(calculate_request_cost(request, config) for request in requests)
    return TurnCost(
        requests=costs,
        official_usd=sum((item.official_usd for item in costs), Decimal("0")),
        billed_usd=sum((item.billed_usd for item in costs), Decimal("0")),
        target_currency=sum((item.target_currency for item in costs), Decimal("0")),
    )


# 计算指定会话轮次的费用。
def calculate_transcript_turn(transcript_path, turn_id, config, fallback_model=None):
    turns = parse_turns(transcript_path, fallback_model)
    requests = turns.get(turn_id, [])  # 目标轮次中的模型请求
    if not requests:
        raise ValueError(f"未找到轮次 token 数据：{turn_id}")
    return calculate_turn_cost(requests, config)


# 按配置精度格式化金额。
def format_decimal(value, decimal_places):
    quantum = Decimal("1").scaleb(-decimal_places)
    return format(value.quantize(quantum), "f")


# 生成每轮结束后显示的紧凑费用信息。
def format_turn_summary(turn_cost, config):
    decimal_places = int(config["display"]["decimal_places"])
    symbol = config["currency"]["symbol"]  # 目标币种符号
    target_value = format_decimal(turn_cost.target_currency, decimal_places)
    parts = [f"本轮 {turn_cost.total_tokens():,} token", f"{symbol}{target_value}"]
    if config["display"].get("show_billed_usd", True):
        billed_usd = format_decimal(turn_cost.billed_usd, decimal_places)
        parts.append(f"US${billed_usd}")
    long_count = turn_cost.long_context_requests()
    if long_count:
        parts.append(f"长上下文 {long_count} 次")
    return " · ".join(parts)


# 将一轮费用转换为可序列化字典。
def turn_cost_to_dict(turn_id, turn_cost, config):
    return {
        "turn_id": turn_id,
        "request_count": len(turn_cost.requests),
        "total_tokens": turn_cost.total_tokens(),
        "long_context_requests": turn_cost.long_context_requests(),
        "official_usd": str(turn_cost.official_usd),
        "billed_usd": str(turn_cost.billed_usd),
        "currency": config["currency"]["code"],
        "target_currency": str(turn_cost.target_currency),
    }


# 处理命令行参数并输出报告。
def main():
    parser = argparse.ArgumentParser(description="统计 Codex token 与折算费用")
    parser.add_argument("--config", help="自定义配置文件路径")
    subparsers = parser.add_subparsers(dest="command", required=True)

    turn_parser = subparsers.add_parser("turn", help="统计指定轮次")
    turn_parser.add_argument("--transcript", required=True)
    turn_parser.add_argument("--turn-id", required=True)
    turn_parser.add_argument("--model")

    session_parser = subparsers.add_parser("session", help="统计整个会话")
    session_parser.add_argument("--transcript", required=True)
    session_parser.add_argument("--model")

    subparsers.add_parser("config-path", help="显示用户配置路径")
    args = parser.parse_args()
    config = load_config(args.config)

    if args.command == "config-path":
        print(get_user_config_path())
        return

    turns = parse_turns(args.transcript, args.model)
    if args.command == "turn":
        turn_cost = calculate_turn_cost(turns.get(args.turn_id, []), config)
        print(json.dumps(turn_cost_to_dict(args.turn_id, turn_cost, config), ensure_ascii=False, indent=2))
        return

    report = []  # 整个会话的逐轮报告
    for turn_id, requests in turns.items():
        if requests:
            turn_cost = calculate_turn_cost(requests, config)
            report.append(turn_cost_to_dict(turn_id, turn_cost, config))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
