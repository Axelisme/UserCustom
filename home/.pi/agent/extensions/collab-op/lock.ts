import { randomUUID } from "node:crypto";
import { constants as fsConstants } from "node:fs";
import { mkdir, open, readFile, rename, unlink } from "node:fs/promises";
import path from "node:path";
import { CollabOpError, pathMetadata } from "./shared.ts";

const LOCK_TTL_MS = 24 * 60 * 60 * 1000;
const LOCK_POLL_MS = 25;

/**
 * Collab mutation lock Module
 *
 * An ownership-safe filesystem lock with a process-local FIFO queue.
 * `withOwnedLock(target, body, options)` runs `body` while holding the lock
 * file at `target.lockPath`:
 * - "fail-fast" refuses at once with `target.busyCode` while a live owner
 *   holds the lock;
 * - "bounded-wait" queues and refuses with `waited_ms`/`timeout_ms` once
 *   `timeoutMs` elapses;
 * - "wait" queues without a deadline.
 * Waiting policies are abortable until the body starts. A lock whose owner
 * pid is dead, or whose custody is unreadable and older than a day, is taken
 * over. Release removes the lock only while it still carries this caller's
 * token; a replacement written by someone else is left byte-for-byte. A
 * failed release poisons the target: later calls refuse with
 * `lock_release_failed` until the lock path is gone.
 * FIFO ordering is process-local; filesystem contenders have no cross-process
 * order guarantee.
 */

export type LockPolicy = "fail-fast" | "bounded-wait" | "wait";

export type LockOptions =
  | { policy?: "fail-fast" | "wait"; signal?: AbortSignal }
  | { policy: "bounded-wait"; signal?: AbortSignal; timeoutMs: number };

type LockCustody = { pid: number; started_at: string; token: string | null };

export type LockTarget = {
  key: string;
  lockPath: string;
  busyCode: "task_busy" | "repository_busy";
  busyMessage: string;
  label: string;
  details: Record<string, unknown>;
  custodyFields: Record<string, unknown>;
};

type AcquiredLock = { lockPath: string; token: string };

type LockWaiter<T> = {
  target: LockTarget;
  body: () => Promise<T>;
  signal?: AbortSignal;
  deadline: number | null;
  timeoutMs: number | null;
  startedAt: number;
  resolve: (value: T) => void;
  reject: (reason: unknown) => void;
};

const lockQueues = new Map<string, Array<LockWaiter<unknown>>>();
const lockReleaseFailures = new Map<string, CollabOpError>();

/** The lock one collab task holds while it mutates, under the Git common directory. */
export function taskLockTarget(gitDir: string, taskId: string): LockTarget {
  const lockPath = path.join(gitDir, "collab-op-locks", `${taskId}.lock`);
  return {
    key: path.resolve(lockPath),
    lockPath,
    busyCode: "task_busy",
    busyMessage: `another collab operation is in progress for task ${taskId}`,
    label: `task ${taskId}`,
    details: { task_id: taskId },
    custodyFields: { task_id: taskId },
  };
}

/** The lock every collab Git mutation in one repository holds first. */
export function repositoryLockTarget(gitDir: string): LockTarget {
  const commonDir = path.resolve(gitDir);
  const lockPath = path.join(commonDir, "collab-op-locks", ".repository.lock");
  return {
    key: path.resolve(lockPath),
    lockPath,
    busyCode: "repository_busy",
    busyMessage: "another collab Git mutation is in progress for this repository",
    label: "repository",
    details: { git_common_dir: commonDir },
    custodyFields: { scope: "repository" },
  };
}

function lockBusyError(
  target: LockTarget,
  custody?: LockCustody | null,
  details: Record<string, unknown> = {},
): CollabOpError {
  return new CollabOpError(
    target.busyCode,
    target.busyMessage,
    "Wait for the in-flight operation to finish, then retry.",
    {
      ...target.details,
      ...(custody === undefined || custody === null
        ? {}
        : { held_by: { pid: custody.pid, started_at: custody.started_at } }),
      ...details,
    },
  );
}

function removeWaiterAbortHandler(waiter: LockWaiter<unknown>): void {
  const handler = (waiter as unknown as { __abortHandler?: () => void }).__abortHandler;
  if (handler && waiter.signal) {
    try { waiter.signal.removeEventListener("abort", handler); } catch {}
  }
  (waiter as unknown as { __abortHandler?: unknown }).__abortHandler = undefined;
}

function requestAbortedError(target: LockTarget): CollabOpError {
  return new CollabOpError(
    "request_aborted",
    "request was aborted",
    "Retry the operation after the caller is ready.",
    target.details,
  );
}

