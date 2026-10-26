---
name: engineering-habits
description: 用户的通用工程与操作偏好：改动前查读取方、先读源码、竞态查架构、测试不靠计时、用户文档写会发生什么、bug 当场修、装工具、配额重试、委派给 pi
metadata:
  type: feedback
---

用户在 2026-09 至 2026-10 多次纠正后的偏好，2026-10-26 合并。

**工程习惯。**
- 改一个通道（消息、字段、argv、文件格式）之前，grep 整个 repo 列出所有读取方。大量测试同因失败是生产代码的线索，不是测试噪音。
- 行为不一致时，先读依赖源码推出原因，再考虑设计观测手段。
- 竞态是架构不良的症状。同一 owner 第二次出现竞态类问题时，停止打补丁，做根因诊断，带至多两个架构选项给用户。
- 测试不靠计时（`Event.wait(1)`、sleep 后断言），用确定性同步；只有围绕设计保证会发生的事件、余量几十秒的防挂死 timeout 可以。
- 给用户看的文档写会发生什么、留下什么状态，不写「不会 X」。
- 中途发现的 bug 和小错误马上安排修正；backlog 只放需要设计决策或大工程的事项。

**操作与资源。**
- 缺开发工具（py-spy、perf 等）就用户级安装（如 `uv tool install`），不手写替代品；repo 依赖不动。
- 配额快用完不暂停工作：用完有 credit 接手；遇到 quota 或 provider 错误，过一阵再重试。
- 不用 Agent 工具开 Claude subagent，它会很快吃满 weekly limit；调查、prototype、实现都用 `mcp__subagents__spawn_subagent` 交给 pi。除了主 session，同时最多再开一个 Claude session。
