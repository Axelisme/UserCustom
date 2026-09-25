// The collab lock module, tested directly: no Pi runtime and no git.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { chmod, mkdir, mkdtemp, readFile, rm, utimes, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { test } from "node:test";

import {
  repositoryLockTarget,
  taskLockTarget,
  withOwnedLock,
} from "../home/.pi/agent/extensions/collab-op/lock.ts";

async function gitDir(t) {
  const directory = await mkdtemp(path.join(tmpdir(), "collab-lock-"));
  t.after(async () => {
    await chmod(path.join(directory, "collab-op-locks"), 0o700).catch(() => {});
    await rm(directory, { recursive: true, force: true });
  });
  return directory;
}

async function writeLock(target, custody) {
  await mkdir(path.dirname(target.lockPath), { recursive: true });
  await writeFile(target.lockPath, typeof custody === "string" ? custody : JSON.stringify(custody));
}

function deadPid() {
  const child = spawnSync(process.execPath, ["-e", ""]);
  return child.pid;
}

async function rejectsWith(promise, code) {
  let caught;
  await promise.then(
    () => assert.fail(`expected ${code}`),
    (error) => { caught = error; },
  );
  assert.equal(caught.code, code, String(caught));
  return caught;
}

function deferred() {
  let resolve;
  const promise = new Promise((r) => { resolve = r; });
  return { promise, resolve };
}

test("targets place task and repository locks under the git directory", async (t) => {
  const directory = await gitDir(t);
  const task = taskLockTarget(directory, "demo");
  const repository = repositoryLockTarget(directory);
  assert.equal(task.lockPath, path.join(directory, "collab-op-locks", "demo.lock"));
  assert.equal(task.busyCode, "task_busy");
  assert.equal(repository.lockPath, path.join(directory, "collab-op-locks", ".repository.lock"));
  assert.equal(repository.busyCode, "repository_busy");
});

test("fail-fast runs the body while holding the lock and releases it", async (t) => {
  const target = taskLockTarget(await gitDir(t), "demo");
  const result = await withOwnedLock(target, async () => {
    const custody = JSON.parse(await readFile(target.lockPath, "utf8"));
    assert.equal(custody.pid, process.pid);
    assert.equal(custody.task_id, "demo");
    return "done";
  });
  assert.equal(result, "done");
  assert.equal(existsSync(target.lockPath), false);
});

test("a body failure still releases the lock and surfaces the body error", async (t) => {
  const target = taskLockTarget(await gitDir(t), "demo");
  await assert.rejects(
    withOwnedLock(target, async () => { throw new Error("body failed"); }),
    /body failed/,
  );
  assert.equal(existsSync(target.lockPath), false);
});

test("fail-fast refuses a live owner and leaves its lock untouched", async (t) => {
  const target = taskLockTarget(await gitDir(t), "demo");
  const custody = JSON.stringify({ pid: process.pid, started_at: "2000-01-01T00:00:00Z", token: "other" });
  await writeLock(target, custody);
  let ran = false;
  const error = await rejectsWith(withOwnedLock(target, async () => { ran = true; }), "task_busy");
  assert.equal(ran, false);
  assert.deepEqual(error.details.held_by, { pid: process.pid, started_at: "2000-01-01T00:00:00Z" });
  assert.equal(await readFile(target.lockPath, "utf8"), custody);
});

test("a lock whose owner pid is dead is taken over", async (t) => {
  const target = taskLockTarget(await gitDir(t), "demo");
  await writeLock(target, { pid: deadPid(), started_at: "2000-01-01T00:00:00Z", token: "gone" });
  const result = await withOwnedLock(target, async () => "ran");
  assert.equal(result, "ran");
  assert.equal(existsSync(target.lockPath), false);
});

test("unreadable custody is stale only once it is older than a day", async (t) => {
  const target = taskLockTarget(await gitDir(t), "demo");
  await writeLock(target, "not json");
  await rejectsWith(withOwnedLock(target, async () => "fresh"), "task_busy");

  const twoDaysAgo = new Date(Date.now() - 2 * 24 * 60 * 60 * 1000);
  await utimes(target.lockPath, twoDaysAgo, twoDaysAgo);
  assert.equal(await withOwnedLock(target, async () => "old"), "old");
  assert.equal(existsSync(target.lockPath), false);
});

test("release leaves a replacement written by someone else byte-for-byte", async (t) => {
  const target = taskLockTarget(await gitDir(t), "demo");
  const foreign = JSON.stringify({ pid: process.pid, started_at: "2000-01-01T00:00:00Z", token: "foreign" });
  await withOwnedLock(target, async () => {
    await rm(target.lockPath);
    await writeFile(target.lockPath, foreign);
  });
  assert.equal(await readFile(target.lockPath, "utf8"), foreign);
});

test("a failed release poisons the target until the lock path is gone", { skip: process.getuid?.() === 0 && "root ignores directory permissions" }, async (t) => {
  const target = taskLockTarget(await gitDir(t), "demo");
  const locks = path.dirname(target.lockPath);
  await rejectsWith(
    withOwnedLock(target, async () => { await chmod(locks, 0o500); }),
    "lock_release_failed",
  );
  await chmod(locks, 0o700);
  let ran = false;
  const poisoned = await rejectsWith(withOwnedLock(target, async () => { ran = true; }), "lock_release_failed");
  assert.equal(ran, false);
  assert.equal(poisoned.details.lock_path, target.lockPath);

  await rm(target.lockPath);
  assert.equal(await withOwnedLock(target, async () => "recovered"), "recovered");
});

test("waiting callers run one at a time in arrival order", async (t) => {
  const target = repositoryLockTarget(await gitDir(t));
  const events = [];
  const gate = deferred();
  const runs = [1, 2, 3].map((id) =>
    withOwnedLock(target, async () => {
      events.push(`start ${id}`);
      if (id === 1) await gate.promise;
      events.push(`end ${id}`);
      return id;
    }, { policy: "wait" }),
  );
  await new Promise((resolve) => setTimeout(resolve, 50));
  assert.deepEqual(events, ["start 1"]);
  gate.resolve();
  assert.deepEqual(await Promise.all(runs), [1, 2, 3]);
  assert.deepEqual(events, ["start 1", "end 1", "start 2", "end 2", "start 3", "end 3"]);
  assert.equal(existsSync(target.lockPath), false);
});

test("bounded wait refuses with the time it waited once the deadline passes", async (t) => {
  const target = taskLockTarget(await gitDir(t), "demo");
  await writeLock(target, { pid: process.pid, started_at: "2000-01-01T00:00:00Z", token: "other" });
  const error = await rejectsWith(
    withOwnedLock(target, async () => {}, { policy: "bounded-wait", timeoutMs: 100 }),
    "task_busy",
  );
  assert.equal(error.details.timeout_ms, 100);
  assert.ok(error.details.waited_ms >= 100, `waited ${error.details.waited_ms} ms`);
});

test("a queued caller aborted before its turn never runs", async (t) => {
  const target = repositoryLockTarget(await gitDir(t));
  const gate = deferred();
  const first = withOwnedLock(target, () => gate.promise, { policy: "wait" });
  const controller = new AbortController();
  let ran = false;
  const second = withOwnedLock(target, async () => { ran = true; }, { policy: "wait", signal: controller.signal });
  controller.abort();
  await rejectsWith(second, "request_aborted");
  gate.resolve("first");
  assert.equal(await first, "first");
  assert.equal(ran, false);
  assert.equal(existsSync(target.lockPath), false);
});