function lockReleaseError(target: LockTarget): CollabOpError {
  return new CollabOpError(
    "lock_release_failed",
    `could not release the ${target.label} lock`,
    "Inspect the reported lock path, remove it only after confirming no collab operation owns it, then restart Pi.",
    { ...target.details, lock_path: target.lockPath },
  );
}

async function rejectIfLockReleaseFailed(target: LockTarget): Promise<void> {
  const failure = lockReleaseFailures.get(target.key);
  if (!failure) return;
  if ((await pathMetadata(target.lockPath)) === null) {
    lockReleaseFailures.delete(target.key);
    return;
  }
  throw failure;
}

function advanceLockQueue(key: string): void {
  const queue = lockQueues.get(key);
  if (!queue || queue.length === 0) {
    lockQueues.delete(key);
    return;
  }
  setTimeout(() => void processLockQueue(key), 0);
}

function removeLockWaiter(key: string, waiter: LockWaiter<unknown>): void {
  const queue = lockQueues.get(key);
  if (!queue) return;
  const index = queue.indexOf(waiter);
  if (index !== -1) queue.splice(index, 1);
  if (queue.length === 0) lockQueues.delete(key);
}

function rejectLockQueue(key: string, error: CollabOpError): void {
  const queue = lockQueues.get(key) ?? [];
  lockQueues.delete(key);
  for (const waiter of queue) {
    removeWaiterAbortHandler(waiter);
    waiter.reject(error);
  }
}

async function releaseQueuedLock(
  waiter: LockWaiter<unknown>,
  acquired: AcquiredLock,
): Promise<boolean> {
  if (await releaseOwnedLock(acquired.lockPath, acquired.token)) return true;
  const error = lockReleaseError(waiter.target);
  lockReleaseFailures.set(waiter.target.key, error);
  rejectLockQueue(waiter.target.key, error);
  return false;
}

async function processLockQueue(key: string): Promise<void> {
  const queue = lockQueues.get(key);
  if (!queue || queue.length === 0) {
    lockQueues.delete(key);
    return;
  }
  const waiter = queue[0] as LockWaiter<unknown>;
  while (true) {
    if (waiter.signal?.aborted) {
      const current = lockQueues.get(key);
      if (current && current[0] === waiter) {
        current.shift();
        removeWaiterAbortHandler(waiter);
        waiter.reject(requestAbortedError(waiter.target));
        advanceLockQueue(key);
      }
      return;
    }
    const now = Date.now();
    if (waiter.deadline !== null && now >= waiter.deadline) {
      const current = lockQueues.get(key);
      if (current && current[0] === waiter) {
        current.shift();
        removeWaiterAbortHandler(waiter);
        waiter.reject(lockBusyError(waiter.target, undefined, {
          waited_ms: now - waiter.startedAt,
          timeout_ms: waiter.timeoutMs,
        }));
        advanceLockQueue(key);
      }
      return;
    }
    try {
      const acquired = await acquireOwnedLock(waiter.target);
      const lockedQueue = lockQueues.get(key);
      if (!lockedQueue || lockedQueue[0] !== waiter) {
        await releaseQueuedLock(waiter, acquired);
        return;
      }
      if (waiter.signal?.aborted) {
        if (!(await releaseQueuedLock(waiter, acquired))) return;
        lockedQueue.shift();
        removeWaiterAbortHandler(waiter);
        waiter.reject(requestAbortedError(waiter.target));
        advanceLockQueue(key);
        return;
      }
      if (waiter.deadline !== null && Date.now() >= waiter.deadline) {
        if (!(await releaseQueuedLock(waiter, acquired))) return;
        lockedQueue.shift();
        removeWaiterAbortHandler(waiter);
        waiter.reject(lockBusyError(waiter.target, undefined, {
          waited_ms: Date.now() - waiter.startedAt,
          timeout_ms: waiter.timeoutMs,
        }));
        advanceLockQueue(key);
        return;
      }
      // Once the body starts, its AbortSignal owns cancellation. Do not reject
      // the outer promise until the body has settled and both locks are gone.
      removeWaiterAbortHandler(waiter);
      let bodyResult: unknown;
      let bodyError: unknown;
      let bodySucceeded = false;
      try {
        bodyResult = await waiter.body();
        bodySucceeded = true;
      } catch (error) {
        bodyError = error;
      }
      if (!(await releaseQueuedLock(waiter, acquired))) return;
      removeLockWaiter(key, waiter);
      removeWaiterAbortHandler(waiter);
      if (bodySucceeded) waiter.resolve(bodyResult);
      else waiter.reject(bodyError);
      advanceLockQueue(key);
      return;
    } catch (error) {
      if (error instanceof CollabOpError && error.code === waiter.target.busyCode) {
        const current = lockQueues.get(key);
        if (!current || current[0] !== waiter) return;
        const remaining = waiter.deadline === null ? LOCK_POLL_MS : waiter.deadline - Date.now();
        if (waiter.deadline !== null && remaining <= 0) continue;
        await new Promise<void>((resolve) => setTimeout(resolve, Math.min(LOCK_POLL_MS, remaining)));
        continue;
      }
      removeLockWaiter(key, waiter);
      removeWaiterAbortHandler(waiter);
      waiter.reject(error);
      advanceLockQueue(key);
      return;
    }
  }
}

function pidIsAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return (error as NodeJS.ErrnoException).code === "EPERM";
  }
}

async function readLockContents(lockPath: string): Promise<string | null> {
  try {
    return await readFile(lockPath, "utf8");
  } catch {
    return null;
  }
}

function parseLockCustody(contents: string | null): LockCustody | null {
  if (contents === null) return null;
  try {
    const parsed = JSON.parse(contents) as {
      pid?: unknown;
      started_at?: unknown;
      token?: unknown;
    };
    if (typeof parsed.pid !== "number" || typeof parsed.started_at !== "string") return null;
    return {
      pid: parsed.pid,
      started_at: parsed.started_at,
      token: typeof parsed.token === "string" ? parsed.token : null,
    };
  } catch {
    return null;
  }
}

type InspectedLock = {
  dev: number;
  ino: number;
  mtimeMs: number;
  contents: string | null;
  custody: LockCustody | null;
};

function lockIsStale(custody: LockCustody | null, mtimeMs: number): boolean {
  if (custody === null) return Date.now() - mtimeMs > LOCK_TTL_MS;
  return !pidIsAlive(custody.pid);
}

async function inspectLock(lockPath: string): Promise<InspectedLock | null> {
  const metadata = await pathMetadata(lockPath);
  if (metadata === null) return null;
  const contents = await readLockContents(lockPath);
  return {
    dev: metadata.dev,
    ino: metadata.ino,
    mtimeMs: metadata.mtimeMs,
    contents,
    custody: parseLockCustody(contents),
  };
}

// Shared ownership-safe quarantine primitive used by both stale takeover and
// release. It atomically renames whatever occupies the canonical lock path to
// a unique quarantine name, then verifies the moved inode and ownership token.
async function quarantineAndVerifyOwnership(
  lockPath: string,
  inspected: InspectedLock,
  expectedToken: string | null,
): Promise<
  | { state: "owned"; quarantinePath: string }
  | { state: "restored" }
  | { state: "retained"; quarantinePath: string }
> {
  const quarantinePath = `${lockPath}.quarantine-${process.pid}-${randomUUID()}`;
  try {
    await rename(lockPath, quarantinePath);
  } catch (error) {
    const failure = error as NodeJS.ErrnoException;
    if (failure.code === "ENOENT") return { state: "restored" };
    throw new CollabOpError(
      "git_error",
      `could not quarantine the collab lock: ${failure.message}`,
    );
  }
  const moved = await pathMetadata(quarantinePath);
  if (moved === null) return { state: "restored" };
  const movedContents = await readLockContents(quarantinePath);
  const movedCustody = parseLockCustody(movedContents);
  const ownedInode = moved.dev === inspected.dev && moved.ino === inspected.ino;
  const ownedIdentity = expectedToken === null
    ? inspected.contents !== null && movedContents === inspected.contents
    : movedCustody !== null && movedCustody.token === expectedToken;
  if (ownedInode && ownedIdentity) {
    return { state: "owned", quarantinePath };
  }
  if ((await pathMetadata(lockPath)) === null) {
    try {
      await rename(quarantinePath, lockPath);
      return { state: "restored" };
    } catch {
      // The canonical path was occupied again; retain and fail closed below.
    }
  }
  return { state: "retained", quarantinePath };
}

async function removeVerifiedQuarantine(
  quarantinePath: string,
  expected: InspectedLock,
): Promise<void> {
  const metadata = await pathMetadata(quarantinePath);
  if (metadata === null) return;
  if (metadata.dev === expected.dev && metadata.ino === expected.ino) {
    try {
      await unlink(quarantinePath);
    } catch {
      // The quarantine name is unique to this operation; a failed removal
      // leaves only an inert artifact.
    }
  }
}

