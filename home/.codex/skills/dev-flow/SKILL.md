---
name: dev-flow
description: Orient in the development-skill pipeline — which skill to use at which stage, from a vague idea through spec, tickets, orchestrated implementation, review, and landing. Use when the user asks "which skill/flow should I use next", wants the full workflow map, or starts a large effort and needs a route through the skills.
---

# Dev Flow

這是各 development skill 的路線圖：告訴你「現在處於哪個階段、下一步用哪個 skill」。
本 skill 只導航，不執行。核心要求：不只指出下一步，還要讓「為何走這條路、採用哪種
執行形狀、為何有或沒有 implementer/reviewer」變成可見且可檢查的決策——用 Route Card 回報。

## 快速退出

小任務不走 pipeline：單檔小修、問答、單回合 review 直接做。Route Card 縮成一行
（`quick exit ＋一句理由`）。這條 pipeline 只給「需要先想清楚才能動手」的中大型工作。

## Command-only vs model-invocable

兩類 downstream skill 的交接方式不同：

- **model-invocable**（grilling、research、prototype、domain-modeling、codebase-design、
  tdd、diagnosing-bugs、code-review、simplify、candidate-backlog、orchestrate）：判斷完
  階段後直接 invoke 接續。
- **command-only**（`/wayfinder`、`/to-spec`、`/to-tickets`、`/grill-with-docs`、
  `/improve-codebase-architecture`；設 `disable-model-invocation: true`）：回報建議指令
  與進入理由，停在合理交接點，由使用者明確呼叫。不要嘗試自動 invoke，也不要把
  available-skills 清單缺席解讀成缺件——command-only skill 不出現在 catalog 是預期行為。

## Route Card

每次使用 dev-flow，固定回報這張卡（quick exit 可縮成一行）：

```text
Current stage:        目前階段
Recommended next step: 下一個 skill／command（command-only 則請使用者輸入該指令）
Why:                  為什麼走這條路
Exit condition:       何時算完成這一階段
Expected artifact:    會產生什麼
Implementation shape: root-only / single-writer / normal wave / critical checkpoint（進入實作才填）
Review policy:        named risk、reviewer identity、是否形成 barrier（無 named risk 明寫 none）
Fallback:             能力或指令不可用時怎麼走
```

這張卡防止「表面上使用了 dev-flow，實際上直接自行實作」。

## 全流程

```text
模糊大想法（多 session 才裝得下、路徑在霧裡）
  └─ /wayfinder ── 建 decision-ticket map，一次解一題
       ├─ HITL 決策票 → grilling ＋ domain-modeling（一次一題訪談）
       ├─ AFK research 票 → research（背景 agent 查一手來源）
       ├─ 「長怎樣/怎麼動」票 → prototype（丟棄式原型）
       └─ 路徑清楚、無票可解 → 往下

既有系統 baseline 不可信（Pyright/pytest 大面積紅、既有 failure 與新工作糾纏）
  └─ diagnosing-bugs／baseline stabilization
       ├─ 釐清哪些 failure 是既有問題、哪些是新引入
       ├─ 讓 type/test/lint baseline 歸零，或建立有證據的 accepted baseline
       └─ baseline gate 穩定後才進入 architecture/spec/implementation

範圍有限、決策已收斂、但涉及跨模組 architecture（bounded architecture change）
  └─ codebase-design（＋/grill-with-docs 落 ADR＋glossary＋acceptance checklist）
       └─ 直接進 shape selection，不為一個 bounded slice 強走 to-spec → to-tickets

共識已在對話中（destination 明確、決策已定）
  └─ /to-spec ──→ 凍結 contract（plan-directory repo 落 .agent_state/plans/<task>/spec.md）
       └─ /to-tickets ──→ tracer-bullet 垂直切片＋blocking edges
            │   （plan-directory repo：無依賴票 → 平行 lane；依賴鏈 → slice queue；
            │     expand–contract → foundation 先落 integration branch）
            └─ orchestrate 依選定 shape 派發（worktree、task branch、exact-SHA review）

驗收與收尾
  ├─ lane/slice 級：orchestrate 的 reviewer 角色（packet 帶 Spec/Standards 兩軸
  │    語彙；Standards 軸引用 code-review 的 smell baseline）
  ├─ 整合後、landing 前：code-review（fixed point = persistence tip；
  │    Spec 軸對 to-spec 產出的 frozen contract）
  ├─ 可選品質清理：simplify（只改品質不找 bug；改動需重跑 targeted tests）
  └─ landing：遵循 repo policy 與當前使用者授權——squash、merge、rebase、直接
       commit 都不是全域預設；任何 persistence landing 都需當下明確授權
```

## 決策表

