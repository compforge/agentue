# AGENTS.md

## 项目定位与边界

AgentUE 提供可组合的 Agent UI 事件协议与 Runner 交付能力，不绑定 Agent 实现、模型供应商、
Web 框架或组件库。UI 协议表达可呈现的语义状态；Runner 提供实时交付与恢复机制，业务状态、
权限和执行策略由宿主拥有。

## 代码地图

```text
agentue/
├── VERSION                   # 仓库 / SDK 发布版本
├── spec/                     # UI 事件与 SSE 规范
├── schema/                   # 跨语言 JSON Schema
├── conformance/              # 各 SDK 共用的协议测试用例
├── sdks/python/              # Python UI 协议与 Runner
├── sdks/typescript/           # TypeScript UI 协议、reducer 和 SSE 编解码
├── sdks/go/                   # Go UI 协议与 Redis 交付组件
├── docs/                     # Runner 设计与运行约定
├── scripts/                  # 版本同步与只读检查
└── Makefile                  # 格式化、lint 和各语言测试入口
```

## 关键约定

1. 根目录 `VERSION` 是仓库 / SDK 发布版本的权威来源，采用 SemVer。
   任何代码改动必须在同一变更中 bump VERSION；同一 PR 无需按每次提交重复递增。
   纯文档改动可以不递增。
2. 只手动修改 VERSION，再执行 `make version`。根 `package.json`、
   `sdks/typescript/package.json` 和 `sdks/python/pyproject.toml` 的包版本是生成副本，
   禁止手工维护；该命令同时通过 `uv lock` 更新 Python 锁文件。
   `make lint` 先只读检查版本一致性，不一致时失败，不自动修复。
   `PROTOCOL_VERSION` / 模型的 `version` 表示协议兼容性，不随 SDK 发布机械递增。
3. 协议变更同步规范、Schema、Python/TypeScript/Go SDK 和共享 conformance 用例。
   `stream_id` 是可选逻辑流地址，不是连接或续接游标；单模型 reducer 不负责多路路由。
4. 复用仓库 `make fix`、`make lint`、`make test`，改动范围明确时可使用对应语言 target。
   对外事件和示例不得包含凭据、内部链接或其他敏感信息。

## References

- `spec/protocol.md` — UI 模型、事件、逻辑流寻址和恢复语义
- `spec/sse.md` — SSE 帧、传输游标和多路交付
- `conformance/README.md` — 跨语言契约测试
- `docs/runner.md` — Runner 执行与交付生命周期
- `sdks/python/README.md`、`sdks/typescript/README.md`、`sdks/go/README.md` — SDK 使用入口
