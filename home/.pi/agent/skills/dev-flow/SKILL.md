---
name: dev-flow
description: Route a heavy, multi-session development effort through the pipeline — wayfinder → to-spec → to-tickets → orchestrate → acceptance (code-review + simplify) → landing → close-out. Use only when the work is too large for one session or needs a frozen contract before implementation; smaller tasks never enter this pipeline.
---

# Dev Flow

重型長時任務的管線路線圖。本 skill 只導航，不執行（收尾清單除外）；交接時說明
目前處於哪一站、以及進入下一站的理由。

兩層管線各自完整：dev-flow 是**外層串行管線**（站點＝skill，一次一站）；orchestrate
站內部自帶**併發管線**的心智模型（lane 空間並行、slice pipeline 時間並行、hazard 判斷、
wave 間檢討），由該 skill 自述，本層不重複。

**不適用**：單 session 裝得下的工作不進這條管線——直接做，或按各 skill 自己的
description 判斷取用。

## 管線

```text
模糊大想法（多 session 才裝得下、路徑在霧裡）
  └─ wayfinder ──→ 建 decision-ticket map，一次解一票，直到路徑清楚
       └─ to-spec ──→ 把已收斂的共識凍結成 contract
            └─ to-tickets ──→ tracer-bullet 垂直切片＋blocking edges
                 └─ orchestrate ──→ 依 shape 派工實作、slice 級 review、整合
                      └─ 驗收（landing 前）──→ code-review：effort 級雙軸 audit，
                      │     Spec 軸對 frozen contract、也對照 wayfinder 的
                      │     destination；＋ simplify：品質清理。兩者產生的改動
                      │     跟最終 gate 一起重驗，不另走一輪管線
                      └─ landing ──→ 依 orchestrate 的 landing 流程、repo policy
                           │     與當下授權
                           └─ 收尾 ──→ 本 skill 內建，見下節
```

各站的觸發條件、內部流程與產物落點由各 skill 自述。其他 skill（grilling、research、
prototype、domain-modeling、codebase-design、tdd、diagnosing-bugs…）是按需工具：
由各站或 agent 依其 description 自行取用，不是管線站點，本圖不列。

進入會展開長流程或凍結 contract 的站（wayfinder、to-spec）前，先用一句話向 user
確認再繼續；to-tickets 接在剛核准的 spec 後屬自然接續，不需再問。

## Effort 收尾（landing 後）

effort 級的關閉動作，orchestrate 只關自己的 task，不關這些：

- **關閉 wayfinder map**：殘餘 frontier／fog 逐項處置——已被 destination 覆蓋的
  close、仍有價值但出了本 effort 的移入 candidate-backlog，map 不留懸置票。
- **詞彙與決策落檔**：途中沉澱但尚未寫入的 glossary 條目／ADR 補寫
  （用 domain-modeling 的格式與 ADR 三條件）。
- **candidate-backlog 掃尾**：實作中發現但出界的東西進 inbox，不擴 scope 也不丟失。
- **plan directory 歸檔**：task narrative 收尾（planning-with-files），
  spec／map 保持指向最終落地 SHA 的狀態。
- **向 user 回報 effort 級總結**：destination 達成狀況、留下的 backlog、
  被推翻或調整過的決策。

## 粒度交接：wayfinder 停在哪、planner 從哪接手

判準：**wayfinder 產出決策，planner 產出推導**。測試——「兩個稱職工程師拿同樣的決策
與程式碼，會收斂到相同答案嗎？」會 → 可推導，執行期由 `contract-planner` just-in-time
補（它讀的是當前程式碼，不會腐爛）；不會 → 真決策，wayfinder/用戶層。

耐久度梯度（越早期產出必須越耐久，因為 wayfinder 跨多 session）：

- **wayfinder**：destination、out-of-scope、領域詞彙、不可逆軸向選擇（persistence／
  wire schema 哲學、ownership 劃分）、價值取捨——能活過 refactor 的層次。
- **to-spec / to-tickets**：模組級介面概念、schema 形狀、測試 seam（HITL 確認）、
  垂直切片的初始切法＋blocking edges（執行期可再拆，見下）、驗收（凍結）。
  不寫 file path／code（prototype 固化的決策片段例外）。
- **planner（執行期）**：精確 integration point、write scope 切分、wave 內順序、
  targeted-test 指令——一切從當前程式碼可推導的。

下限：後續階段永遠不需要重開決策（重開＝contract-level 中斷，最貴）。上限：可推導的
一律不寫（早期寫死的程式碼細節到執行時是腐爛的假權威）。一句話：**具體到「不需要再問
用戶就能動工」為止，然後停手。**

Ticket 邊界屬 planner 層可推導物，不是 frozen contract 的一部分：執行期發現某票超出
single-context，直接拆票、更新 DAG 與 durable plan 後繼續——frozen 的是 contract 與
acceptance，不是最初寫下的 ticket 外形。

執行期也可新增 **enabling refactor / dependency-extraction task**：當現有 code seam 被證明
尚未成熟、硬做原票會增加等待、衝突或返工時，先抽出一個只解除結構阻塞的前置工作。這不是
spec 變更，也不重開 wayfinder；在 durable plan 只記 blocked ticket、discovered seam、unblocked
dependents 與新的 DAG。若不能說明它省下哪個等待／衝突／返工成本，就不要新增這類票。
