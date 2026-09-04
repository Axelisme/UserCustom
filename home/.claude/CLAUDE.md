# Always-resident authority index

1. **Fixed subject:** Every review binds to one immutable fixed subject; a Git-backed subject is one exact clean commit and tree.
2. **Mutation authority:** Persistence mutation requires current user authority or an in-force task-scoped user grant naming the mutation and its conditions.
3. **Reorientation:** After compaction or handoff, reread every skill still governing the work, dev-flow and collab included: a summary of a rule is not the rule, and recalling that you once read one is not having read it. Then take the task `INDEX.md` and handed-off ticket, and follow only their pointers needed for current work. When that closure cannot identify the next action, maintain the record instead of scanning all tickets, artifacts, or the task DAG to infer one.
4. **Custody:** Preserve pre-existing user dirt and non-task evidence; never stash, reset, overwrite, or delete it.
5. **Test surface:** Tests validate only observable behavior and Interfaces; prose, document wording, static content, configuration values, and repository data remain outside the test surface.
6. **Subagent scheduling:** Launch subagents in the background and continue independent work rather than block-waiting or polling; each foreground wait keeps the turn open, blocks compaction, and can exhaust the context window.
