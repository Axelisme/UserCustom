---
name: candidate-backlog
description: Capture evidence-backed discoveries that are valuable but outside the current task into a repo-local candidate backlog, without expanding scope or avoiding current-task obligations. Also use when planning work in an area (check its inbox first) or when the user asks what is worth doing next.
skill_version: 5
---

# Candidate Backlog

把「不影響當前 task 驗收、但有具體證據且值得未來處理」的發現寫入
`.agent_state/backlog/`。這是 local candidate inbox，不是已承諾 roadmap、issue tracker 或設計決策。

## Hard gates

- 當前 task 的 correctness、regression、review finding 或 acceptance gap 必須留在當前 task 處理。
- 需求不明、架構分叉或需要新授權時，停下詢問使用者；不可用 backlog 取代決策。
- 登記不授權 agent 擴張 scope，也不代表項目已排程。
- 只記錄有 `Observation`、`Evidence`、`Impact`、`Desired outcome` 的發現；不記個人偏好或無證據猜測。
- 不寫 credentials、硬體秘密、本機敏感設定、原始量測資料或大量 log。

## Capture workflow

1. 判斷發現不影響當前 task 驗收；若影響，回到 task finding。
2. 用 `list` 搜尋相同 title / area；`add` 也會 Fast Fail 並回報既有 ID。
3. 用 `scripts/backlog.py add` 建立一項一檔的 observation。
4. 在 task report / final 回報新建或補充的 backlog ID。
5. 不自行把項目升為 task；決定執行時才用 `bind` 綁定正式 task-id。

欄位與 taxonomy 見 [schema.md](references/schema.md)；狀態轉移與收尾條件見
[lifecycle.md](references/lifecycle.md)；人工撰寫時使用
[item-template.md](assets/item-template.md)。人工建立時必須把模板複製成與 metadata `id` 相同的
`<id>.md`，並同步替換 metadata 與 Markdown body；CLI 讀取時會驗證完整 metadata。

## CLI

文件中的 `<repo-python>` 代表 repo 文件記載的直譯器（例如 `.venv/bin/python`），`<skill-dir>` 是本
`SKILL.md` 所在目錄。資料存於主 checkout 的 `.agent_state/backlog/`（gitignored）。`--root` 可省略，
省略時 CLI 從 cwd 自動推導主 checkout（拒絕 linked worktree）；只有在需要覆寫時才顯式指定：

```text
<repo-python> <skill-dir>/scripts/backlog.py add --kind <kind> --area <area> --source-task <task-id> --title <title> --observation <text> --evidence <text> --impact <text> --desired-outcome <text>
<repo-python> <skill-dir>/scripts/backlog.py list [--status inbox|planned|resolved|closed] [--kind <kind>] [--area <area>] [--full]
<repo-python> <skill-dir>/scripts/backlog.py bind <id> --task-id <task-id>
<repo-python> <skill-dir>/scripts/backlog.py close <id> --resolution implemented --task-id <task-id> --commit <sha> --validation <text>
<repo-python> <skill-dir>/scripts/backlog.py close <id> --resolution duplicate --duplicate-of <canonical-id>
```

CLI 使用 UTC timestamp、UTF-8 與 atomic replace；輸出恆為單行 JSON envelope（成功與錯誤皆印到
stdout，`ok`/`operation`/`backlog_version` 固定欄位）。不要繞過 transition 或直接覆寫 metadata。

`list` 預設只回 `id`／`title`／`kind`／`area`／`status`／`priority_hint`，並標記 `detail: summary`。
四個散文欄位（`observation`／`evidence`／`impact`／`desired_outcome`）才是一筆 item 的全部重量，
而定位與查重都用不到它們——一次 24 筆的 inbox 全文是 33 KB，摘要是 6 KB。要全文用 `--full`，
或先用 `--area`／`--kind` 收斂再取；單筆內容也可直接讀 `.agent_state/backlog/<status>/<id>.md`。

## 消費時刻（防 inbox rot）

backlog 只有被讀才有價值。三個固定消費點：

- **規劃時**：task／slice 規劃碰到某個 area 前，先 `list --area <area> --status inbox`——
  與本次改動同路的順風單以極低成本併入 slice；不順路的不撿，不得藉此擴 scope。
- **用戶問「接下來做什麼」時**：`list --status inbox` 整理成按 area／kind 分組的候選清單供用戶
  裁決；agent 不自行排程。
- **task 收尾時**（雙向）：進水——檢查 findings、review report 與 workaround，跨 scope 且可重現
  的進 inbox；出水——同 area 的既有 inbox item 若已被本次改動解決或變得無效，即時 `close`
  （`implemented` 或 `obsolete`），不留腐爛項。

當前 task 的必要修正不得被「移到 backlog」後略過。真正生效的設計仍寫入 tracked `docs/adr/` 或
模組 `README.md`。

## Area 命名

`area` 用模組路徑或 repo glossary 的既有詞（例如 `gui/writeback`、`liveplot`），不發明新別名——
同一 area 的歷史 item 靠這個字串聚合，命名漂移會讓規劃時的 `list --area` 漏抓。
