---
name: token-cost
description: 读取本地 Codex 会话日志，查看当前轮次、指定会话或历史会话的 token 与折算费用，并协助配置模型价格、渠道倍率和美元汇率。
---

# Auto Token Count

仅使用本地 JSONL 会话日志和插件配置计算费用，不调用模型 API，也不联网获取价格或汇率。

## 使用方式

- 用户询问当前配置路径时，运行 `python3 ${PLUGIN_ROOT}/scripts/token_cost.py config-path`。
- 用户要求统计指定轮次时，运行 `python3 ${PLUGIN_ROOT}/scripts/token_cost.py turn --transcript <日志路径> --turn-id <turn_id> --model <模型>`。
- 用户要求统计完整会话时，运行 `python3 ${PLUGIN_ROOT}/scripts/token_cost.py session --transcript <日志路径> --model <模型>`。
- 用户要求修改价格、倍率或汇率时，先取得配置路径，再直接编辑该 JSON 配置。

用户配置固定保存为 `~/.codex/token-cost/config.json`，自动 hook 和手动查询共用该文件。

## 计费规则

- 逐个 `last_token_usage` 计算，再按 `turn_id` 汇总。
- `input_tokens` 包含缓存 token；未缓存输入为输入减去缓存输入与缓存写入。
- `reasoning_output_tokens` 是 `output_tokens` 的子集，只展示，不重复计费。
- 单次请求输入严格大于模型的 `long_context_threshold` 时，该请求全部 token 使用长上下文价格。
- 配置中的价格单位均为每百万 token 的美元价格。
- 最终金额依次应用官方价格、`billing_multiplier` 和 `usd_exchange_rate`。