| 工作形狀 | 路線 |
|---|---|
| 小、低風險、單一 coherent change | quick exit／root-only |
| 測試或型別 baseline 已紅 | `diagnosing-bugs` → baseline stabilization |
| 模組 boundary／public interface／test seam／ownership 未定 | `codebase-design`（＋`domain-modeling` 固定詞彙） |
| 不知道哪裡值得改善、找 deep-module opportunity | `/improve-codebase-architecture` |
| 大型模糊工作、跨 session | `/wayfinder` |
| 想法明確但決策沒對齊 | `grilling`（＋`domain-modeling`） |
| 訪談中的決策需要落檔（ADR／glossary） | `/grill-with-docs`（checkpoint mode 批次寫入） |
| 需要 repo 外的事實才能決定 | `research` |
| 「該長怎樣／state model 對不對」吵不出結果 | `prototype` |
| 共識已收斂，需要 frozen contract | `/to-spec` |
| 有 spec、要拆 blocking slices | `/to-tickets` |
| 一個 coherent implementation slice | orchestrate single-writer |
| 多個真正獨立 slices | orchestrate normal wave |
| 不可逆 core 且 dependent work 即將堆疊 | orchestrate critical checkpoint |
| 有 named risk，但不構成 critical barrier | writer ＋ independent cumulative review |
| root handoff 成本確實高於工作 | root-only（Route Card 明記理由） |
| 實作純邏輯 slice（state machine、schema、wire contract） | `tdd`（紅綠循環；seam 來自凍結的 spec，不重開） |
| 東西壞了／測試紅了／效能退化 | `diagnosing-bugs`（先建 feedback loop） |
| 問「接下來做什麼」／盤點欠帳 | `candidate-backlog list --status inbox`（按 area 分組供用戶裁決） |
| diff 已正確、只需品質整理 | `simplify` |
| landing 前正式驗收 | `code-review`（slice 級 review 由 orchestrate 分級派發，不用它） |
| GitHub PR review | 當前環境提供的 PR review workflow（有專用 GitHub skill 優先；否則用內建指令） |

## 進入實作前：shape selection

四種 shape（定義、觸發條件與完整流程見 orchestrate 的 Pipeline shapes 表；此處只給路由語彙）：

- **root-only**：root 親自實作；沒有 identity separation。
- **single-writer**：一位 implementer 寫 coherent slice；root 負責 freeze、harvest、review、integration。
- **normal wave**：兩個以上真正獨立的 slices 平行推進。
- **critical checkpoint**：不可逆 core ＋ dependent work 即將堆疊，形成 review barrier。

開始改碼前必須明確選一種並寫入 Route Card——不可默默把 root-only 當預設。至少回答：

1. Freeze／dispatch／harvest 成本是否真的大於工作本身？
2. 是否存在值得不同 identity 檢查的 named risk？
3. 是否有兩個以上真正獨立的 slices？
4. 是否有依賴工作即將堆疊在不可逆的 critical core 上？

選 root-only 時明說：為何 handoff 不值得、缺少 independent identity 的限制、
以哪些測試／contract check／其他證據補足。

**Reviewer 觸發＝named risk，不是改動檔案多**。named risk 軸向例：process ownership、
persistence、shutdown/cleanup、concurrency/atomicity、wire schema、security boundary、
destructive migration、hardware authority、mutation retry／unknown outcome、
public contract compatibility。命中時 Route Card 的 Review policy 寫明具體 risk、
reviewer identity（≠ implementer）、barrier 位置（在 dependent work 堆疊之前）。
不是每個 single-writer 都必須配 independent reviewer。

### Capability／authority check

推薦 orchestrate delegation 前確認：runtime 允許 sub-agent、使用者已授權 delegation、
concurrency slots 足夠、repo 適合 worktree／task branch、當前 dirty tree 能安全切
lane、commit／branch／landing 已授權。任一不成立 → 退回 root-only ＋ Route Card 明記
限制與補強證據——不要假裝 implementer／reviewer 已被使用。

## 粒度交接：wayfinder 停在哪、planner 從哪接手

判準：**wayfinder 產出決策，planner 產出推導**。測試——「兩個稱職工程師拿同樣的決策
與程式碼，會收斂到相同答案嗎？」會 → 可推導，執行期由 `contract-planner` just-in-time
補（它讀的是當前程式碼，不會腐爛）；不會 → 真決策，wayfinder/用戶層。

耐久度梯度（越早期產出必須越耐久，因為 wayfinder 跨多 session）：

- **wayfinder**：destination、out-of-scope、領域詞彙、不可逆軸向選擇（persistence／
  wire schema 哲學、ownership 劃分）、價值取捨——能活過 refactor 的層次。
- **to-spec / to-tickets**：模組級介面概念、schema 形狀、測試 seam（HITL 確認）、
  垂直切片＋驗收＋blocking edges。不寫 file path／code（prototype 固化的決策片段例外）。
- **planner（執行期）**：精確 integration point、write scope 切分、wave 內順序、
  targeted-test 指令——一切從當前程式碼可推導的。

下限：後續階段永遠不需要重開決策（重開＝contract-level 中斷，最貴）。上限：可推導的
一律不寫（早期寫死的程式碼細節到執行時是腐爛的假權威）。一句話：**具體到「不需要再問
用戶就能動工」為止，然後停手。**

## 三個 review 的分工（不要混用）

- **`code-review`** = 找問題、只回報：Standards（repo 規範＋Fowler smell baseline）
  與 Spec（是否忠實實作 frozen contract）兩個 sub-agent 平行跑、分開回報。
- **`simplify`** = 改品質、直接動手：reuse／簡化／效率，明確不找 bug。
- **GitHub PR review** = 用當前環境提供的 PR review workflow；不把特定 UI command
  當永久介面。

## candidate-backlog 檢查點

candidate-backlog 要求規劃某 area 前先查 inbox。除了「問接下來做什麼」，在這四個
節點各做一次 area-scoped check：進入 `/to-spec` 前、進入 `/to-tickets` 前、freeze
implementation slice 前、task close 前。只撿順路項目，不擴張 scope。

## 後端慣例（所有 pipeline skill 共用）

產物落點依 repo 而定，三個層級依序判斷：

1. **plan-directory repo**（CLAUDE.md 記載 `planning-with-files`／`.agent_state/plans/`）：
   一切落 plan 目錄，**絕不**建 tracker issue 或 workflow state 檔。
2. **tracker repo**（有 `docs/agents/issue-tracker.md` 之類的文件）：照該文件的
   issue／label／blocking 慣例。
3. **都沒有**：落 `.scratch/`，並告知用戶位置。
