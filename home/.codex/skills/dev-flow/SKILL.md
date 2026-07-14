---
name: dev-flow
description: Orient in the development-skill pipeline — which skill to use at which stage, from a vague idea through spec, tickets, orchestrated implementation, review, and landing. Use when the user asks "which skill/flow should I use next", wants the full workflow map, or starts a large effort and needs a route through the skills.
---

# Dev Flow

這是各 development skill 的路線圖：告訴你「現在處於哪個階段、下一步用哪個 skill」。
本 skill 只導航，不執行——判斷完階段後 invoke 對應 skill。

## 快速退出

小任務不走 pipeline：單檔小修、問答、單回合 review 直接做（或直接走 `orchestrate`
single-writer）。這條 pipeline 只給「需要先想清楚才能動手」的中大型工作。

## 全流程

```text
模糊大想法（多 session 才裝得下、路徑在霧裡）
  └─ /wayfinder ── 建 decision-ticket map，一次解一題
       ├─ HITL 決策票 → /grilling ＋ /domain-modeling（一次一題訪談）
       ├─ AFK research 票 → /research（背景 agent 查一手來源）
       ├─ 「長怎樣/怎麼動」票 → /prototype（丟棄式原型）
       └─ 路徑清楚、無票可解 → 往下

共識已在對話中（destination 明確、決策已定）
  └─ /to-spec ──→ 凍結 contract（plan-directory repo 落 .agent_state/plans/<task>/spec.md）
       └─ /to-tickets ──→ tracer-bullet 垂直切片＋blocking edges
            │   （plan-directory repo：無依賴票 → 平行 lane；依賴鏈 → slice queue；
            │     expand–contract → foundation 先落 integration branch）
            └─ orchestrate 派發 implementer/reviewer（worktree、task branch、
                 review-readiness packet、merge slot）

驗收與收尾
  ├─ lane/slice 級：orchestrate 的 reviewer 角色（packet 帶 Spec/Standards 兩軸
  │    語彙；Standards 軸引用 code-review 的 smell baseline）
  ├─ 整合後、landing 前：/code-review（fixed point = persistence tip；
  │    Spec 軸對 to-spec 產出的 frozen contract）
  ├─ 可選品質清理：/simplify（只改品質不找 bug；改動需重跑 targeted tests）
  └─ landing：squash 單 commit，需用戶明確授權（MCCT）
```

## 各階段的進入判斷

| 你手上的東西 | 用 |
|---|---|
| 模糊想法，一個 session 裝不下 | `/wayfinder`（先 chart，之後每 session 解一票） |
| 想法明確但決策沒對齊 | `/grilling`（＋`/domain-modeling` 固定詞彙） |
| 需要 repo 外的事實才能決定 | `/research` |
| 「該長怎樣／state model 對不對」吵不出結果 | `/prototype` |
| 討論收斂、該寫下來了 | `/to-spec` |
| 有 spec、要拆成可派工的單位 | `/to-tickets` |
| 有票／有明確 scope、要動手 | `orchestrate`（single-writer 為預設路徑） |
| diff 完成、要找問題 | `/code-review`（兩軸：Standards＋Spec） |
| diff 正確、想更乾淨 | `/simplify` |
| GitHub PR review | 內建 `/review` |

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

- **`/code-review`** = 找問題、只回報：Standards（repo 規範＋Fowler smell baseline）
  與 Spec（是否忠實實作 frozen contract）兩個 sub-agent 平行跑、分開回報。
- **`/simplify`** = 改品質、直接動手：reuse／簡化／效率，明確不找 bug。
- **內建 `/review`** = GitHub PR 專用。

## 後端慣例（所有 pipeline skill 共用）

產物落點依 repo 而定，三個層級依序判斷：

1. **plan-directory repo**（CLAUDE.md 記載 `planning-with-files`／`.agent_state/plans/`）：
   一切落 plan 目錄，**絕不**建 tracker issue 或 workflow state 檔。
2. **tracker repo**（有 `docs/agents/issue-tracker.md` 之類的文件）：照該文件的
   issue／label／blocking 慣例。
3. **都沒有**：落 `.scratch/`，並告知用戶位置。
