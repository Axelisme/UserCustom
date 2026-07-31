# Candidate Backlog Lifecycle

```text
inbox --bind--> planned --close implemented--> resolved
inbox --close implemented (rider, with evidence)--> resolved
inbox/planned --close declined|duplicate|obsolete|not-reproducible|out-of-scope--> closed
```

- `bind` 綁定 task-id（CLI 只驗證格式；dev-flow task record 的存在與正確性屬 task record
  慣例與 review 職責，CLI 不跨界檢查）；正式 task 的 generic ticket 反向引用 backlog ID。
- 實作完成但尚未整合仍是 `planned`。
- `implemented` 接受 `planned`（task-id 必須與 plan 綁定值相同）或 `inbox` 直達（順風單：規劃時
  併入 slice、收尾時直接關）；一律要求 task-id、至少一個 commit 與 validation evidence。完成表示
  缺口已消失、驗證完成且已整合至正式目標 branch。
- `duplicate` 必須指向另一個存在的 canonical ID，且不可指向自己。
- 其它 close reason 可從 inbox 或 planned 進入 closed，並保留原因與時間。
- 不直接刪除 resolved/closed 記錄；真正需要團隊長期共享的事項提升至 tracked 文件或 issue tracker。
