# Auto Token Count

Auto Token Count 是一个纯本地 Codex 插件。它会在每轮回复结束后读取本地会话日志，统计输入、缓存输入、缓存写入和输出 token，并按照可配置的官方价格、渠道倍率和充值比例估算费用。

## 使用方法

把当前仓库地址给 Codex：

```text
https://github.com/Jiuri3/auto-token-count
```

然后输入：

```text
安装
```

Codex 会从仓库中的 marketplace 安装 `auto-token-count`。安装完成后新建一个任务，并在首次提示时信任本地 `Stop` hook。

## 手动安装

```bash
codex plugin marketplace add Jiuri3/auto-token-count
codex plugin add auto-token-count@auto-token-count
```

## 配置

首次运行会生成：

```text
~/.codex/token-cost/config.json
```

默认配置使用：

- 渠道倍率：`0.12`
- 站内美元额度/人民币充值比例：`1:1`
- GPT-5.6 Sol、Terra、Luna 官方短上下文与长上下文价格
- 长上下文阈值：单次请求输入严格大于 `272000`

默认倍率和充值比例仅作为示例。请按照实际中转站修改：

```text
实际费用 = 官方分类费用 x 渠道倍率 x 每 1 站内美元额度的人民币成本
```

例如充值人民币 100 元到账 80 站内美元额度时，配置中的换算比例应为 `100 / 80 = 1.25`。

## 说明

- 插件只读取本地 JSONL 会话日志，不联网获取价格或汇率。
- `Stop` hook 不会要求模型续写，也不会产生额外模型请求。
- 推理 token 已包含在输出 token 中，不会重复计费。
- 插件只统计 token 费用，不包含网页搜索、Computer Use 等可能按次收取的工具费用。
- 显示金额是按照配置计算的估算值，不保证与中转站最终账单完全一致。

## 本地测试

测试只使用脱敏夹具，不读取真实会话、不发起网络请求或模型请求：

```bash
cd plugins/auto-token-count
python3 -m unittest discover -s tests -v
```

## 运行环境

- Codex 插件功能
- Python 3
- 本地 Codex JSONL 会话日志
