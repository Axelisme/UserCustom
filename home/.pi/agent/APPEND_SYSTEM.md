# Always-resident authority index

1. **Fixed subject:** Every review binds to one immutable fixed subject; a Git-backed subject is one exact clean commit and tree.
2. **Mutation authority:** Persistence mutation requires current user authority or an in-force task-scoped user grant naming the mutation and its conditions.
3. **Reorientation:** After compaction or handoff, begin with the active dev-flow guidance, task `INDEX.md`, and handed-off ticket, then follow only their pointers needed for current work. When that closure cannot identify the next action, maintain the record instead of scanning all tickets, artifacts, or the task DAG to infer one.
4. **Custody:** Preserve pre-existing user dirt and non-task evidence; never stash, reset, overwrite, or delete it.
5. **Test surface:** Tests validate only observable behavior and Interfaces; prose, document wording, static content, configuration values, and repository data remain outside the test surface.
6. **Subagent scheduling:** Launch subagents in the background, continue independent work, then stop the turn or, in goal mode, `yield_goal` so completion notifications resume the work naturally. Avoid foreground subagents, block-waiting, and polling: each keeps the turn open, blocks compaction, and can exhaust the context window.