async function acquireOwnedLock(target: LockTarget): Promise<AcquiredLock> {
  await mkdir(path.dirname(target.lockPath), { recursive: true, mode: 0o700 });
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const token = randomUUID();
    try {
      const handle = await open(
        target.lockPath,
        fsConstants.O_CREAT | fsConstants.O_EXCL | fsConstants.O_WRONLY | fsConstants.O_NOFOLLOW,
        0o600,
      );
      try {
        await handle.writeFile(
          JSON.stringify({
            pid: process.pid,
            started_at: new Date().toISOString(),
            ...target.custodyFields,
            token,
          }),
          { encoding: "utf8" },
        );
      } finally {
        await handle.close();
      }
      return { lockPath: target.lockPath, token };
    } catch (error) {
      const failure = error as NodeJS.ErrnoException;
      if (failure.code !== "EEXIST") {
        throw new CollabOpError(
          "git_error",
          `could not acquire the ${target.label} lock: ${failure.message}`,
        );
      }
      const inspected = await inspectLock(target.lockPath);
      if (inspected === null) continue;
      if (!lockIsStale(inspected.custody, inspected.mtimeMs)) {
        throw lockBusyError(target, inspected.custody);
      }
      const result = await quarantineAndVerifyOwnership(target.lockPath, inspected, null);
      if (result.state === "owned") {
        await removeVerifiedQuarantine(result.quarantinePath, inspected);
        continue;
      }
      if (result.state === "restored") continue;
      throw lockBusyError(target, undefined, {
        retained_quarantine: result.quarantinePath,
        reason: `${target.label} lock changed concurrently during stale takeover`,
      });
    }
  }
  throw lockBusyError(target, undefined, {
    reason: `${target.label} lock could not be acquired`,
  });
}

async function releaseOwnedLock(lockPath: string, token: string): Promise<boolean> {
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      const inspected = await inspectLock(lockPath);
      if (inspected === null) return true;
      const result = await quarantineAndVerifyOwnership(lockPath, inspected, token);
      if (result.state === "owned") {
        await removeVerifiedQuarantine(result.quarantinePath, inspected);
      }
      // owned: the canonical path is free; restored/retained: it no longer
      // contains our token. Either way this caller no longer owns the path.
      return true;
    } catch {
      if (attempt < 2) {
        await new Promise<void>((resolve) => setTimeout(resolve, LOCK_POLL_MS));
      }
    }
  }
  return false;
}

export async function withOwnedLock<T>(
  target: LockTarget,
  body: () => Promise<T>,
  options: LockOptions = {},
): Promise<T> {
  await rejectIfLockReleaseFailed(target);
  const policy = options.policy ?? "fail-fast";
  if (policy === "fail-fast") {
    const acquired = await acquireOwnedLock(target);
    let bodyResult: T | undefined;
    let bodyError: unknown;
    let bodySucceeded = false;
    try {
      bodyResult = await body();
      bodySucceeded = true;
    } catch (error) {
      bodyError = error;
    }
    if (!(await releaseOwnedLock(acquired.lockPath, acquired.token))) {
      const error = lockReleaseError(target);
      lockReleaseFailures.set(target.key, error);
      throw error;
    }
    if (bodySucceeded) return bodyResult as T;
    throw bodyError;
  }
  const signal = options.signal;
  if (signal?.aborted) throw requestAbortedError(target);
  const timeoutMs = options.policy === "bounded-wait" ? options.timeoutMs : null;
  const startedAt = Date.now();
  const deadline = timeoutMs === null ? null : startedAt + timeoutMs;
  return new Promise<T>((resolve, reject) => {
    const waiter: LockWaiter<T> = {
      target,
      body,
      signal,
      deadline,
      timeoutMs,
      startedAt,
      resolve,
      reject,
    };
    let queue = lockQueues.get(target.key);
    if (!queue) {
      queue = [];
      lockQueues.set(target.key, queue);
    }
    queue.push(waiter as unknown as LockWaiter<unknown>);
    if (signal) {
      const abortHandler = () => {
        const current = lockQueues.get(target.key);
        if (!current) return;
        const index = current.indexOf(waiter as unknown as LockWaiter<unknown>);
        if (index === -1) return;
        current.splice(index, 1);
        if (current.length === 0) lockQueues.delete(target.key);
        try { signal.removeEventListener("abort", abortHandler); } catch {}
        (waiter as unknown as { __abortHandler?: unknown }).__abortHandler = undefined;
        waiter.reject(requestAbortedError(target));
        if (index === 0) advanceLockQueue(target.key);
      };
      (waiter as unknown as { __abortHandler?: () => void }).__abortHandler = abortHandler;
      signal.addEventListener("abort", abortHandler, { once: true });
    }
    if (queue.length === 1) void processLockQueue(target.key);
  });
}
