# Auto Token Count

这是一个纯本地 Codex 插件，用于按每次模型请求统计 token，并按照预配置的官方价格、渠道倍率和美元汇率折算费用。

## 使用方法

把当前仓库地址给 Codex：

```text
https://github.com/Jiuri3/auto-token-count
```

然后输入：

```text
安装
```

也可以手动安装：

```bash
codex plugin marketplace add Jiuri3/auto-token-count
codex plugin add auto-token-count@auto-token-count
```

安装后新建一个 Codex 任务，并在首次提示时信任本地 `Stop` hook。

## 自动统计

插件通过 `Stop` hook 在每轮结束时读取当前会话 JSONL。hook 返回 `continue: true`，不会要求模型续写，也不会产生额外模型请求。

## 配置

首次运行会把 `config/default.json` 复制到 `~/.codex/token-cost/config.json`。自动 hook 与手动查询共用该文件。默认配置为：

- 渠道倍率：`0.12`
- 站内美元额度/人民币充值比例：`1:1`
- GPT-5.6 Sol、Terra、Luna 官方短上下文与长上下文价格
- 长上下文阈值：单次请求输入严格大于 `272000`

默认倍率和充值比例仅作为示例。请根据实际中转站修改 `~/.codex/token-cost/config.json`：

```text
实际费用 = 官方分类费用 x 渠道倍率 x 每 1 站内美元额度的人民币成本
```

插件只统计 token 费用，不包含网页搜索、Computer Use 等可能按次收取的工具费用。

配置路径可以通过以下命令查看：

```bash
python3 scripts/token_cost.py config-path
```

## 本地测试

测试只使用 `tests/fixtures/session.jsonl` 脱敏夹具，不发起网络请求或模型请求：

```bash
python3 -m unittest discover -s tests -v
```

## 运行环境

- Codex 插件功能
- Python 3
- 本地 Codex JSONL 会话日志
