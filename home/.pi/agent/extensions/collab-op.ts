import { randomUUID } from "node:crypto";
import { constants as fsConstants } from "node:fs";
import { appendFile, cp, lstat, mkdir, open, readdir, readFile, readlink, realpath, rename, rm, rmdir, stat, symlink, unlink } from "node:fs/promises";
import path from "node:path";
import { type ExtensionAPI, type ExtensionContext } from "@earendil-works/pi-coding-agent";
const TOOL_VERSION = 1;
const IDENTIFIER = /^[a-z0-9][a-z0-9._-]*$/;
type GitResult = { code: number; stdout: string; stderr: string };
export type WorktreeRecord = {
  worktree?: string;
  HEAD?: string;
  branch?: string;
  detached?: boolean;
};

type RefRecord = {
  object: string | null;
  symbolicTarget: string | null;
};

export type GitRunner = (
  cwd: string,
  args: readonly string[],
  signal?: AbortSignal,
) => Promise<GitResult>;

export type Repository = {
  worktreeRoot: string;
  controlRoot: string;
  gitDir: string;
  git: GitRunner;
};

export class TaskLayout {
  readonly root: string;
  readonly integrationBranch: string;
  readonly integrationBaseRef: string;
  readonly integrationPath: string;
  readonly persistenceRef: string;

  constructor(
    readonly repo: Repository,
    readonly taskId: string,
  ) {
    this.root = path.join(repo.controlRoot, ".agent_state", "worktrees", taskId);
    this.integrationBranch = `wave/${taskId}/integration`;
    this.integrationBaseRef = `refs/orchestrate/${taskId}/integration/base`;
    this.integrationPath = path.join(this.root, "integration");
    this.persistenceRef = `refs/orchestrate/${taskId}/persistence`;
  }

  laneBranch(laneId: string): string {
    return `wave/${this.taskId}/${laneId}`;
  }

  lanePath(laneId: string): string {
    return path.join(this.root, "lanes", laneId);
  }
}

class CollabOpError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly repair?: string,
    readonly details?: Record<string, unknown>,
  ) {
    super(message);
  }
}

function requireIdentifier(value: unknown, label: string): string {
  if (typeof value !== "string" || !IDENTIFIER.test(value)) {
    throw new CollabOpError(
      "invalid_identifier",
      `${label} must match ${IDENTIFIER.source}`,
      `Use a lowercase ${label} containing only letters, digits, dot, underscore, or hyphen.`,
    );
  }
  return value;
}

function gitRunner(pi: ExtensionAPI): GitRunner {
  return async (cwd, args, signal) => {
    const result = await pi.exec("git", [...args], { cwd, signal });
    return { code: result.code, stdout: result.stdout, stderr: result.stderr };
  };
}

const TASK_LOCK_TTL_MS = 24 * 60 * 60 * 1000;

const LANE_CREATE_BOUNDED_WAIT_MS = 10_000;
const LANE_CREATE_POLL_MS = 25;

/**
 * Task mutation lock Module
 *
 * Fail-fast default: withTaskLock without a bounded-wait policy attempts the filesystem lock immediately and throws task_busy if held.
 * Lane-create-only bounded-wait: only registered collab_lane with action create may pass { policy: "bounded-wait", signal, timeoutMs: 10000 } to wait.
 * FIFO boundary: one process-local FIFO per canonical repository control root (path.resolve) and taskId; only its head polls the ownership-safe filesystem lock at a short bounded interval; no fairness promise against another OS process.
 * Cancellation: an AbortSignal abort removes only that waiter, returns request_aborted, and advances the next eligible waiter without cancelling siblings.
 * Timeout: a fixed ten-second deadline returns the existing task_busy error with bounded wait facts (task_id, waited_ms, timeout_ms) without mutation or leaked queue state.
 * Ownership-safe release: release uses quarantine-and-verify by inode and token, never unlinking the canonical path, restoring foreign replacements or retaining on conflict.
 * Placement revalidation: lane placement (laneCreate) retains per-call request/signal/receipt/error and, after acquisition, re-reads requireManagedIntegration and laneInventory under the held lock before any mutation.
 */

type TaskLockOptions = {
  policy?: "fail-fast" | "bounded-wait";
  signal?: AbortSignal;
  timeoutMs?: number;
};

type TaskLockWaiter<T> = {
  id: string;
  repo: Repository;
  taskId: string;
  key: string;
  body: () => Promise<T>;
  signal?: AbortSignal;
  deadline: number;
  startedAt: number;
  resolve: (value: T) => void;
  reject: (reason: unknown) => void;
};

const taskLockQueues = new Map<string, Array<TaskLockWaiter<unknown>>>();

function taskLockQueueKey(repo: Repository, taskId: string): string {
  return `${path.resolve(repo.controlRoot)}\0${taskId}`;
}

async function processTaskLockQueue(key: string): Promise<void> {
  const queue = taskLockQueues.get(key);
  if (!queue || queue.length === 0) {
    taskLockQueues.delete(key);
    return;
  }
  const waiter = queue[0] as TaskLockWaiter<unknown>;
  const startedAt = waiter.startedAt;
  const deadline = waiter.deadline;
  const taskId = waiter.taskId;
  const advance = () => {
    const q = taskLockQueues.get(key);
    if (!q) return;
    if (q.length === 0) taskLockQueues.delete(key);
    else setTimeout(() => void processTaskLockQueue(key), 0);
  };
  while (true) {
    const abortBeforeAttempt = waiter.signal?.aborted;
    if (abortBeforeAttempt) {
      const q = taskLockQueues.get(key);
      if (q && q[0] === waiter) {
        q.shift();
        const handler = (waiter as unknown as { __abortHandler?: () => void }).__abortHandler;
        if (handler && waiter.signal) {
          try { waiter.signal.removeEventListener("abort", handler); } catch {}
        }
        waiter.reject(new CollabOpError("request_aborted", "request was aborted", "Retry the operation after the caller is ready.", { task_id: taskId }));
        advance();
      }
      return;
    }
    const now = Date.now();
    if (now >= deadline) {
      const q = taskLockQueues.get(key);
      if (q && q[0] === waiter) {
        q.shift();
        const handler = (waiter as unknown as { __abortHandler?: () => void }).__abortHandler;
        if (handler && waiter.signal) {
          try { waiter.signal.removeEventListener("abort", handler); } catch {}
        }
        const waitedMs = now - startedAt;
        waiter.reject(new CollabOpError("task_busy", `another collab operation is in progress for task ${taskId}`, "Wait for the in-flight operation to finish, then retry.", { task_id: taskId, waited_ms: waitedMs, timeout_ms: LANE_CREATE_BOUNDED_WAIT_MS }));
        advance();
      }
      return;
    }
    try {
      const acquired = await acquireTaskLock(waiter.repo, waiter.taskId);
      const lockedQueue = taskLockQueues.get(key);
      const stillHead = !!lockedQueue && lockedQueue[0] === waiter;
      if (!stillHead) {
        try { await releaseTaskLock(acquired.lockPath, acquired.token); } catch {}
        return;
      }
      if (waiter.signal?.aborted) {
        try { await releaseTaskLock(acquired.lockPath, acquired.token); } catch {}
        lockedQueue!.shift();
        const handler = (waiter as unknown as { __abortHandler?: () => void }).__abortHandler;
        if (handler && waiter.signal) {
          try { waiter.signal.removeEventListener("abort", handler); } catch {}
        }
        waiter.reject(new CollabOpError("request_aborted", "request was aborted", "Retry the operation after the caller is ready.", { task_id: taskId }));
        advance();
        return;
      }
      if (Date.now() >= waiter.deadline) {
        try { await releaseTaskLock(acquired.lockPath, acquired.token); } catch {}
        lockedQueue!.shift();
        const handler = (waiter as unknown as { __abortHandler?: () => void }).__abortHandler;
        if (handler && waiter.signal) {
          try { waiter.signal.removeEventListener("abort", handler); } catch {}
        }
        const waitedMs = Date.now() - startedAt;
        waiter.reject(new CollabOpError("task_busy", `another collab operation is in progress for task ${taskId}`, "Wait for the in-flight operation to finish, then retry.", { task_id: taskId, waited_ms: waitedMs, timeout_ms: LANE_CREATE_BOUNDED_WAIT_MS }));
        advance();
        return;
      }
      let bodyResult: unknown;
      let bodyError: unknown;
      let bodySucceeded = false;
      try {
        bodyResult = await waiter.body();
        bodySucceeded = true;
      } catch (e) {
        bodyError = e;
      }
      try { await releaseTaskLock(acquired.lockPath, acquired.token); } catch {}
      const q2 = taskLockQueues.get(key);
      if (q2 && q2[0] === waiter) q2.shift();
      else if (q2) {
        const idx = q2.indexOf(waiter);
        if (idx !== -1) q2.splice(idx, 1);
      }
      const handler2 = (waiter as unknown as { __abortHandler?: () => void }).__abortHandler;
      if (handler2 && waiter.signal) {
        try { waiter.signal.removeEventListener("abort", handler2); } catch {}
      }
      if (bodySucceeded) waiter.resolve(bodyResult as unknown);
      else waiter.reject(bodyError);
      advance();
      return;
    } catch (error) {
      if (error instanceof CollabOpError && error.code === "task_busy") {
        const q = taskLockQueues.get(key);
        if (!q || q[0] !== waiter) return;
        if (waiter.signal?.aborted) {
          q.shift();
          const handler = (waiter as unknown as { __abortHandler?: () => void }).__abortHandler;
          if (handler && waiter.signal) {
            try { waiter.signal.removeEventListener("abort", handler); } catch {}
          }
          waiter.reject(new CollabOpError("request_aborted", "request was aborted", "Retry the operation after the caller is ready.", { task_id: taskId }));
          advance();
          return;
        }
        const remaining = deadline - Date.now();
        if (remaining <= 0) continue;
        const sleepMs = Math.min(LANE_CREATE_POLL_MS, remaining);
        await new Promise<void>(resolve => setTimeout(resolve, sleepMs));
        continue;
      } else {
        const q = taskLockQueues.get(key);
        if (q && q[0] === waiter) q.shift();
        else if (q) {
          const idx = q.indexOf(waiter);
          if (idx !== -1) q.splice(idx, 1);
        }
        const handler = (waiter as unknown as { __abortHandler?: () => void }).__abortHandler;
        if (handler && waiter.signal) {
          try { waiter.signal.removeEventListener("abort", handler); } catch {}
        }
        waiter.reject(error);
        advance();
        return;
      }
    }
  }
}

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

async function repositoryObjectFormat(
  repo: Repository,
  signal?: AbortSignal,
): Promise<"sha1" | "sha256"> {
  const result = await repo.git(
    repo.worktreeRoot,
    ["rev-parse", "--show-object-format"],
    signal,
  );
  const value = result.stdout.trim();
  if (result.code === 0 && (value === "sha1" || value === "sha256")) return value;
  // Older Git without --show-object-format: derive the format from an exact
  // validated object id length.
  const probe = await repo.git(
    repo.worktreeRoot,
    ["rev-parse", "--verify", "--quiet", "HEAD^{commit}"],
    signal,
  );
  const oid = probe.stdout.trim();
  if (probe.code === 0 && /^[0-9a-f]{64}$/.test(oid)) return "sha256";
  return "sha1";
}

async function zeroOidFor(repo: Repository, signal?: AbortSignal): Promise<string> {
  return (await repositoryObjectFormat(repo, signal)) === "sha256"
    ? "0".repeat(64)
    : "0".repeat(40);
}

function lockDirectory(repo: Repository): string {
  return path.join(repo.gitDir, "collab-op-locks");
}

function lockFilePath(repo: Repository, taskId: string): string {
  return path.join(lockDirectory(repo), `${taskId}.lock`);
}

function pidIsAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return (error as NodeJS.ErrnoException).code === "EPERM";
  }
}

type TaskLockCustody = { pid: number; started_at: string; token: string | null };

type AcquiredTaskLock = { lockPath: string; token: string };

async function readLockCustody(lockPath: string): Promise<TaskLockCustody | null> {
  try {
    const parsed = JSON.parse(await readFile(lockPath, "utf8")) as {
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
  custody: TaskLockCustody | null;
};

function lockIsStale(custody: TaskLockCustody | null, mtimeMs: number): boolean {
  if (custody === null) return Date.now() - mtimeMs > TASK_LOCK_TTL_MS;
  return !pidIsAlive(custody.pid);
}

async function inspectTaskLock(lockPath: string): Promise<InspectedLock | null> {
  const metadata = await pathMetadata(lockPath);
  if (metadata === null) return null;
  return {
    dev: metadata.dev,
    ino: metadata.ino,
    mtimeMs: metadata.mtimeMs,
    custody: await readLockCustody(lockPath),
  };
}

// Shared ownership-safe quarantine primitive used by both stale takeover and
// release. It atomically renames whatever occupies the canonical lock path to
// a unique quarantine name (rename never unlinks its source, so a live
// replacement can never be deleted), then verifies the moved file against the
// inspected identity and the expected ownership token. A foreign moved file
// is restored to the canonical path when it is free, or retained under the
// quarantine name and reported as fail-closed otherwise.
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
      `could not quarantine the task lock: ${failure.message}`,
    );
  }
  const moved = await pathMetadata(quarantinePath);
  if (moved === null) return { state: "restored" };
  const movedCustody = await readLockCustody(quarantinePath);
  const ownedInode = moved.dev === inspected.dev && moved.ino === inspected.ino;
  const ownedToken =
    expectedToken === null ||
    (movedCustody !== null && movedCustody.token === expectedToken);
  if (ownedInode && ownedToken) {
    return { state: "owned", quarantinePath };
  }
  // The moved file is not the one we inspected or own: restore it when the
  // canonical path is free; otherwise retain it and fail closed rather than
  // ever clobbering another owner.
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

async function acquireTaskLock(
  repo: Repository,
  taskId: string,
): Promise<AcquiredTaskLock> {
  const directory = lockDirectory(repo);
  const lockPath = lockFilePath(repo, taskId);
  await mkdir(directory, { recursive: true, mode: 0o700 });
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const token = randomUUID();
    try {
      const handle = await open(
        lockPath,
        fsConstants.O_CREAT | fsConstants.O_EXCL | fsConstants.O_WRONLY | fsConstants.O_NOFOLLOW,
        0o600,
      );
      try {
        await handle.writeFile(
          JSON.stringify({
            pid: process.pid,
            started_at: new Date().toISOString(),
            task_id: taskId,
            token,
          }),
          { encoding: "utf8" },
        );
      } finally {
        await handle.close();
      }
      return { lockPath, token };
    } catch (error) {
      const failure = error as NodeJS.ErrnoException;
      if (failure.code !== "EEXIST") {
        throw new CollabOpError(
          "git_error",
          `could not acquire the task lock: ${failure.message}`,
        );
      }
      // Inspect the existing lock and verify ownership by inode before any
      // takeover mutation.
      const inspected = await inspectTaskLock(lockPath);
      if (inspected === null) continue;
      if (!lockIsStale(inspected.custody, inspected.mtimeMs)) {
        throw new CollabOpError(
          "task_busy",
          `another collab operation is in progress for task ${taskId}`,
          "Wait for the in-flight operation to finish, then retry.",
          inspected.custody === null
            ? { task_id: taskId }
            : {
                task_id: taskId,
                held_by: {
                  pid: inspected.custody.pid,
                  started_at: inspected.custody.started_at,
                },
              },
        );
      }
      const result = await quarantineAndVerifyOwnership(lockPath, inspected, null);
      if (result.state === "owned") {
        await removeVerifiedQuarantine(result.quarantinePath, inspected);
        continue; // retry acquisition at the now-free canonical path
      }
      if (result.state === "restored") {
        continue; // retry; the restored file is inspected fresh on the next pass
      }
      throw new CollabOpError(
        "task_busy",
        `task lock for ${taskId} changed concurrently during stale takeover`,
        "Wait for the in-flight operation to finish, then retry.",
        { task_id: taskId, retained_quarantine: result.quarantinePath },
      );
    }
  }
  throw new CollabOpError(
    "task_busy",
    `task lock for ${taskId} could not be acquired`,
    "Wait for the in-flight operation to finish, then retry.",
    { task_id: taskId },
  );
}

async function releaseTaskLock(lockPath: string, token: string): Promise<void> {
  try {
    // Rename the canonical lock away first, then verify the moved file's
    // ownership; the canonical path is never unlinked, so a replacement that
    // appears after the initial inspection is restored or retained, never
    // deleted.
    const inspected = await inspectTaskLock(lockPath);
    if (inspected === null) return;
    const result = await quarantineAndVerifyOwnership(lockPath, inspected, token);
    if (result.state === "owned") {
      await removeVerifiedQuarantine(result.quarantinePath, inspected);
    }
    // "restored": the foreign replacement is back at the canonical path;
    // "retained": it could not be restored and stays under its quarantine
    // name; both fail closed without deleting anything.
  } catch {
    // A failed release is recovered by staleness; never force a removal here.
  }
}

export async function withTaskLock<T>(
  repo: Repository,
  taskId: string,
  body: () => Promise<T>,
  options?: TaskLockOptions,
): Promise<T> {
  const policy = options?.policy;
  if (policy !== "bounded-wait") {
    const { lockPath, token } = await acquireTaskLock(repo, taskId);
    try {
      return await body();
    } finally {
      await releaseTaskLock(lockPath, token);
    }
  }
  const signal = options?.signal;
  const timeoutMs = options?.timeoutMs ?? LANE_CREATE_BOUNDED_WAIT_MS;
  if (signal?.aborted) {
    throw new CollabOpError("request_aborted", "request was aborted", "Retry the operation after the caller is ready.", { task_id: taskId });
  }
  const key = taskLockQueueKey(repo, taskId);
  const startedAt = Date.now();
  const deadline = startedAt + timeoutMs;
  return new Promise<T>((resolve, reject) => {
    const waiter: TaskLockWaiter<T> = { id: randomUUID(), repo, taskId, key, body, signal, deadline, startedAt, resolve, reject };
    let queue = taskLockQueues.get(key);
    if (!queue) { queue = []; taskLockQueues.set(key, queue); }
    queue.push(waiter as unknown as TaskLockWaiter<unknown>);
    let abortHandler: (() => void) | undefined;
    if (signal) {
      abortHandler = () => {
        const q = taskLockQueues.get(key);
        if (!q) return;
        const idx = q.indexOf(waiter as unknown as TaskLockWaiter<unknown>);
        if (idx === -1) return;
        q.splice(idx, 1);
        if (q.length === 0) taskLockQueues.delete(key);
        try { signal.removeEventListener("abort", abortHandler!); } catch {}
        (waiter as unknown as { __abortHandler?: unknown }).__abortHandler = undefined;
        waiter.reject(new CollabOpError("request_aborted", "request was aborted", "Retry the operation after the caller is ready.", { task_id: taskId }));
        if (idx === 0) {
          const remaining = taskLockQueues.get(key);
          if (remaining && remaining.length > 0) setTimeout(() => void processTaskLockQueue(key), 0);
        }
      };
      (waiter as unknown as { __abortHandler?: () => void }).__abortHandler = abortHandler;
      signal.addEventListener("abort", abortHandler, { once: true });
    }
    if (queue.length === 1) void processTaskLockQueue(key);
  });
}

async function requireGit(
  run: GitRunner,
  cwd: string,
  args: readonly string[],
  signal?: AbortSignal,
): Promise<string> {
  const result = await run(cwd, args, signal);
  if (result.code !== 0) {
    const detail = result.stderr.trim() || result.stdout.trim() || `exit ${result.code}`;
    throw new CollabOpError("git_error", `Git command failed: ${detail}`);
  }
  return result.stdout.trim();
}

export async function discoverRepository(
  run: GitRunner,
  cwd: string,
  signal?: AbortSignal,
): Promise<Repository> {
  const rootProbe = await run(cwd, ["rev-parse", "--show-toplevel"], signal);
  if (rootProbe.code !== 0 || !rootProbe.stdout.trim()) {
    throw new CollabOpError(
      "not_git_repository",
      "the selected path is not in a Git worktree",
      "Pass an absolute Git worktree-root path as repo, or omit repo and run from inside a Git worktree.",
    );
  }
  const worktreeRoot = path.resolve(rootProbe.stdout.trim());
  const common = await requireGit(
    run,
    worktreeRoot,
    ["rev-parse", "--path-format=absolute", "--git-common-dir"],
    signal,
  );
  const commonDir = path.resolve(common);
  return {
    worktreeRoot,
    controlRoot: path.basename(commonDir) === ".git" ? path.dirname(commonDir) : commonDir,
    gitDir: commonDir,
    git: run,
  };
}

const AGENT_STATE_DIRECTORY = ".agent_state";
// git check-ignore matches a directory-only pattern only when the probed path
// names a directory, and the managed root usually does not exist yet on a
// first establishing call, so the probe always carries the trailing slash.
const AGENT_STATE_PROBE = `${AGENT_STATE_DIRECTORY}/`;
const AGENT_STATE_PATTERN = `/${AGENT_STATE_DIRECTORY}/`;

async function agentStateIsIgnored(repo: Repository, signal?: AbortSignal): Promise<boolean> {
  const result = await repo.git(
    repo.controlRoot,
    ["check-ignore", "-q", "--", AGENT_STATE_PROBE],
    signal,
  );
  if (result.code === 0) return true;
  if (result.code === 1) return false;
  const detail = result.stderr.trim() || result.stdout.trim() || `exit ${result.code}`;
  throw agentStateExclusionIoError(
    `check whether ${AGENT_STATE_DIRECTORY} is ignored`,
    path.join(repo.gitDir, "info", "exclude"),
    new Error(detail),
    { git_exit_code: result.code },
  );
}

// Only the worktree-root .gitignore outranks the common directory's
// info/exclude for a repository-root path, so its negations are the complete
// candidate set for an exclusion that verification found ineffective.
async function negatingIgnorePatterns(
  repo: Repository,
): Promise<Array<{ source: string; line: number; pattern: string }>> {
  const gitignore = path.join(repo.controlRoot, ".gitignore");
  let content: string;
  try {
    content = await readFile(gitignore, "utf8");
  } catch {
    return [];
  }
  const negations: Array<{ source: string; line: number; pattern: string }> = [];
  content.split("\n").forEach((raw, index) => {
    const pattern = raw.trim();
    if (!pattern.startsWith("!")) return;
    negations.push({ source: ".gitignore", line: index + 1, pattern });
  });
  return negations.slice(0, 8);
}

function agentStateExclusionIoError(
  operation: string,
  excludeFile: string,
  error: unknown,
  details: Record<string, unknown> = {},
): CollabOpError {
  const failure = error as NodeJS.ErrnoException;
  const detail = failure.message?.trim() || String(error);
  return new CollabOpError(
    "agent_state_exclusion_io_error",
    `could not ${operation} for ${excludeFile}: ${detail}`,
    `Make the repository's common Git info directory and ${excludeFile} writable regular paths, then retry.`,
    {
      operation,
      exclude_file: excludeFile,
      ...(failure.code ? { filesystem_code: failure.code } : {}),
      ...details,
    },
  );
}

/**
 * Make the acting repository ignore the managed state directory, returning the
 * warning that reports a performed write and null when nothing was written.
 */
async function ensureAgentStateIgnored(
  repo: Repository,
  signal?: AbortSignal,
): Promise<string | null> {
  const excludeFile = path.join(repo.gitDir, "info", "exclude");
  let excludeMetadata;
  try {
    excludeMetadata = await pathMetadata(excludeFile);
  } catch (error) {
    throw agentStateExclusionIoError("inspect the exclusion file", excludeFile, error);
  }
  if (excludeMetadata !== null && !excludeMetadata.isFile()) {
    const pathType = excludeMetadata.isSymbolicLink()
      ? "symbolic link"
      : excludeMetadata.isDirectory()
        ? "directory"
        : "non-regular path";
    throw agentStateExclusionIoError(
      "validate the exclusion file",
      excludeFile,
      new Error(`${excludeFile} is a ${pathType}, not a regular file`),
      { path_type: pathType },
    );
  }
  if (await agentStateIsIgnored(repo, signal)) return null;
  try {
    await mkdir(path.dirname(excludeFile), { recursive: true });
  } catch (error) {
    throw agentStateExclusionIoError("create the exclusion directory", excludeFile, error);
  }
  let existing = "";
  try {
    existing = await readFile(excludeFile, "utf8");
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ENOENT") {
      throw agentStateExclusionIoError("read the exclusion file", excludeFile, error);
    }
  }
  const alreadyWritten = existing
    .split("\n")
    .some((line) => line.trim() === AGENT_STATE_PATTERN);
  let wroteExclusion = false;
  if (!alreadyWritten) {
    const separator = existing.length > 0 && !existing.endsWith("\n") ? "\n" : "";
    try {
      await appendFile(excludeFile, `${separator}${AGENT_STATE_PATTERN}\n`);
      wroteExclusion = true;
    } catch (error) {
      throw agentStateExclusionIoError("append the exclusion pattern", excludeFile, error);
    }
  }
  if (!(await agentStateIsIgnored(repo, signal))) {
    const overriding = await negatingIgnorePatterns(repo);
    const writeOutcome = wroteExclusion
      ? `; the appended line remains in ${excludeFile}`
      : `; this call did not modify ${excludeFile}`;
    throw new CollabOpError(
      "agent_state_not_ignored",
      `${AGENT_STATE_DIRECTORY} is still not ignored even though ${AGENT_STATE_PATTERN} is present in ${excludeFile}${writeOutcome}`,
      `${wroteExclusion ? `The appended line remains in ${excludeFile}. ` : ""}Remove the ignore rule that re-includes ${AGENT_STATE_DIRECTORY}, or ignore ${AGENT_STATE_DIRECTORY} in the repository, then retry.`,
      {
        exclude_file: excludeFile,
        pattern: AGENT_STATE_PATTERN,
        exclude_written: wroteExclusion,
        ...(overriding.length ? { overriding_patterns: overriding } : {}),
      },
    );
  }
  return alreadyWritten
    ? null
    : `wrote ${AGENT_STATE_PATTERN} to ${excludeFile} so managed task state is not reported as untracked`;
}

async function commitAt(
  repo: Repository,
  ref: string,
  signal?: AbortSignal,
): Promise<string | null> {
  const result = await repo.git(
    repo.worktreeRoot,
    ["rev-parse", "--verify", "--quiet", `${ref}^{commit}`],
    signal,
  );
  const value = result.stdout.trim();
  return result.code === 0 && /^[0-9a-f]{40,64}$/.test(value) ? value : null;
}

async function refNames(
  repo: Repository,
  prefix: string,
  signal?: AbortSignal,
): Promise<string[]> {
  const output = await requireGit(
    repo.git,
    repo.worktreeRoot,
    ["for-each-ref", "--format=%(refname)", prefix],
    signal,
  );
  return output ? output.split("\n").filter(Boolean) : [];
}

async function refSnapshot(
  repo: Repository,
  prefixes: readonly string[],
  signal?: AbortSignal,
): Promise<Map<string, RefRecord>> {
  const output = await requireGit(
    repo.git,
    repo.worktreeRoot,
    ["for-each-ref", "--format=%(refname)%09%(objectname)%09%(symref)", ...prefixes],
    signal,
  );
  const refs = new Map<string, RefRecord>();
  for (const line of output.split("\n")) {
    if (!line) continue;
    const [name, object, symbolicTarget] = line.split("\t");
    refs.set(name, {
      object: /^[0-9a-f]{40,64}$/.test(object) ? object : null,
      symbolicTarget: symbolicTarget || null,
    });
  }
  return refs;
}

async function isAncestor(
  repo: Repository,
  ancestor: string,
  descendant: string,
  signal?: AbortSignal,
): Promise<boolean> {
  const result = await repo.git(
    repo.worktreeRoot,
    ["merge-base", "--is-ancestor", ancestor, descendant],
    signal,
  );
  if (result.code === 0) return true;
  if (result.code === 1) return false;
  throw new CollabOpError(
    "git_error",
    `could not compare Git ancestry: ${result.stderr.trim() || result.stdout.trim()}`,
  );
}

async function worktreeRecords(
  repo: Repository,
  signal?: AbortSignal,
): Promise<WorktreeRecord[]> {
  const output = await requireGit(
    repo.git,
    repo.worktreeRoot,
    ["worktree", "list", "--porcelain"],
    signal,
  );
  if (!output) return [];
  return output.split(/\n\n+/).map((block) => {
    const record: WorktreeRecord = {};
    for (const line of block.split("\n")) {
      if (line.startsWith("worktree ")) record.worktree = path.resolve(line.slice(9));
      else if (line.startsWith("HEAD ")) record.HEAD = line.slice(5);
      else if (line.startsWith("branch ")) record.branch = line.slice(7);
      else if (line === "detached") record.detached = true;
    }
    return record;
  });
}

async function pathMetadata(pathname: string) {
  try {
    return await lstat(pathname);
  } catch (error) {
    const failure = error as NodeJS.ErrnoException;
    if (failure.code === "ENOENT" || failure.code === "ENOTDIR") return null;
    throw error;
  }
}

async function pathIsDirectory(pathname: string): Promise<boolean> {
  return (await pathMetadata(pathname))?.isDirectory() ?? false;
}

// Generic Collab dirt is tracked-only: staged and unstaged tracked changes
// count, while ordinary untracked and ignored paths do not.
async function hasTrackedDirt(
  repo: Repository,
  worktree: string,
  signal?: AbortSignal,
): Promise<boolean> {
  const result = await repo.git(
    worktree,
    ["status", "--porcelain=v1", "--untracked-files=no"],
    signal,
  );
  if (result.code !== 0) {
    throw new CollabOpError(
      "git_error",
      `could not inspect worktree state: ${result.stderr.trim() || result.stdout.trim()}`,
    );
  }
  return result.stdout.length > 0;
}

async function warnManagedWorktree(
  repo: Repository,
  records: readonly WorktreeRecord[],
  expectedPath: string,
  branch: string,
  head: string | null,
  label: string,
  warnings: string[],
  signal?: AbortSignal,
): Promise<void> {
  const branchRef = `refs/heads/${branch}`;
  const matches = records.filter((record) => record.branch === branchRef);
  if (matches.length !== 1) {
    warnings.push(`${label} worktree registration is missing or ambiguous`);
    return;
  }
  const record = matches[0];
  if (
    record.worktree !== expectedPath ||
    record.HEAD !== head ||
    !(await pathIsDirectory(expectedPath))
  ) {
    warnings.push(`${label} worktree identity does not match managed refs`);
    return;
  }
  if (await hasTrackedDirt(repo, expectedPath, signal)) warnings.push(`${label} worktree is dirty`);
}

async function taskIds(repo: Repository, signal?: AbortSignal): Promise<string[]> {
  const names = await refNames(repo, "refs/orchestrate/", signal);
  const tasks = new Set<string>();
  for (const name of names) {
    const match = /^refs\/orchestrate\/([^/]+)\/integration\/base$/.exec(name);
    if (match && IDENTIFIER.test(match[1])) tasks.add(match[1]);
  }
  return [...tasks].sort();
}

async function recordEvent(
  task: TaskLayout,
  operation: string,
  outcome: string,
  fields: Record<string, unknown> = {},
): Promise<string | null> {
  const stateRoot = path.join(task.repo.controlRoot, ".agent_state");
  const candidates = [
    path.join(stateRoot, "plans", task.taskId),
    path.join(stateRoot, "archives", task.taskId),
  ];
  let container: string | null = null;
  for (const candidate of candidates) {
    if (await pathIsDirectory(candidate)) {
      container = candidate;
      break;
    }
  }
  if (container === null) {
    return "task container is unavailable; telemetry was not recorded";
  }

  try {
    const directory = path.join(container, ".collab_op");
    const metadata = await pathMetadata(directory);
    if (metadata !== null && !metadata.isDirectory()) {
      throw new Error("telemetry directory is not a regular directory");
    }
    await mkdir(directory, { mode: 0o700, recursive: true });
    const telemetry = path.join(directory, "telemetry.jsonl");
    const handle = await open(
      telemetry,
      fsConstants.O_APPEND |
        fsConstants.O_CREAT |
        fsConstants.O_WRONLY |
        fsConstants.O_NOFOLLOW,
      0o600,
    );
    try {
      const event = {
        event_version: 1,
        tool_version: TOOL_VERSION,
        at: new Date().toISOString(),
        task_id: task.taskId,
        operation,
        outcome,
        ...fields,
      };
      await handle.writeFile(`${JSON.stringify(event)}\n`, { encoding: "utf8" });
    } finally {
      await handle.close();
    }
    return null;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return `telemetry was not recorded: ${message}`;
  }
}

async function requireLocalBranch(
  repo: Repository,
  value: unknown,
  label: string,
  signal?: AbortSignal,
): Promise<{ name: string; ref: string }> {
  if (
    typeof value !== "string" ||
    value.length === 0 ||
    value.startsWith("-") ||
    value.startsWith("refs/")
  ) {
    throw new CollabOpError(
      "invalid_branch",
      `${label} must be a local branch name`,
      `Use the short name of an existing local branch, not a remote ref.`,
    );
  }
  const ref = `refs/heads/${value}`;
  const checked = await repo.git(repo.worktreeRoot, ["check-ref-format", ref], signal);
  if (checked.code !== 0) {
    throw new CollabOpError(
      "invalid_branch",
      `${label} is not a valid local branch name`,
      `Use a Git branch name below refs/heads/.`,
    );
  }
  return { name: value, ref };
}

async function localBranchTip(
  repo: Repository,
  branch: { name: string; ref: string },
  label: string,
  signal?: AbortSignal,
): Promise<string> {
  const tip = await commitAt(repo, branch.ref, signal);
  if (tip === null) {
    throw new CollabOpError(
      "branch_unavailable",
      `${label} does not resolve to a local commit: ${branch.name}`,
      `Create the local branch and point it at a commit before adopting it.`,
      { branch: branch.name },
    );
  }
  return tip;
}

async function exactBaseSha(
  repo: Repository,
  value: unknown,
  signal?: AbortSignal,
): Promise<string> {
  if (typeof value !== "string" || !/^[0-9a-f]{40,64}$/.test(value)) {
    throw new CollabOpError(
      "invalid_base_sha",
      "base_sha must be a full lowercase Git object ID",
      "Pass the complete 40-64 character lowercase commit ID.",
    );
  }
  const resolved = await commitAt(repo, value, signal);
  if (resolved !== value) {
    throw new CollabOpError(
      "invalid_base_sha",
      "base_sha must resolve exactly to a commit",
      "Pass the complete object ID for an existing commit.",
    );
  }
  return value;
}

async function symbolicRefTarget(
  repo: Repository,
  ref: string,
  signal?: AbortSignal,
): Promise<string | null> {
  const result = await repo.git(repo.worktreeRoot, ["symbolic-ref", "--quiet", ref], signal);
  return result.code === 0 ? result.stdout.trim() : null;
}

async function taskPersistenceBranch(
  repo: Repository,
  task: TaskLayout,
  signal?: AbortSignal,
): Promise<{ name: string; ref: string }> {
  const target = await symbolicRefTarget(controlRepository(repo), task.persistenceRef, signal);
  if (target === null || !target.startsWith("refs/heads/") || target === "refs/heads/") {
    throw new CollabOpError(
      "task_state_invalid",
      `managed task ${task.taskId} is missing its persistence symbolic ref`,
      "Restore the task-owned persistence symbolic ref to an existing local branch before retrying.",
    );
  }
  return requireLocalBranch(
    controlRepository(repo),
    target.slice("refs/heads/".length),
    "persistence",
    signal,
  );
}

async function taskInventory(
  repo: Repository,
  task: TaskLayout,
  signal?: AbortSignal,
) {
  const orchestratePrefix = `refs/orchestrate/${task.taskId}`;
  const wavePrefix = `refs/heads/wave/${task.taskId}`;
  const stateRoot = path.join(repo.controlRoot, ".agent_state");
  const worktreeRoot = path.join(stateRoot, "worktrees");
  const [candidateRefs, candidateBranches, records, rootMetadata, stateMetadata, worktreeMetadata] =
    await Promise.all([
      refNames(repo, orchestratePrefix, signal),
      refNames(repo, wavePrefix, signal),
      worktreeRecords(repo, signal),
      pathMetadata(task.root),
      pathMetadata(stateRoot),
      pathMetadata(worktreeRoot),
    ]);
  const ownedRefs = candidateRefs.filter(
    (name) => name === orchestratePrefix || name.startsWith(`${orchestratePrefix}/`),
  );
  const ownedBranches = candidateBranches.filter(
    (name) => name === wavePrefix || name.startsWith(`${wavePrefix}/`),
  );
  const registeredUnderRoot = records.filter(
    (record) =>
      record.worktree === task.root ||
      record.worktree?.startsWith(`${task.root}${path.sep}`),
  );
  return {
    records,
    rootMetadata,
    stateMetadata,
    worktreeMetadata,
    ownedRefs,
    ownedBranches,
    registeredUnderRoot,
  };
}

async function removeEmptyDirectory(pathname: string): Promise<void> {
  try {
    const metadata = await pathMetadata(pathname);
    if (metadata === null || !metadata.isDirectory()) return;
    await rmdir(pathname);
  } catch {
    // Preserve foreign or concurrently-created contents.
  }
}

async function compensateAdoption(
  repo: Repository,
  task: TaskLayout,
  sourceSha: string,
  sourceWasCanonical: boolean,
  persistRef: string,
  persistTarget: string,
  baseSha: string,
  mayHaveWorktree: boolean,
  mayHaveBranch: boolean,
  mayHaveBase: boolean,
  mayHavePersistence: boolean,
  createdStateRoot: boolean,
  createdWorktreeRoot: boolean,
  createdTaskRoot: boolean,
): Promise<void> {
  const integrationRef = `refs/heads/${task.integrationBranch}`;
  let removedWorktree = false;

  if (mayHaveWorktree && !sourceWasCanonical) {
    try {
      const records = await worktreeRecords(repo);
      const record = records.find(
        (candidate) =>
          candidate.worktree === task.integrationPath &&
          candidate.branch === integrationRef &&
          candidate.HEAD === sourceSha,
      );
      if (record) {
        const removal = await repo.git(repo.worktreeRoot, [
          "worktree",
          "remove",
          task.integrationPath,
        ]);
        removedWorktree = removal.code === 0;
      }
    } catch {
      // Preserve the worktree when its identity is uncertain or Git refuses removal.
    }
  }

  if (removedWorktree) {
    await removeEmptyDirectory(task.integrationPath);
  }

  if (mayHaveBranch && !sourceWasCanonical) {
    try {
      const records = await worktreeRecords(repo);
      const branchTarget = await symbolicRefTarget(repo, integrationRef);
      const tip = await commitAt(repo, integrationRef);
      if (
        branchTarget === null &&
        tip === sourceSha &&
        !records.some((record) => record.branch === integrationRef)
      ) {
        await repo.git(repo.worktreeRoot, [
          "update-ref",
          "-d",
          integrationRef,
          sourceSha,
        ]);
      }
    } catch {
      // Preserve a branch if its current identity cannot be proven.
    }
  }

  if (mayHavePersistence) {
    try {
      if ((await symbolicRefTarget(repo, persistRef)) === persistTarget) {
        await repo.git(repo.worktreeRoot, ["symbolic-ref", "--delete", persistRef]);
      }
    } catch {
      // Preserve an interleaved or otherwise unverified ref.
    }
  }

  if (mayHaveBase) {
    try {
      const target = await symbolicRefTarget(repo, task.integrationBaseRef);
      if (target === null && (await commitAt(repo, task.integrationBaseRef)) === baseSha) {
        await repo.git(repo.worktreeRoot, [
          "update-ref",
          "-d",
          task.integrationBaseRef,
          baseSha,
        ]);
      }
    } catch {
      // Preserve an interleaved or otherwise unverified ref.
    }
  }

  if (!sourceWasCanonical) {
    if (createdTaskRoot) await removeEmptyDirectory(task.root);
    if (createdWorktreeRoot) {
      await removeEmptyDirectory(path.join(task.repo.controlRoot, ".agent_state", "worktrees"));
    }
    if (createdStateRoot) {
      await removeEmptyDirectory(path.join(task.repo.controlRoot, ".agent_state"));
    }
  }
}

async function integrationCreate(
  run: GitRunner,
  cwd: string,
  request: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<Record<string, unknown>> {
  const repo = await discoverRepository(run, cwd, signal);
  const taskId = requireIdentifier(request.task_id, "task id");
  const task = new TaskLayout(repo, taskId);
  const inventory = await taskInventory(repo, task, signal);
  const unsafeParent =
    (inventory.stateMetadata !== null && !inventory.stateMetadata.isDirectory()) ||
    (inventory.worktreeMetadata !== null && !inventory.worktreeMetadata.isDirectory());
  if (
    inventory.ownedRefs.length ||
    inventory.ownedBranches.length ||
    inventory.registeredUnderRoot.length ||
    inventory.rootMetadata !== null ||
    unsafeParent
  ) {
    throw new CollabOpError(
      "task_resource_collision",
      `managed resources already exist for task ${taskId}`,
    );
  }

  const symbolic = await repo.git(repo.worktreeRoot, ["symbolic-ref", "--quiet", "HEAD"], signal);
  const persistenceTarget = symbolic.code === 0 ? symbolic.stdout.trim() : "";
  if (!persistenceTarget.startsWith("refs/heads/")) {
    throw new CollabOpError(
      "detached_head",
      "integration creation requires HEAD attached to a local branch",
    );
  }
  const head = await commitAt(repo, "HEAD", signal);
  if (head === null) {
    throw new CollabOpError("git_error", "current HEAD does not resolve to a commit");
  }

  const warnings: string[] = [];
  const exclusionWarning = await ensureAgentStateIgnored(repo, signal);
  if (exclusionWarning) warnings.push(exclusionWarning);

  try {
    await mkdir(path.dirname(task.integrationPath), { recursive: true });
    await requireGit(
      repo.git,
      repo.worktreeRoot,
      ["worktree", "add", "-b", task.integrationBranch, task.integrationPath, head],
      signal,
    );
    await requireGit(
      repo.git,
      repo.worktreeRoot,
      ["update-ref", task.integrationBaseRef, head, "0".repeat(head.length)],
      signal,
    );
    await requireGit(
      repo.git,
      repo.worktreeRoot,
      ["symbolic-ref", task.persistenceRef, persistenceTarget],
      signal,
    );
  } catch (error) {
    const currentPersistence = await repo.git(
      repo.worktreeRoot,
      ["symbolic-ref", "--quiet", task.persistenceRef],
    );
    if (currentPersistence.code === 0 && currentPersistence.stdout.trim() === persistenceTarget) {
      await repo.git(repo.worktreeRoot, ["symbolic-ref", "--delete", task.persistenceRef]);
    }
    await repo.git(
      repo.worktreeRoot,
      ["update-ref", "-d", task.integrationBaseRef, head],
    );
    const removedWorktree = await repo.git(
      repo.worktreeRoot,
      ["worktree", "remove", task.integrationPath],
    );
    if (removedWorktree.code === 0) {
      await removeEmptyDirectory(task.integrationPath);
    }
    try {
      const integrationRef = `refs/heads/${task.integrationBranch}`;
      const records = await worktreeRecords(repo);
      if (
        !records.some((record) => record.branch === integrationRef) &&
        (await commitAt(repo, integrationRef)) === head
      ) {
        await repo.git(repo.worktreeRoot, ["update-ref", "-d", integrationRef, head]);
      }
    } catch {
      // Preserve a branch when its identity or registration is uncertain.
    }
    try {
      await rmdir(task.root);
    } catch {
      // Preserve any concurrently introduced or otherwise unknown inventory.
    }
    throw error;
  }

  const telemetryWarning = await recordEvent(task, "integration-create", "success", {
    subject_sha: head,
    persist: persistenceTarget.slice("refs/heads/".length),
  });
  if (telemetryWarning) warnings.push(telemetryWarning);
  return {
    ok: true,
    operation: "integration-create",
    tool_version: TOOL_VERSION,
    ...(warnings.length ? { warnings } : {}),
  };
}

async function integrationAdopt(
  run: GitRunner,
  cwd: string,
  request: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<Record<string, unknown>> {
  const repo = await discoverRepository(run, cwd, signal);
  const taskId = requireIdentifier(request.task_id, "task id");
  const task = new TaskLayout(repo, taskId);
  const sourceBranch = await requireLocalBranch(
    repo,
    request.source_branch,
    "source_branch",
    signal,
  );
  const persistBranch = await requireLocalBranch(repo, request.persist, "persist", signal);
  const baseSha = await exactBaseSha(repo, request.base_sha, signal);
  const sourceSha = await localBranchTip(repo, sourceBranch, "source_branch", signal);
  const persistSha = await localBranchTip(repo, persistBranch, "persist", signal);
  if (!(await isAncestor(repo, baseSha, sourceSha, signal))) {
    throw new CollabOpError(
      "base_not_ancestor",
      "base_sha is not an ancestor of source_branch",
      "Choose a base commit reachable from both local branch tips.",
      { base_sha: baseSha, source_sha: sourceSha },
    );
  }
  if (!(await isAncestor(repo, baseSha, persistSha, signal))) {
    throw new CollabOpError(
      "base_not_ancestor",
      "base_sha is not an ancestor of persist",
      "Choose a base commit reachable from both local branch tips.",
      { base_sha: baseSha, persist_sha: persistSha },
    );
  }

  const inventory = await taskInventory(repo, task, signal);
  const basePresent = inventory.ownedRefs.includes(task.integrationBaseRef);
  const persistencePresent = inventory.ownedRefs.includes(task.persistenceRef);
  const sourceWasCanonical = sourceBranch.name === task.integrationBranch;
  const integrationRef = `refs/heads/${task.integrationBranch}`;
  const persistTarget = persistBranch.ref;
  const allowedRefs = new Set([task.integrationBaseRef, task.persistenceRef]);

  if (!sourceWasCanonical) {
    if (
      inventory.ownedRefs.length > 0 ||
      inventory.ownedBranches.length > 0 ||
      inventory.registeredUnderRoot.length > 0 ||
      inventory.rootMetadata !== null ||
      (inventory.stateMetadata !== null && !inventory.stateMetadata.isDirectory()) ||
      (inventory.worktreeMetadata !== null && !inventory.worktreeMetadata.isDirectory())
    ) {
      throw new CollabOpError(
        "task_resource_collision",
        `managed resources already exist for task ${taskId}`,
      );
    }
  } else {
    const baseTarget = basePresent ? await commitAt(repo, task.integrationBaseRef, signal) : null;
    const baseSymbolic = basePresent
      ? await symbolicRefTarget(repo, task.integrationBaseRef)
      : null;
    const existingPersistenceTarget = persistencePresent
      ? await symbolicRefTarget(repo, task.persistenceRef)
      : null;
    const integrationMetadata = await pathMetadata(task.integrationPath);
    const rootEntries =
      inventory.rootMetadata?.isDirectory() ? await readdir(task.root) : null;
    const canonicalBranchRecords = inventory.records.filter(
      (record) => record.branch === integrationRef,
    );
    const exactCanonicalArrangement =
      inventory.ownedBranches.length === 1 &&
      inventory.ownedBranches[0] === integrationRef &&
      [...inventory.ownedRefs].every((name) => allowedRefs.has(name)) &&
      inventory.rootMetadata?.isDirectory() === true &&
      inventory.stateMetadata?.isDirectory() === true &&
      inventory.worktreeMetadata?.isDirectory() === true &&
      rootEntries?.length === 1 &&
      rootEntries[0] === path.basename(task.integrationPath) &&
      integrationMetadata?.isDirectory() === true &&
      canonicalBranchRecords.length === 1 &&
      canonicalBranchRecords[0].worktree === task.integrationPath &&
      canonicalBranchRecords[0].HEAD === sourceSha &&
      inventory.registeredUnderRoot.length === 1 &&
      inventory.registeredUnderRoot[0].worktree === task.integrationPath &&
      (!basePresent || (baseSymbolic === null && baseTarget === baseSha)) &&
      (!persistencePresent || existingPersistenceTarget === persistTarget);
    if (!exactCanonicalArrangement) {
      throw new CollabOpError(
        "task_resource_collision",
        `canonical integration arrangement for task ${taskId} is incomplete or colliding`,
      );
    }
    if (await hasTrackedDirt(repo, task.integrationPath, signal)) {
      throw new CollabOpError(
        "task_resource_collision",
        "canonical integration worktree is not clean",
        "Clean the canonical integration worktree before adopting it.",
      );
    }
  }


  const warnings: string[] = [];
  const exclusionWarning = await ensureAgentStateIgnored(repo, signal);
  if (exclusionWarning) warnings.push(exclusionWarning);

  const createdStateRoot = inventory.stateMetadata === null;
  const createdWorktreeRoot = inventory.worktreeMetadata === null;
  const createdTaskRoot = inventory.rootMetadata === null;
  let mayHaveWorktree = false;
  let mayHaveBranch = false;
  let mayHaveBase = false;
  let mayHavePersistence = false;
  try {
    if (!sourceWasCanonical) {
      await mkdir(path.dirname(task.integrationPath), { recursive: true });
      await requireGit(
        repo.git,
        repo.worktreeRoot,
        ["worktree", "add", "-b", task.integrationBranch, task.integrationPath, sourceSha],
        signal,
      );
      mayHaveWorktree = true;
      mayHaveBranch = true;
    }
    if (!basePresent) {
      await requireGit(
        repo.git,
        repo.worktreeRoot,
        ["update-ref", task.integrationBaseRef, baseSha, "0".repeat(baseSha.length)],
        signal,
      );
      mayHaveBase = true;
    }
    if (!persistencePresent) {
      await requireGit(
        repo.git,
        repo.worktreeRoot,
        ["symbolic-ref", task.persistenceRef, persistTarget],
        signal,
      );
      mayHavePersistence = true;
    }
  } catch (error) {
    try {
      await compensateAdoption(
        repo,
        task,
        sourceSha,
        sourceWasCanonical,
        task.persistenceRef,
        persistTarget,
        baseSha,
        mayHaveWorktree,
        mayHaveBranch,
        mayHaveBase,
        mayHavePersistence,
        createdStateRoot,
        createdWorktreeRoot,
        createdTaskRoot,
      );
    } catch {
      // Keep the original mutation error; compensation remains conservative.
    }
    throw error;
  }

  const telemetryWarning = await recordEvent(task, "integration-adopt", "success", {
    subject_sha: sourceSha,
    source_branch: sourceBranch.name,
    source_sha: sourceSha,
    integration_branch: task.integrationBranch,
    integration_sha: sourceSha,
    base_sha: baseSha,
    persist: persistBranch.name,
  });
  if (telemetryWarning) warnings.push(telemetryWarning);
  return {
    ok: true,
    operation: "integration-adopt",
    tool_version: TOOL_VERSION,
    source_branch: sourceBranch.name,
    source_sha: sourceSha,
    integration_branch: task.integrationBranch,
    integration_sha: sourceSha,
    base_sha: baseSha,
    ...(warnings.length ? { warnings } : {}),
  };
}

function isActualDirectory(
  metadata: Awaited<ReturnType<typeof pathMetadata>>,
): boolean {
  return metadata?.isDirectory() === true;
}

function mutationCwd(repo: Repository): string {
  return repo.controlRoot;
}

function controlRepository(repo: Repository): Repository {
  return { ...repo, worktreeRoot: repo.controlRoot };
}

export async function requireManagedIntegration(
  repo: Repository,
  task: TaskLayout,
  signal?: AbortSignal,
): Promise<{ tip: string; base: string; records: WorktreeRecord[] }> {
  const gitRepo = controlRepository(repo);
  const branchRef = `refs/heads/${task.integrationBranch}`;
  const tip = await commitAt(gitRepo, branchRef, signal);
  if (tip === null) {
    throw new CollabOpError("task_not_found", `managed task ${task.taskId} does not exist`);
  }
  const base = await commitAt(gitRepo, task.integrationBaseRef, signal);
  if (base === null) {
    throw new CollabOpError(
      "task_state_invalid",
      `managed integration for task ${task.taskId} is missing its base ref`,
    );
  }
  const [branchSymbolic, baseSymbolic, records, stateMetadata, worktreeMetadata, rootMetadata, integrationMetadata] =
    await Promise.all([
      symbolicRefTarget(gitRepo, branchRef, signal),
      symbolicRefTarget(gitRepo, task.integrationBaseRef, signal),
      worktreeRecords(gitRepo, signal),
      pathMetadata(path.join(repo.controlRoot, ".agent_state")),
      pathMetadata(path.join(repo.controlRoot, ".agent_state", "worktrees")),
      pathMetadata(task.root),
      pathMetadata(task.integrationPath),
    ]);
  const branchRecords = records.filter((record) => record.branch === branchRef);
  const integrationRecords = records.filter(
    (record) =>
      record.worktree === task.integrationPath ||
      record.worktree?.startsWith(`${task.integrationPath}${path.sep}`),
  );
  if (
    branchSymbolic !== null ||
    baseSymbolic !== null ||
    !isActualDirectory(stateMetadata) ||
    !isActualDirectory(worktreeMetadata) ||
    !isActualDirectory(rootMetadata) ||
    !isActualDirectory(integrationMetadata) ||
    branchRecords.length !== 1 ||
    integrationRecords.length !== 1 ||
    branchRecords[0].worktree !== task.integrationPath ||
    branchRecords[0].HEAD !== tip
  ) {
    throw new CollabOpError(
      "worktree_identity_mismatch",
      `managed integration identity for task ${task.taskId} does not match its canonical worktree`,
      "Restore the canonical integration branch, base ref, and worktree registration before retrying.",
    );
  }
  if (!(await isAncestor(gitRepo, base, tip, signal))) {
    throw new CollabOpError(
      "task_state_invalid",
      `managed integration base is not an ancestor of its branch tip for task ${task.taskId}`,
    );
  }
  return { tip, base, records };
}

export async function laneInventory(
  repo: Repository,
  task: TaskLayout,
  laneId: string,
  signal?: AbortSignal,
  worktreeRecordsInput?: readonly WorktreeRecord[],
) {
  const gitRepo = controlRepository(repo);
  const branchRef = `refs/heads/${task.laneBranch(laneId)}`;
  const branchParentRef = `refs/heads/wave/${task.taskId}`;
  const lanePath = task.lanePath(laneId);
  const lanesPath = path.dirname(lanePath);
  const stateRoot = path.join(repo.controlRoot, ".agent_state");
  const worktreeRoot = path.join(stateRoot, "worktrees");
  const [branchNamesRaw, branchParentNames] = await Promise.all([
    refNames(gitRepo, branchRef, signal),
    refNames(gitRepo, branchParentRef, signal),
  ]);
  const branchNames = branchNamesRaw.filter(
    (name) => name === branchRef || name.startsWith(`${branchRef}/`),
  );
  const [branchTip, branchSymbolicTarget, records, laneMetadata, lanesMetadata, stateMetadata, worktreeMetadata, rootMetadata] =
    await Promise.all([
      commitAt(gitRepo, branchRef, signal),
      symbolicRefTarget(gitRepo, branchRef, signal),
      worktreeRecordsInput
        ? Promise.resolve(worktreeRecordsInput as WorktreeRecord[])
        : worktreeRecords(gitRepo, signal),
      pathMetadata(lanePath),
      pathMetadata(lanesPath),
      pathMetadata(stateRoot),
      pathMetadata(worktreeRoot),
      pathMetadata(task.root),
    ]);
  const branchRecords = records.filter((record) => record.branch === branchRef);
  const pathRecords = records.filter((record) => record.worktree === lanePath);
  const pathDescendantRecords = records.filter(
    (record) =>
      record.worktree === lanePath ||
      record.worktree?.startsWith(`${lanePath}${path.sep}`),
  );
  const parentRecords = records.filter((record) => record.worktree === lanesPath);
  const pathCustodySafe = [stateMetadata, worktreeMetadata, rootMetadata, lanesMetadata].every(
    (metadata) => metadata === null || metadata.isDirectory(),
  );
  return {
    branchRef,
    branchParentRef,
    lanePath,
    lanesPath,
    branchNames,
    branchParentNames,
    branchTip,
    branchSymbolicTarget,
    records,
    branchRecords,
    pathRecords,
    pathDescendantRecords,
    parentRecords,
    laneMetadata,
    lanesMetadata,
    stateMetadata,
    worktreeMetadata,
    rootMetadata,
    pathCustodySafe,
  };
}

export type LaneInventory = Awaited<ReturnType<typeof laneInventory>>;

function requireLaneId(value: unknown): string {
  const laneId = requireIdentifier(value, "lane id");
  if (laneId === "integration") {
    throw new CollabOpError(
      "reserved_lane",
      "lane id integration is reserved for the managed integration",
      "Choose a lane id other than integration.",
    );
  }
  return laneId;
}

function laneCoreIsComplete(
  inventory: Awaited<ReturnType<typeof laneInventory>>,
): boolean {
  return (
    inventory.branchNames.length === 1 &&
    inventory.branchNames[0] === inventory.branchRef &&
    !inventory.branchParentNames.includes(inventory.branchParentRef) &&
    inventory.branchTip !== null &&
    inventory.branchSymbolicTarget === null &&
    inventory.laneMetadata !== null
  );
}

function requireLaneComment(value: unknown): string | undefined {
  if (value === undefined) return undefined;
  if (typeof value !== "string") {
    throw new CollabOpError(
      "invalid_comment",
      "comment must be a non-empty string when provided",
      "Use a trimmed comment of at most 500 Unicode characters without control characters.",
    );
  }
  if (/\p{Cc}/u.test(value)) {
    throw new CollabOpError(
      "invalid_comment",
      "comment must not contain Unicode control characters",
      "Remove control characters from the comment.",
    );
  }
  const comment = value.trim();
  if (comment.length === 0 || [...comment].length > 500) {
    throw new CollabOpError(
      "invalid_comment",
      "comment must be non-empty and at most 500 Unicode characters",
      "Pass a trimmed comment containing between 1 and 500 Unicode characters.",
    );
  }
  return comment;
}

function laneNamespaceCollision(
  inventory: Awaited<ReturnType<typeof laneInventory>>,
): boolean {
  return (
    inventory.branchNames.length > 0 ||
    inventory.branchParentNames.includes(inventory.branchParentRef) ||
    inventory.laneMetadata !== null ||
    (inventory.lanesMetadata !== null && !isActualDirectory(inventory.lanesMetadata)) ||
    inventory.pathDescendantRecords.length > 0 ||
    inventory.parentRecords.length > 0
  );
}

async function countUncollectedLanes(
  repo: Repository,
  task: TaskLayout,
  integrationTip: string,
  signal?: AbortSignal,
): Promise<number> {
  const branchPrefix = `refs/heads/wave/${task.taskId}/`;
  const gitRepo = controlRepository(repo);
  const branchNames = await refNames(gitRepo, branchPrefix, signal);
  const laneIds = new Set<string>();
  for (const name of branchNames) {
    const laneId = laneIdFromRef(name, branchPrefix);
    if (laneId) laneIds.add(laneId);
  }
  let count = 0;
  for (const laneId of [...laneIds].sort()) {
    const inventory = await laneInventory(repo, task, laneId, signal);
    if (inventory.branchTip === null) continue;
    if (await isAncestor(gitRepo, inventory.branchTip, integrationTip, signal)) continue;
    count += 1;
    if (count >= 9) break;
  }
  return count;
}

async function hasMergeOrConflictState(
  repo: Repository,
  worktree: string,
  signal?: AbortSignal,
): Promise<boolean> {
  if (await mergeHeadPresent(repo, worktree, signal)) return true;
  const unmerged = await repo.git(worktree, ["ls-files", "--unmerged"], signal);
  if (unmerged.code !== 0) {
    throw new CollabOpError(
      "git_error",
      `could not inspect conflict state: ${unmerged.stderr.trim() || unmerged.stdout.trim()}`,
    );
  }
  return unmerged.stdout.trim().length > 0;
}

async function mergeHeadPresent(
  repo: Repository,
  worktree: string,
  signal?: AbortSignal,
): Promise<boolean> {
  const result = await repo.git(
    worktree,
    ["rev-parse", "--verify", "--quiet", "MERGE_HEAD"],
    signal,
  );
  if (result.code === 0) return true;
  if (result.code === 1) return false;
  throw new CollabOpError(
    "git_error",
    `could not inspect merge state: ${result.stderr.trim() || result.stdout.trim()}`,
  );
}

async function collectConflictPaths(
  repo: Repository,
  worktree: string,
  signal?: AbortSignal,
): Promise<{ paths: string[]; truncated: boolean } | null> {
  const result = await repo.git(
    worktree,
    ["diff", "--name-only", "--diff-filter=U", "-z", "--"],
    signal,
  );
  if (result.code !== 0) return null;
  const rawPaths = result.stdout ? result.stdout.split("\0") : [];
  if (rawPaths.at(-1) === "") rawPaths.pop();
  if (
    rawPaths.some(
      (pathname) =>
        pathname.length === 0 ||
        pathname.length > 512 ||
        /[\u0000-\u001f\u007f]/u.test(pathname),
    )
  ) {
    return null;
  }
  const truncated = rawPaths.length > 32;
  return { paths: rawPaths.slice(0, 32), truncated };
}

function boundedGitText(value: string): string {
  const text = value.trim();
  return text.length > 512 ? `${text.slice(0, 512)}…` : text;
}

async function rollbackLaneReconcile(
  repo: Repository,
  task: TaskLayout,
  laneId: string,
  laneSha: string,
): Promise<Record<string, unknown>> {
  const evidence: Record<string, unknown> = {
    lane_sha_before: laneSha,
  };
  let mergeState: boolean | null = null;
  try {
    mergeState = await mergeHeadPresent(repo, task.lanePath(laneId));
    evidence.merge_state_before_rollback = mergeState;
  } catch (error) {
    evidence.merge_state_before_rollback = "unknown";
    evidence.merge_state_error = boundedGitText(error instanceof Error ? error.message : String(error));
  }
  if (mergeState === true) {
    try {
      const aborted = await repo.git(task.lanePath(laneId), ["merge", "--abort"]);
      evidence.merge_abort = aborted.code === 0;
      if (aborted.code !== 0) {
        evidence.merge_abort_error = boundedGitText(aborted.stderr || aborted.stdout);
      }
    } catch (error) {
      evidence.merge_abort = false;
      evidence.merge_abort_error = boundedGitText(error instanceof Error ? error.message : String(error));
    }
  }
  try {
    const current = await laneInventory(repo, task, laneId);
    const clean = !(await hasTrackedDirt(repo, current.lanePath));
    const conflicted = await hasMergeOrConflictState(repo, current.lanePath);
    const exact =
      current.branchTip === laneSha &&
      laneIsComplete(current) &&
      clean &&
      !conflicted;
    evidence.lane_sha_after = current.branchTip;
    evidence.clean = clean;
    evidence.merge_or_conflict = conflicted;
    evidence.restored = exact;
  } catch (error) {
    evidence.restored = false;
    evidence.rollback_check_error = boundedGitText(error instanceof Error ? error.message : String(error));
  }
  return evidence;
}

async function syncLaneWithIntegration(
  repo: Repository,
  task: TaskLayout,
  laneId: string,
  laneSha: string,
  integrationTip: string,
  signal?: AbortSignal,
): Promise<{
  state: "merged" | "conflicted";
  lane_sha?: string;
  conflict_paths?: string[];
  conflict_paths_truncated?: boolean;
}> {
  const mergeArgs = [
    "merge",
    "--no-ff",
    "-m",
    `Reconcile lane ${laneId} with integration`,
    integrationTip,
  ] as const;
  let mergeResult: GitResult;
  try {
    mergeResult = await repo.git(task.lanePath(laneId), mergeArgs, signal);
  } catch (error) {
    const rollback = await rollbackLaneReconcile(repo, task, laneId, laneSha);
    throw new CollabOpError(
      "git_error",
      error instanceof Error ? error.message : String(error),
      undefined,
      { lane_sha: laneSha, integration_sha: integrationTip, rollback },
    );
  }
  if (mergeResult.code !== 0) {
    let mergeState = false;
    try {
      mergeState = await mergeHeadPresent(repo, task.lanePath(laneId));
    } catch {
      // A failed state check is retained in the rollback evidence below.
    }
    if (!mergeState) {
      const rollback = await rollbackLaneReconcile(repo, task, laneId, laneSha);
      throw new CollabOpError(
        "git_error",
        `Git command failed: ${boundedGitText(mergeResult.stderr || mergeResult.stdout) || `exit ${mergeResult.code}`}`,
        undefined,
        { lane_sha: laneSha, integration_sha: integrationTip, rollback },
      );
    }
    let conflictInfo: { paths: string[]; truncated: boolean } | null = null;
    try {
      conflictInfo = await collectConflictPaths(repo, task.lanePath(laneId));
    } catch {
      // Omit paths when they cannot be safely inspected.
    }
    return {
      state: "conflicted",
      conflict_paths: conflictInfo?.paths ?? [],
      ...(conflictInfo?.truncated ? { conflict_paths_truncated: true } : {}),
    };
  }
  const mergedSha = await commitAt(
    controlRepository(repo),
    `refs/heads/${task.laneBranch(laneId)}`,
    signal,
  );
  if (mergedSha === null) {
    const rollback = await rollbackLaneReconcile(repo, task, laneId, laneSha);
    throw new CollabOpError(
      "git_error",
      "reconciliation merge did not produce a lane commit",
      undefined,
      { lane_sha: laneSha, integration_sha: integrationTip, rollback },
    );
  }
  return { state: "merged", lane_sha: mergedSha };
}

async function laneReconcile(
  run: GitRunner,
  cwd: string,
  request: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<Record<string, unknown>> {
  const repo = await discoverRepository(run, cwd, signal);
  const taskId = requireIdentifier(request.task_id, "task id");
  const laneId = requireLaneId(request.lane_id);
  const task = new TaskLayout(repo, taskId);
  const lane = await laneInventory(repo, task, laneId, signal);
  if (!laneCoreIsComplete(lane)) {
    throw new CollabOpError(
      "lane_inventory_incomplete",
      `managed lane ${taskId}/${laneId} inventory is incomplete`,
      "Restore the complete canonical lane branch and worktree before reconciling it.",
    );
  }
  if (!laneIsComplete(lane)) {
    throw new CollabOpError(
      "worktree_identity_mismatch",
      "lane worktree registration does not match its canonical branch and path",
      "Restore the canonical lane worktree registration before reconciling it.",
    );
  }
  const laneSha = lane.branchTip as string;
  if (await hasTrackedDirt(repo, lane.lanePath, signal)) {
    throw new CollabOpError(
      "dirty_worktree",
      "lane worktree is dirty",
      "Clean the lane worktree before reconciling integration.",
    );
  }
  if (await hasMergeOrConflictState(repo, lane.lanePath, signal)) {
    throw new CollabOpError(
      "dirty_worktree",
      "lane worktree has an active merge or conflict state",
      "Finish or abort the lane merge before reconciling integration.",
    );
  }

  const integration = await requireManagedIntegration(controlRepository(repo), task, signal);
  if (await isAncestor(controlRepository(repo), integration.tip, laneSha, signal)) {
    const warnings = ["lane already includes latest integration"];
    const telemetryWarning = await recordEvent(task, "lane-reconcile", "noop", {
      lane_id: laneId,
      state: "noop",
      lane_sha: laneSha,
      integration_sha: integration.tip,
    });
    if (telemetryWarning) warnings.push(telemetryWarning);
    return {
      ok: true,
      operation: "lane-reconcile",
      tool_version: TOOL_VERSION,
      state: "noop",
      lane_sha: laneSha,
      integration_sha: integration.tip,
      warnings,
    };
  }

  const synced = await syncLaneWithIntegration(
    repo,
    task,
    laneId,
    laneSha,
    integration.tip,
    signal,
  );
  if (synced.state === "conflicted") {
    const warnings = ["resolve the lane conflict, then commit it before collecting it"];
    const telemetryWarning = await recordEvent(task, "lane-reconcile", "success", {
      lane_id: laneId,
      state: "conflicted",
      lane_sha: laneSha,
      integration_sha: integration.tip,
      conflict_path_count: synced.conflict_paths?.length ?? 0,
    });
    if (telemetryWarning) warnings.push(telemetryWarning);
    return {
      ok: true,
      operation: "lane-reconcile",
      tool_version: TOOL_VERSION,
      state: "conflicted",
      lane_sha: laneSha,
      integration_sha: integration.tip,
      conflict_paths: synced.conflict_paths ?? [],
      ...(synced.conflict_paths_truncated ? { conflict_paths_truncated: true } : {}),
      warnings,
    };
  }
  const mergedSha = synced.lane_sha as string;
  const warnings: string[] = [];
  const telemetryWarning = await recordEvent(task, "lane-reconcile", "success", {
    lane_id: laneId,
    state: "merged",
    lane_sha: mergedSha,
    integration_sha: integration.tip,
  });
  if (telemetryWarning) warnings.push(telemetryWarning);
  return {
    ok: true,
    operation: "lane-reconcile",
    tool_version: TOOL_VERSION,
    state: "merged",
    lane_sha: mergedSha,
    integration_sha: integration.tip,
    ...(warnings.length ? { warnings } : {}),
  };
}

async function exactSha(
  repo: Repository,
  value: unknown,
  label: string,
  signal?: AbortSignal,
): Promise<string> {
  if (typeof value !== "string" || !/^[0-9a-f]{40,64}$/.test(value)) {
    throw new CollabOpError(
      "invalid_sha",
      `${label} must be a full lowercase Git object ID`,
      "Pass the complete 40-64 character lowercase commit ID.",
    );
  }
  const resolved = await commitAt(controlRepository(repo), value, signal);
  if (resolved !== value) {
    throw new CollabOpError(
      "invalid_sha",
      `${label} must resolve exactly to a commit`,
      "Pass the complete object ID for an existing commit.",
    );
  }
  return value;
}

async function retireLaneWorktree(
  repo: Repository,
  inventory: Awaited<ReturnType<typeof laneInventory>>,
  abandon: boolean,
): Promise<{ removed: boolean; warnings: string[] }> {
  const warnings: string[] = [];
  if (!inventory.pathCustodySafe) {
    warnings.push("lane path custody is unsafe; no path contents were removed");
    return { removed: false, warnings };
  }
  const exactRegistration =
    inventory.pathRecords.length === 1 &&
    inventory.pathRecords[0].branch === inventory.branchRef &&
    inventory.pathDescendantRecords.length === 1 &&
    inventory.parentRecords.length === 0;
  if (exactRegistration) {
    if (inventory.laneMetadata?.isSymbolicLink()) {
      try {
        await unlink(inventory.lanePath);
      } catch {
        warnings.push("canonical lane symlink could not be unlinked safely");
        return { removed: false, warnings };
      }
    }
    const result = await repo.git(mutationCwd(repo), [
      "worktree",
      "remove",
      "--force",
      inventory.lanePath,
    ]);
    if (result.code === 0) {
      await removeEmptyDirectory(inventory.lanePath);
      return { removed: true, warnings };
    }
    warnings.push(`lane worktree could not be removed: ${result.stderr.trim() || result.stdout.trim()}`);
    return { removed: false, warnings };
  }
  if (inventory.pathRecords.length > 0 || inventory.pathDescendantRecords.length > 0) {
    warnings.push("lane worktree registration is incomplete; its path was preserved");
    return { removed: false, warnings };
  }
  if (inventory.laneMetadata?.isSymbolicLink()) {
    try {
      await unlink(inventory.lanePath);
      return { removed: true, warnings };
    } catch {
      warnings.push("canonical lane symlink could not be unlinked safely");
      return { removed: false, warnings };
    }
  }
  if (isActualDirectory(inventory.laneMetadata)) {
    try {
      const entries = await readdir(inventory.lanePath);
      if (entries.length === 0) {
        await rmdir(inventory.lanePath);
        return { removed: true, warnings };
      }
    } catch {
      // Preserve unknown path contents.
    }
    warnings.push("canonical lane path contains unknown contents; it was preserved");
    return { removed: false, warnings };
  }
  if (inventory.laneMetadata !== null) {
    warnings.push("canonical lane path is not a removable directory or symlink");
  }
  if (!abandon) warnings.push("lane worktree is not registered at its canonical path");
  return { removed: false, warnings };
}

async function restoreLaneSnapshot(
  repo: Repository,
  task: TaskLayout,
  laneId: string,
  laneSha: string,
  removedBranch: boolean,
): Promise<void> {
  if (!removedBranch) return;
  const current = await laneInventory(repo, task, laneId);
  if (current.branchNames.length === 0 && current.branchTip === null) {
    await repo.git(mutationCwd(repo), [
      "update-ref",
      "--no-deref",
      current.branchRef,
      laneSha,
      "0".repeat(laneSha.length),
    ]);
  }
}

async function retireCollectedLane(
  repo: Repository,
  task: TaskLayout,
  laneId: string,
  expectedLaneSha: string,
): Promise<{ cleaned: boolean; warnings: string[] }> {
  const warnings: string[] = [];
  const inventory = await laneInventory(repo, task, laneId);
  if (!laneIsComplete(inventory) || inventory.branchTip !== expectedLaneSha) {
    warnings.push(`lane ${laneId} retained: identity no longer matches the collected subject`);
    return { cleaned: false, warnings };
  }
  if (await hasTrackedDirt(repo, inventory.lanePath)) {
    warnings.push(`lane ${laneId} retained: worktree has tracked changes`);
    return { cleaned: false, warnings };
  }
  if (await hasMergeOrConflictState(repo, inventory.lanePath)) {
    warnings.push(`lane ${laneId} retained: worktree has an active merge or conflict state`);
    return { cleaned: false, warnings };
  }
  const laneSha = inventory.branchTip as string;
  let removedBranch = false;
  try {
    await requireGit(
      repo.git,
      mutationCwd(repo),
      ["update-ref", "--no-deref", "-d", inventory.branchRef, laneSha],
    );
    removedBranch = true;
    const removed = await retireLaneWorktree(repo, inventory, false);
    if (!removed.removed) {
      try {
        await restoreLaneSnapshot(repo, task, laneId, laneSha, removedBranch);
      } catch (restoreError) {
        warnings.push(
          `lane ${laneId} branch restoration failed: ${boundedGitText(restoreError instanceof Error ? restoreError.message : String(restoreError))}`,
        );
      }
      warnings.push(`lane ${laneId} retained: ${removed.warnings[0] || "worktree could not be removed"}`);
      return { cleaned: false, warnings };
    }
    return { cleaned: true, warnings };
  } catch (error) {
    let restoration: unknown = null;
    try {
      restoration = await restoreLaneSnapshot(repo, task, laneId, laneSha, removedBranch);
    } catch (restoreError) {
      restoration = boundedGitText(restoreError instanceof Error ? restoreError.message : String(restoreError));
    }
    warnings.push(
      `lane ${laneId} retained after cleanup failure: ${boundedGitText(error instanceof Error ? error.message : String(error))}; restoration=${JSON.stringify(restoration)}`,
    );
    return { cleaned: false, warnings };
  }
}

async function laneCollect(
  run: GitRunner,
  cwd: string,
  request: Record<string, unknown>,
  signal?: AbortSignal,
  currentTips = false,
): Promise<Record<string, unknown>> {
  const repo = await discoverRepository(run, cwd, signal);
  const taskId = requireIdentifier(request.task_id, "task id");
  const laneId = requireLaneId(request.lane_id);
  const requestedSha = currentTips
    ? null
    : await exactSha(repo, request.sha, "sha", signal);
  const judgedIntegrationSha = currentTips
    ? null
    : await exactSha(
        repo,
        request.integration_sha,
        "integration_sha",
        signal,
      );
  const task = new TaskLayout(repo, taskId);
  const lane = await laneInventory(repo, task, laneId, signal);
  if (!laneCoreIsComplete(lane)) {
    throw new CollabOpError(
      "lane_inventory_incomplete",
      `managed lane ${taskId}/${laneId} inventory is incomplete`,
      "Restore the complete canonical lane branch and worktree before collecting it.",
    );
  }
  if (!laneIsComplete(lane)) {
    throw new CollabOpError(
      "worktree_identity_mismatch",
      "lane worktree registration does not match its canonical branch and path",
      "Restore the canonical lane worktree registration before collecting it.",
    );
  }
  const laneSha = lane.branchTip as string;
  if (!currentTips && laneSha !== requestedSha) {
    throw new CollabOpError(
      "lane_sha_mismatch",
      "supplied sha is not the exact current lane tip",
      "Collect the exact lane subject on which the Orchestrator judgement relies.",
      { lane_sha: laneSha, supplied_sha: requestedSha },
    );
  }
  if (await hasMergeOrConflictState(repo, lane.lanePath, signal)) {
    throw new CollabOpError(
      "dirty_worktree",
      "lane worktree has an active merge or conflict state",
      "Finish or abort the lane merge before collecting it.",
    );
  }

  const integration = await requireManagedIntegration(controlRepository(repo), task, signal);
  if (await hasTrackedDirt(repo, task.integrationPath, signal)) {
    throw new CollabOpError(
      "dirty_worktree",
      "integration worktree has tracked changes",
      "Commit or discard the tracked changes in the canonical integration worktree before collecting a lane.",
    );
  }
  if (await hasMergeOrConflictState(repo, task.integrationPath, signal)) {
    throw new CollabOpError(
      "dirty_worktree",
      "integration worktree has an active merge or conflict state",
      "Finish or abort the integration merge before collecting a lane.",
    );
  }

  // The judged comparison point must be the exact integration head the Orchestrator
  // judged against, and that head must be contained in the judged lane subject.
  // Any mismatch stops before collection mutation: a stale subject is
  // synchronized with current integration, and an unchanged subject whose
  // comparison point moved is returned for new review and Orchestrator judgement.
  const subjectContainsIntegration = await isAncestor(
    controlRepository(repo),
    integration.tip,
    laneSha,
    signal,
  );
  const comparisonMatches = currentTips || judgedIntegrationSha === integration.tip;

  if (!comparisonMatches && subjectContainsIntegration) {
    const warnings = [
      "judged integration_sha no longer equals current integration; review the unchanged lane subject against current integration before collecting",
    ];
    const telemetryWarning = await recordEvent(task, "lane-collect", "success", {
      lane_id: laneId,
      state: "comparison_moved",
      collected: false,
      lane_sha: laneSha,
      integration_sha: integration.tip,
      judged_integration_sha: judgedIntegrationSha,
    });
    if (telemetryWarning) warnings.push(telemetryWarning);
    return {
      ok: true,
      operation: "lane-collect",
      tool_version: TOOL_VERSION,
      state: "comparison_moved",
      collected: false,
      lane_sha: laneSha,
      integration_sha: integration.tip,
      judged_integration_sha: judgedIntegrationSha,
      warnings,
    };
  }

  // A stale subject: current integration is not contained in the judged lane tip.
  if (!subjectContainsIntegration) {
    if (await hasTrackedDirt(repo, lane.lanePath, signal)) {
      throw new CollabOpError(
        "dirty_worktree",
        "lane worktree has tracked changes",
        "Commit or discard the tracked changes in the lane worktree so it can be synchronized with current integration.",
      );
    }
    const synced = await syncLaneWithIntegration(
      repo,
      task,
      laneId,
      laneSha,
      integration.tip,
      signal,
    );
    if (synced.state === "conflicted") {
      const warnings = [
        "lane was stale; the integration merge conflicted — resolve it in the lane before collecting",
      ];
      const telemetryWarning = await recordEvent(task, "lane-collect", "success", {
        lane_id: laneId,
        state: "conflicted",
        collected: false,
        lane_sha: laneSha,
        integration_sha: integration.tip,
        judged_integration_sha: judgedIntegrationSha,
        conflict_path_count: synced.conflict_paths?.length ?? 0,
      });
      if (telemetryWarning) warnings.push(telemetryWarning);
      return {
        ok: true,
        operation: "lane-collect",
        tool_version: TOOL_VERSION,
        state: "conflicted",
        collected: false,
        lane_sha: laneSha,
        integration_sha: integration.tip,
        judged_integration_sha: judgedIntegrationSha,
        conflict_paths: synced.conflict_paths ?? [],
        ...(synced.conflict_paths_truncated ? { conflict_paths_truncated: true } : {}),
        warnings,
      };
    }
    const warnings = [
      "lane was stale; it was reconciled to a new exact subject that needs review and Orchestrator judgement before collection",
    ];
    const telemetryWarning = await recordEvent(task, "lane-collect", "success", {
      lane_id: laneId,
      state: "reconciled",
      collected: false,
      lane_sha: synced.lane_sha,
      integration_sha: integration.tip,
      judged_integration_sha: judgedIntegrationSha,
    });
    if (telemetryWarning) warnings.push(telemetryWarning);
    return {
      ok: true,
      operation: "lane-collect",
      tool_version: TOOL_VERSION,
      state: "reconciled",
      collected: false,
      lane_sha: synced.lane_sha as string,
      integration_sha: integration.tip,
      judged_integration_sha: judgedIntegrationSha,
      warnings,
    };
  }

  // Ready: compare-and-swap integration to the exact supplied subject without
  // creating another content-bearing commit, then keep the worktree consistent.
  if (await hasTrackedDirt(repo, lane.lanePath, signal)) {
    throw new CollabOpError(
      "dirty_worktree",
      "lane worktree has tracked changes",
      "Commit or discard the tracked changes in the lane worktree before collecting it.",
    );
  }
  const integrationRef = `refs/heads/${task.integrationBranch}`;
  const casResult = await repo.git(
    mutationCwd(repo),
    ["update-ref", integrationRef, laneSha, integration.tip],
    signal,
  );
  if (casResult.code !== 0) {
    throw new CollabOpError(
      "git_error",
      `could not advance integration to the collected subject: ${boundedGitText(casResult.stderr || casResult.stdout)}`,
      undefined,
      { integration_sha: integration.tip, lane_sha: laneSha },
    );
  }
  const reset = await repo.git(task.integrationPath, ["reset", "--hard", laneSha], signal);
  if (reset.code !== 0) {
    try {
      await repo.git(mutationCwd(repo), ["update-ref", integrationRef, integration.tip, laneSha]);
    } catch {
      // Preserve the explicit Git inventory as evidence of the interrupted mutation.
    }
    throw new CollabOpError(
      "git_error",
      `could not synchronize the integration worktree: ${boundedGitText(reset.stderr || reset.stdout)}`,
      undefined,
      { integration_sha: integration.tip, lane_sha: laneSha },
    );
  }
  const after = await commitAt(controlRepository(repo), integrationRef, signal);
  if (after !== laneSha) {
    try {
      await repo.git(mutationCwd(repo), ["update-ref", integrationRef, integration.tip, after ?? (await zeroOidFor(repo, signal))]);
      await repo.git(task.integrationPath, ["reset", "--hard", integration.tip]);
    } catch {
      // Preserve the explicit Git inventory as evidence of the interrupted mutation.
    }
    throw new CollabOpError(
      "git_error",
      "integration did not advance to the exact collected subject",
      undefined,
      { integration_sha: integration.tip, lane_sha: laneSha },
    );
  }

  const cleanup = await retireCollectedLane(repo, task, laneId, laneSha);
  const warnings: string[] = [...cleanup.warnings];
  const telemetryWarning = await recordEvent(task, "lane-collect", "success", {
    lane_id: laneId,
    state: "collected",
    lane_sha: laneSha,
    integration_sha: laneSha,
    judged_integration_sha: judgedIntegrationSha,
    cleanup_cleaned: cleanup.cleaned,
  });
  if (telemetryWarning) warnings.push(telemetryWarning);
  return {
    ok: true,
    operation: "lane-collect",
    tool_version: TOOL_VERSION,
    state: "collected",
    lane_sha: laneSha,
    integration_sha: laneSha,
    judged_integration_sha: judgedIntegrationSha,
    cleanup: { cleaned: cleanup.cleaned },
    ...(warnings.length ? { warnings } : {}),
  };
}

async function compensateCreatedLane(
  repo: Repository,
  task: TaskLayout,
  laneId: string,
  tip: string,
  mayHaveWorktree: boolean,
  mayHaveBranch: boolean,
  createdLanesPath: boolean,
): Promise<void> {
  const inventory = await laneInventory(repo, task, laneId);
  if (
    mayHaveWorktree &&
    inventory.pathRecords.length === 1 &&
    inventory.pathRecords[0].branch === inventory.branchRef &&
    inventory.pathRecords[0].HEAD === tip &&
    inventory.pathDescendantRecords.length === 1 &&
    inventory.pathCustodySafe &&
    isActualDirectory(inventory.laneMetadata)
  ) {
    const removed = await repo.git(mutationCwd(repo), [
      "worktree",
      "remove",
      inventory.lanePath,
    ]);
    if (removed.code === 0) {
      await removeEmptyDirectory(inventory.lanePath);
    }
  }
  if (mayHaveBranch) {
    const current = await laneInventory(repo, task, laneId);
    if (
      current.branchNames.length === 1 &&
      current.branchNames[0] === current.branchRef &&
      current.branchSymbolicTarget === null &&
      current.branchTip === tip &&
      current.branchRecords.length === 0
    ) {
      await repo.git(mutationCwd(repo), [
        "update-ref",
        "--no-deref",
        "-d",
        current.branchRef,
        tip,
      ]);
    }
  }
  if (createdLanesPath) {
    await removeEmptyDirectory(path.dirname(task.lanePath(laneId)));
  }
}

async function createLaneResources(
  repo: Repository,
  task: TaskLayout,
  laneId: string,
  integrationTip: string,
  lane: Awaited<ReturnType<typeof laneInventory>>,
  signal?: AbortSignal,
): Promise<{ createdLanesPath: boolean }> {
  if (laneNamespaceCollision(lane)) {
    throw new CollabOpError(
      "lane_resource_collision",
      `managed lane resources already exist for ${task.taskId}/${laneId}`,
    );
  }
  const createdLanesPath = lane.lanesMetadata === null;
  let mayHaveWorktree = false;
  let mayHaveBranch = false;
  try {
    await mkdir(lane.lanesPath, { recursive: true });
    await requireGit(
      repo.git,
      mutationCwd(repo),
      ["worktree", "add", "-b", task.laneBranch(laneId), lane.lanePath, integrationTip],
      signal,
    );
    mayHaveWorktree = true;
    mayHaveBranch = true;
  } catch (error) {
    try {
      await compensateCreatedLane(
        repo,
        task,
        laneId,
        integrationTip,
        mayHaveWorktree,
        mayHaveBranch,
        createdLanesPath,
      );
    } catch {
      // Preserve the original failure and any state whose identity is uncertain.
    }
    throw error;
  }
  return { createdLanesPath };
}

async function laneCreate(
  run: GitRunner,
  cwd: string,
  request: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<Record<string, unknown>> {
  const repo = await discoverRepository(run, cwd, signal);
  const taskId = requireIdentifier(request.task_id, "task id");
  const laneId = requireLaneId(request.lane_id);
  const comment = requireLaneComment(request.comment);
  const task = new TaskLayout(repo, taskId);
  const integration = await requireManagedIntegration(repo, task, signal);
  const lane = await laneInventory(repo, task, laneId, signal);
  if (laneNamespaceCollision(lane)) {
    throw new CollabOpError(
      "lane_resource_collision",
      `managed lane resources already exist for ${taskId}/${laneId}`,
    );
  }
  const uncollectedLanes = await countUncollectedLanes(
    repo,
    task,
    integration.tip,
    signal,
  );
  await createLaneResources(repo, task, laneId, integration.tip, lane, signal);

  const warnings: string[] = [];
  if (uncollectedLanes >= 9) {
    warnings.push("9 or more lanes have uncollected work; collect or drop them before adding more lanes");
  }
  const telemetryWarning = await recordEvent(task, "lane-create", "success", {
    lane_id: laneId,
    lane_sha: integration.tip,
    integration_sha: integration.tip,
    ...(comment === undefined ? {} : { comment }),
    ...(uncollectedLanes >= 9 ? { uncollected_lanes: uncollectedLanes } : {}),
  });
  if (telemetryWarning) warnings.push(telemetryWarning);
  return {
    ok: true,
    operation: "lane-create",
    tool_version: TOOL_VERSION,
    ...(warnings.length ? { warnings } : {}),
  };
}

async function requirePersistenceCheckout(
  repo: Repository,
  task: TaskLayout,
  persistBranch: { name: string; ref: string },
  signal?: AbortSignal,
): Promise<{ tip: string; record: WorktreeRecord }> {
  const gitRepo = controlRepository(repo);
  const persistenceTarget = await symbolicRefTarget(gitRepo, task.persistenceRef, signal);
  if (persistenceTarget === null) {
    throw new CollabOpError(
      "task_state_invalid",
      `managed task ${task.taskId} is missing its persistence symbolic ref`,
    );
  }
  if (persistenceTarget !== persistBranch.ref) {
    throw new CollabOpError(
      "persistence_mismatch",
      `persist must match the task-owned persistence branch for ${task.taskId}`,
      `Use ${persistenceTarget.slice("refs/heads/".length)} for persist.`,
      { requested: persistBranch.name, recorded: persistenceTarget },
    );
  }
  if ((await symbolicRefTarget(gitRepo, persistBranch.ref, signal)) !== null) {
    throw new CollabOpError(
      "persistence_identity_mismatch",
      `persistence branch ${persistBranch.name} is not a direct local branch`,
    );
  }
  const tip = await localBranchTip(gitRepo, persistBranch, "persist", signal);
  const records = await worktreeRecords(gitRepo, signal);
  const matches = records.filter((record) => record.branch === persistBranch.ref);
  if (
    matches.length !== 1 ||
    matches[0].worktree === undefined ||
    matches[0].HEAD !== tip ||
    !isActualDirectory(await pathMetadata(matches[0].worktree))
  ) {
    throw new CollabOpError(
      "persistence_identity_mismatch",
      `persistence branch ${persistBranch.name} must have exactly one checkout at its tip`,
      "Restore one registered persistence checkout whose HEAD matches the branch tip.",
      {
        branch: persistBranch.name,
        tip,
        checkout_count: matches.length,
        checkout_heads: matches.map((record) => record.HEAD ?? null),
      },
    );
  }
  return { tip, record: matches[0] };
}

async function compensateReconcileLane(
  repo: Repository,
  task: TaskLayout,
  laneId: string,
  integrationTip: string,
  createdLanesPath: boolean,
): Promise<Record<string, unknown>> {
  const evidence: Record<string, unknown> = {};
  let mergeState: boolean | null = null;
  try {
    mergeState = await mergeHeadPresent(repo, task.lanePath(laneId));
    evidence.merge_state_before_compensation = mergeState;
  } catch (error) {
    evidence.merge_state_before_compensation = "unknown";
    evidence.merge_state_error = boundedGitText(error instanceof Error ? error.message : String(error));
  }
  if (mergeState === true) {
    try {
      const aborted = await repo.git(task.lanePath(laneId), ["merge", "--abort"]);
      evidence.merge_abort = aborted.code === 0;
      if (aborted.code !== 0) {
        evidence.merge_abort_error = boundedGitText(aborted.stderr || aborted.stdout);
      }
    } catch (error) {
      evidence.merge_abort = false;
      evidence.merge_abort_error = boundedGitText(error instanceof Error ? error.message : String(error));
    }
  }
  try {
    await compensateCreatedLane(
      repo,
      task,
      laneId,
      integrationTip,
      true,
      true,
      createdLanesPath,
    );
  } catch (error) {
    evidence.compensation_error = boundedGitText(error instanceof Error ? error.message : String(error));
  }
  try {
    const remaining = await laneInventory(repo, task, laneId);
    evidence.remaining_branch_refs = remaining.branchNames.slice(0, 32);
    evidence.remaining_worktree_records = remaining.pathDescendantRecords.length;
    evidence.restored =
      remaining.branchNames.length === 0 &&
      remaining.pathDescendantRecords.length === 0 &&
      remaining.laneMetadata === null;
  } catch (error) {
    evidence.restored = false;
    evidence.remaining_inventory_error = boundedGitText(error instanceof Error ? error.message : String(error));
  }
  return evidence;
}

async function integrationReconcile(
  run: GitRunner,
  cwd: string,
  request: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<Record<string, unknown>> {
  const repo = await discoverRepository(run, cwd, signal);
  const taskId = requireIdentifier(request.task_id, "task id");
  const laneId = requireLaneId(request.lane_id);
  const task = new TaskLayout(repo, taskId);
  const persistBranch = await taskPersistenceBranch(repo, task, signal);
  const integration = await requireManagedIntegration(controlRepository(repo), task, signal);
  if (await hasTrackedDirt(repo, task.integrationPath, signal)) {
    throw new CollabOpError(
      "dirty_worktree",
      "integration worktree is dirty",
      "Clean the canonical integration worktree before reconciling persistence.",
    );
  }
  if (await hasMergeOrConflictState(repo, task.integrationPath, signal)) {
    throw new CollabOpError(
      "dirty_worktree",
      "integration worktree has an active merge or conflict state",
      "Finish or abort the integration merge before reconciling persistence.",
    );
  }
  const persistence = await requirePersistenceCheckout(repo, task, persistBranch, signal);
  const telemetryFields = {
    lane_id: laneId,
    persist: persistBranch.name,
    integration_sha: integration.tip,
    persistence_sha: persistence.tip,
  };
  if (await isAncestor(controlRepository(repo), persistence.tip, integration.tip, signal)) {
    const warnings = ["persistence is already included in integration"];
    const telemetryWarning = await recordEvent(task, "integration-reconcile", "noop", {
      ...telemetryFields,
      state: "noop",
    });
    if (telemetryWarning) warnings.push(telemetryWarning);
    return {
      ok: true,
      operation: "integration-reconcile",
      tool_version: TOOL_VERSION,
      state: "noop",
      integration_sha: integration.tip,
      persistence_sha: persistence.tip,
      warnings,
    };
  }

  const lane = await laneInventory(repo, task, laneId, signal);
  const created = await createLaneResources(repo, task, laneId, integration.tip, lane, signal);
  let mergeResult: GitResult;
  try {
    mergeResult = await repo.git(
      task.lanePath(laneId),
      ["merge", "--no-ff", "-m", `Reconcile persistence into lane ${laneId}`, persistence.tip],
      signal,
    );
  } catch (error) {
    const compensation = await compensateReconcileLane(
      repo,
      task,
      laneId,
      integration.tip,
      created.createdLanesPath,
    );
    throw new CollabOpError(
      "git_error",
      error instanceof Error ? error.message : String(error),
      undefined,
      {
        lane_id: laneId,
        integration_sha: integration.tip,
        persistence_sha: persistence.tip,
        compensation,
      },
    );
  }

  if (mergeResult.code !== 0) {
    let mergeState = false;
    try {
      mergeState = await mergeHeadPresent(repo, task.lanePath(laneId));
    } catch {
      // A failed merge-state check is retained in the compensation evidence.
    }
    if (mergeState) {
      let conflictInfo: { paths: string[]; truncated: boolean } | null = null;
      try {
        conflictInfo = await collectConflictPaths(repo, task.lanePath(laneId));
      } catch {
        // Omit paths when they cannot be safely inspected.
      }
      const warnings = ["resolve the lane conflict, then commit it before collecting the lane"];
      const telemetryWarning = await recordEvent(task, "integration-reconcile", "success", {
        ...telemetryFields,
        state: "conflicted",
        lane_sha: integration.tip,
        conflict_path_count: conflictInfo?.paths.length ?? 0,
      });
      if (telemetryWarning) warnings.push(telemetryWarning);
      return {
        ok: true,
        operation: "integration-reconcile",
        tool_version: TOOL_VERSION,
        state: "conflicted",
        lane_id: laneId,
        lane_sha: integration.tip,
        integration_sha: integration.tip,
        persistence_sha: persistence.tip,
        conflict_paths: conflictInfo?.paths ?? [],
        ...(conflictInfo?.truncated ? { conflict_paths_truncated: true } : {}),
        warnings,
      };
    }
    const compensation = await compensateReconcileLane(
      repo,
      task,
      laneId,
      integration.tip,
      created.createdLanesPath,
    );
    throw new CollabOpError(
      "git_error",
      `Git command failed: ${boundedGitText(mergeResult.stderr || mergeResult.stdout) || `exit ${mergeResult.code}`}`,
      undefined,
      {
        lane_id: laneId,
        integration_sha: integration.tip,
        persistence_sha: persistence.tip,
        compensation,
      },
    );
  }

  const laneSha = await commitAt(
    controlRepository(repo),
    `refs/heads/${task.laneBranch(laneId)}`,
    signal,
  );
  if (laneSha === null) {
    const compensation = await compensateReconcileLane(
      repo,
      task,
      laneId,
      integration.tip,
      created.createdLanesPath,
    );
    throw new CollabOpError(
      "git_error",
      "reconciliation merge did not produce a lane commit",
      undefined,
      {
        lane_id: laneId,
        integration_sha: integration.tip,
        persistence_sha: persistence.tip,
        compensation,
      },
    );
  }
  const warnings: string[] = [];
  const telemetryWarning = await recordEvent(task, "integration-reconcile", "success", {
    ...telemetryFields,
    state: "merged",
    lane_sha: laneSha,
  });
  if (telemetryWarning) warnings.push(telemetryWarning);
  return {
    ok: true,
    operation: "integration-reconcile",
    tool_version: TOOL_VERSION,
    state: "merged",
    lane_id: laneId,
    lane_sha: laneSha,
    integration_sha: integration.tip,
    persistence_sha: persistence.tip,
    ...(warnings.length ? { warnings } : {}),
  };
}

async function treeAt(
  repo: Repository,
  sha: string,
  signal?: AbortSignal,
): Promise<string> {
  const result = await repo.git(
    controlRepository(repo).worktreeRoot,
    ["rev-parse", "--verify", "--quiet", `${sha}^{tree}`],
    signal,
  );
  const tree = result.stdout.trim();
  if (result.code !== 0 || !/^[0-9a-f]{40,64}$/.test(tree)) {
    throw new CollabOpError(
      "git_error",
      `could not resolve commit tree: ${result.stderr.trim() || result.stdout.trim()}`,
    );
  }
  return tree;
}

export function laneIsComplete(
  inventory: Awaited<ReturnType<typeof laneInventory>>,
): boolean {
  return (
    inventory.branchNames.length === 1 &&
    inventory.branchNames[0] === inventory.branchRef &&
    !inventory.branchParentNames.includes(inventory.branchParentRef) &&
    inventory.branchTip !== null &&
    inventory.branchSymbolicTarget === null &&
    isActualDirectory(inventory.laneMetadata) &&
    isActualDirectory(inventory.lanesMetadata) &&
    isActualDirectory(inventory.rootMetadata) &&
    inventory.pathCustodySafe &&
    inventory.branchRecords.length === 1 &&
    inventory.pathRecords.length === 1 &&
    inventory.pathDescendantRecords.length === 1 &&
    inventory.parentRecords.length === 0 &&
    inventory.branchRecords[0].worktree === inventory.lanePath &&
    inventory.branchRecords[0].HEAD === inventory.branchTip &&
    inventory.pathRecords[0].branch === inventory.branchRef
  );
}

async function laneAbandon(
  repo: Repository,
  task: TaskLayout,
  laneId: string,
  inventory: Awaited<ReturnType<typeof laneInventory>>,
  signal?: AbortSignal,
): Promise<Record<string, unknown>> {
  const warnings: string[] = [];
  let incomplete = false;
  const branchRecognizable =
    inventory.branchNames.length === 1 &&
    inventory.branchNames[0] === inventory.branchRef &&
    !inventory.branchParentNames.includes(inventory.branchParentRef);
  const exactRegistration =
    inventory.pathRecords.length === 1 &&
    inventory.pathRecords[0].branch === inventory.branchRef &&
    inventory.pathDescendantRecords.length === 1 &&
    inventory.parentRecords.length === 0;
  if (!branchRecognizable || !laneIsComplete(inventory)) {
    incomplete = true;
  }

  let dirty = false;
  let conflicted = false;
  if (
    inventory.pathCustodySafe &&
    exactRegistration &&
    isActualDirectory(inventory.laneMetadata)
  ) {
    try {
      dirty = await hasTrackedDirt(repo, inventory.lanePath, signal);
      conflicted = await hasMergeOrConflictState(repo, inventory.lanePath, signal);
    } catch {
      incomplete = true;
    }
  } else if (inventory.laneMetadata !== null || inventory.pathRecords.length > 0) {
    incomplete = true;
  }

  let uncollected = false;
  const integrationTip = await commitAt(
    controlRepository(repo),
    `refs/heads/${task.integrationBranch}`,
    signal,
  );
  if (inventory.branchTip !== null && integrationTip !== null) {
    if (
      !(await isAncestor(controlRepository(repo), inventory.branchTip, integrationTip, signal))
    ) {
      uncollected = true;
    }
  } else {
    incomplete = true;
  }

  const recognizable =
    branchRecognizable ||
    (inventory.pathCustodySafe &&
      (exactRegistration || inventory.laneMetadata !== null));
  if (!recognizable) {
    throw new CollabOpError(
      "lane_inventory_incomplete",
      `managed lane ${task.taskId}/${laneId} has no safely recognizable canonical resources`,
    );
  }

  const pathResult = await retireLaneWorktree(repo, inventory, true);
  warnings.push(...pathResult.warnings);
  if (
    !pathResult.removed &&
    (inventory.laneMetadata !== null || inventory.pathRecords.length > 0)
  ) {
    incomplete = true;
  }
  const afterPath = await laneInventory(repo, task, laneId, signal);
  if (branchRecognizable && !afterPath.records.some((record) => record.branch === inventory.branchRef)) {
    const result = await repo.git(mutationCwd(repo), [
      "update-ref",
      "--no-deref",
      "-d",
      inventory.branchRef,
      ...(inventory.branchTip === null ? [] : [inventory.branchTip]),
    ], signal);
    if (result.code !== 0) {
      incomplete = true;
      warnings.push(`lane branch could not be removed: ${result.stderr.trim() || result.stdout.trim()}`);
    }
  } else if (branchRecognizable) {
    incomplete = true;
    warnings.push("lane branch remains because a worktree registration could not be safely retired");
  }
  if (dirty || conflicted) warnings.push("discarded dirty or conflicted lane worktree");
  if (uncollected) warnings.push("discarded uncollected lane commits");
  if (incomplete) warnings.push("lane inventory was incomplete; only safely recognized resources were removed");

  const telemetryFields: Record<string, unknown> = {
    lane_id: laneId,
    disposition: "abandoned",
    dirty,
    conflicted,
    uncollected,
    incomplete,
  };
  if (inventory.branchTip !== null) telemetryFields.lane_sha = inventory.branchTip;
  const telemetryWarning = await recordEvent(task, "lane-drop", "success", telemetryFields);
  if (telemetryWarning) warnings.push(telemetryWarning);
  return {
    ok: true,
    operation: "lane-drop",
    tool_version: TOOL_VERSION,
    ...(inventory.branchTip === null ? {} : { lane_sha: inventory.branchTip }),
    disposition: "abandoned",
    ...(warnings.length ? { warnings } : {}),
  };
}

function laneIdFromRef(name: string, prefix: string, suffix = ""): string | null {
  if (!name.startsWith(prefix) || (suffix && !name.endsWith(suffix))) return null;
  const end = suffix ? -suffix.length : undefined;
  const laneId = name.slice(prefix.length, end);
  return laneId !== "integration" && IDENTIFIER.test(laneId) ? laneId : null;
}

async function directAuthority(
  repo: Repository,
  ref: string,
  label: string,
  signal?: AbortSignal,
): Promise<string | null> {
  const names = await refNames(controlRepository(repo), ref, signal);
  if (names.length > 1 || (names.length === 1 && names[0] !== ref)) {
    throw new CollabOpError(
      "managed_ref_invalid",
      `${label} ref has a colliding descendant`,
    );
  }
  const symbolic = await symbolicRefTarget(controlRepository(repo), ref, signal);
  if (symbolic !== null) {
    throw new CollabOpError(
      "managed_ref_invalid",
      `${label} ref must be a direct ref`,
    );
  }
  if (names.length === 0) return null;
  const value = await commitAt(controlRepository(repo), ref, signal);
  if (value === null) {
    throw new CollabOpError(
      "managed_ref_invalid",
      `${label} ref does not resolve to a commit`,
    );
  }
  return value;
}

async function nulPathList(
  repo: Repository,
  cwd: string,
  args: readonly string[],
  signal?: AbortSignal,
): Promise<string[]> {
  const result = await repo.git(cwd, args, signal);
  if (result.code !== 0) {
    throw new CollabOpError(
      "git_error",
      `could not inspect landing paths: ${result.stderr.trim() || result.stdout.trim()}`,
    );
  }
  return result.stdout ? result.stdout.split("\0").filter(Boolean) : [];
}

function pathOverlaps(left: string, right: string): boolean {
  return (
    left === right ||
    left.startsWith(`${right}${path.posix.sep}`) ||
    right.startsWith(`${left}${path.posix.sep}`)
  );
}

// Refuse ordinary untracked paths only when the accepted transition itself
// would overwrite them, matching git merge --squash treatment of D/F overlaps.
// Writing a file at a changed path clobbers dirt at that path and any
// directory standing where the file must land. A baseline tracked leaf that
// was locally replaced by a directory is also a D/F obstruction when the
// transition changes or deletes that leaf; deleting tracked paths beneath a
// real baseline directory still leaves unrelated untracked siblings in place.
function transitionOverwrites(
  dirty: string,
  changed: string,
  baselinePaths: ReadonlySet<string>,
  writtenPaths: ReadonlySet<string>,
): boolean {
  if (!pathOverlaps(dirty, changed)) return false;
  if (dirty === changed) return true;
  if (dirty.startsWith(`${changed}/`) && baselinePaths.has(changed)) return true;
  return writtenPaths.has(changed);
}

// The index is clean only when every cached entry matches HEAD exactly.
// `git diff --cached --quiet` misses intent-to-add entries — their cached
// blob is the empty blob for paths HEAD does not have — so compare the full
// cached index, including unmerged stages, against the HEAD tree instead.
async function persistenceIndexClean(
  repo: Repository,
  worktree: string,
  signal?: AbortSignal,
): Promise<boolean> {
  const head = await repo.git(worktree, ["ls-tree", "-r", "-z", "HEAD"], signal);
  if (head.code !== 0) {
    throw new CollabOpError(
      "git_error",
      `could not inspect persistence index: ${head.stderr.trim() || head.stdout.trim()}`,
    );
  }
  const index = await repo.git(
    worktree,
    ["ls-files", "--cached", "--stage", "-z"],
    signal,
  );
  if (index.code !== 0) {
    throw new CollabOpError(
      "git_error",
      `could not inspect persistence index: ${index.stderr.trim() || index.stdout.trim()}`,
    );
  }
  const headEntries = new Set<string>();
  for (const entry of head.stdout.split("\0").filter(Boolean)) {
    const tab = entry.indexOf("\t");
    const [mode, , object] = entry.slice(0, tab).split(" ");
    headEntries.add(`${mode} ${object} ${entry.slice(tab + 1)}`);
  }
  let cachedEntries = 0;
  for (const entry of index.stdout.split("\0").filter(Boolean)) {
    const tab = entry.indexOf("\t");
    const [mode, object, stage] = entry.slice(0, tab).split(" ");
    // Unmerged stages are a non-HEAD index state.
    if (stage !== "0") return false;
    cachedEntries += 1;
    // Staged additions, modifications, mode changes, and intent-to-add
    // entries all diverge from HEAD here; staged deletions shrink the set.
    if (!headEntries.has(`${mode} ${object} ${entry.slice(tab + 1)}`)) return false;
  }
  return cachedEntries === headEntries.size;
}

function requireLandingMessage(value: unknown, taskId: string): string {
  if (value === undefined) return `Land ${taskId}`;
  if (
    typeof value !== "string" ||
    value.length === 0 ||
    value.length > 200 ||
    /[\u0000-\u001f\u007f]/u.test(value)
  ) {
    throw new CollabOpError(
      "invalid_message",
      "message must be a non-empty subject without control characters",
      "Pass a single-line landing subject of at most 200 characters.",
    );
  }
  return value;
}

async function landingMessageMatches(
  repo: Repository,
  sha: string,
  subject: string,
  taskId: string,
  integrationSha: string,
): Promise<boolean> {
  const message = await requireGit(
    repo.git,
    controlRepository(repo).worktreeRoot,
    ["show", "-s", "--format=%B", sha],
  );
  const expected = `${subject}\n\nTask: ${taskId}\nLanded: ${integrationSha}`;
  const actual = message.endsWith("\n\n")
    ? message.slice(0, -2)
    : message.endsWith("\n")
      ? message.slice(0, -1)
      : message;
  return actual === expected;
}

type LandingPreflight = {
  oursTree: string;
  mergedTree: string;
};

type LandingWorktreeSnapshot = {
  root: string;
  paths: string[];
};

async function copyLandingPath(
  sourceRoot: string,
  destinationRoot: string,
  pathname: string,
): Promise<void> {
  const source = path.join(sourceRoot, ...pathname.split("/"));
  const destination = path.join(destinationRoot, ...pathname.split("/"));
  const metadata = await pathMetadata(source);
  await rm(destination, { recursive: true, force: true });
  if (metadata === null) return;
  await mkdir(path.dirname(destination), { recursive: true });
  if (metadata.isSymbolicLink()) {
    await symlink(await readlink(source), destination);
  } else if (metadata.isDirectory()) {
    await cp(source, destination, { recursive: true, force: true });
  } else if (metadata.isFile()) {
    await cp(source, destination, { force: true });
  } else {
    throw new CollabOpError(
      "git_error",
      `could not safely inspect persistence path: ${pathname}`,
    );
  }
}

function landingConflictPaths(output: string): string[] {
  const paths: string[] = [];
  for (const line of output.split("\n")) {
    const match = line.match(/\s[123](?:\s|\t)(.+)$/u);
    if (match?.[1] && !paths.includes(match[1])) paths.push(match[1]);
  }
  return paths.slice(0, 32);
}

async function discardLandingWorktree(
  repo: Repository,
  temporary: string,
): Promise<void> {
  const temporaryPath = path.resolve(temporary);
  await rm(temporaryPath, { recursive: true, force: true });
  const administration = path.join(repo.gitDir, "worktrees");
  let entries: string[];
  try {
    entries = await readdir(administration);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return;
    throw error;
  }
  for (const entry of entries) {
    const record = path.join(administration, entry);
    try {
      const gitdir = (await readFile(path.join(record, "gitdir"), "utf8")).trim();
      if (path.resolve(gitdir) === path.join(temporaryPath, ".git")) {
        await rm(record, { recursive: true, force: true });
      }
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
    }
  }
}

// Build the local tracked tree in a disposable worktree, then let Git's
// tree-level merge prove whether it can be combined with integration without
// touching the persistence checkout.
async function landingPreflight(
  repo: Repository,
  persistencePath: string,
  beforeSha: string,
  integrationSha: string,
  signal?: AbortSignal,
): Promise<LandingPreflight> {
  const control = controlRepository(repo);
  const trackedPaths = await nulPathList(
    repo,
    persistencePath,
    ["ls-files", "--cached", "-z"],
    signal,
  );
  const temporary = path.join(repo.controlRoot, `.collab-land-preflight-${randomUUID()}`);
  let worktreeAdded = false;
  try {
    const addedWorktree = await repo.git(
      control.worktreeRoot,
      ["worktree", "add", "--detach", temporary, beforeSha],
      signal,
    );
    if (addedWorktree.code !== 0) {
      throw new CollabOpError(
        "git_error",
        `could not prepare landing preservation proof: ${boundedGitText(addedWorktree.stderr || addedWorktree.stdout)}`,
      );
    }
    worktreeAdded = true;
    for (const pathname of trackedPaths) {
      await copyLandingPath(persistencePath, temporary, pathname);
    }
    const added = await repo.git(temporary, ["add", "-u", "--"], signal);
    if (added.code !== 0) {
      throw new CollabOpError(
        "git_error",
        `could not capture unstaged persistence changes: ${boundedGitText(added.stderr || added.stdout)}`,
      );
    }
    const oursTree = await requireGit(repo.git, temporary, ["write-tree"], signal);
    const oursCommit = await requireGit(
      repo.git,
      temporary,
      [
        "-c",
        "user.name=Collab landing preflight",
        "-c",
        "user.email=collab-landing-preflight@localhost",
        "commit-tree",
        oursTree,
        "-p",
        beforeSha,
        "-m",
        "Collab landing preservation preflight",
      ],
      signal,
    );
    const merged = await repo.git(
      temporary,
      ["merge-tree", "--write-tree", oursCommit, integrationSha],
      signal,
    );
    if (merged.code === 1) {
      const paths = landingConflictPaths(merged.stdout);
      throw new CollabOpError(
        "path_collision",
        "unstaged persistence changes conflict with the integration tree",
        "Resolve the conflicting unstaged persistence changes before landing.",
        paths.length > 0 ? { paths } : undefined,
      );
    }
    if (merged.code !== 0) {
      throw new CollabOpError(
        "git_error",
        `could not prove safe landing preservation: ${boundedGitText(merged.stderr || merged.stdout)}`,
      );
    }
    const mergedTree = merged.stdout.split("\n", 1)[0].trim();
    if (!/^[0-9a-f]{40,64}$/u.test(mergedTree)) {
      throw new CollabOpError(
        "git_error",
        "could not prove safe landing preservation: Git returned no merge tree",
      );
    }
    return { oursTree, mergedTree };
  } finally {
    if (!worktreeAdded) {
      await discardLandingWorktree(repo, temporary);
    } else {
      const removedWorktree = await repo.git(
        control.worktreeRoot,
        ["worktree", "remove", "--force", temporary],
        signal,
      );
      if (removedWorktree.code !== 0) {
        await discardLandingWorktree(repo, temporary);
        throw new CollabOpError(
          "git_error",
          `could not clean landing preservation proof: ${boundedGitText(removedWorktree.stderr || removedWorktree.stdout)}`,
        );
      }
    }
  }
}

// A D/F flip inside one accepted transition puts both endpoints in the
// transition path list, but a restore source tree can never hold both
// sides of the flip: asking Git to match a strict descendant of a changed
// ancestor fails outright ("did not match any file(s) known to git") when
// the ancestor now occupies its place as a file, or as a directory above
// it. The changed ancestor already covers everything beneath it — no-overlay
// removal clears deleted children and Git's checkout machinery clears a
// conflicting file when a descendant needs the directory — so the restore
// set keeps only maximal paths. Collision analysis and post-landing
// verification keep the full transition list.
function maximalRestorePaths(paths: readonly string[]): string[] {
  const unique = [...new Set(paths)];
  return unique.filter((p) => !unique.some((q) => q !== p && p.startsWith(`${q}/`)));
}

// Find the exact existing roots that an accepted transition can rewrite. If
// the transition path is absent because a file or symlink blocks one of its
// ancestors, that obstruction is the root. Existing directories above an
// absent path are not collisions and remain outside the snapshot.
async function landingSnapshotPaths(
  persistencePath: string,
  transitionPaths: readonly string[],
): Promise<string[]> {
  const roots: string[] = [];
  for (const pathname of maximalRestorePaths(transitionPaths)) {
    let candidate = pathname;
    while (candidate !== ".") {
      const metadata = await pathMetadata(
        path.join(persistencePath, ...candidate.split("/")),
      );
      if (metadata !== null) {
        if (candidate === pathname || !metadata.isDirectory()) roots.push(candidate);
        break;
      }
      candidate = path.posix.dirname(candidate);
    }
  }
  return maximalRestorePaths(roots);
}

// Move filesystem roots aside without asking Git to enumerate ignored paths.
// Renaming within the persistence filesystem preserves every inode kind Git
// may overwrite, including FIFOs. The backup remains available until
// publication succeeds or rollback has restored the original roots.
async function snapshotLandingWorktree(
  persistencePath: string,
  transitionPaths: readonly string[],
): Promise<LandingWorktreeSnapshot> {
  const paths = await landingSnapshotPaths(persistencePath, transitionPaths);
  const root = path.join(persistencePath, `.collab-land-rollback-${randomUUID()}`);
  await mkdir(root, { mode: 0o700 });
  const rootMetadata = await pathMetadata(root);
  const moved: string[] = [];
  try {
    for (const pathname of paths) {
      const source = path.join(persistencePath, ...pathname.split("/"));
      const sourceMetadata = await pathMetadata(source);
      if (sourceMetadata === null || sourceMetadata.dev !== rootMetadata?.dev) {
        throw new Error(`persistence path cannot be moved atomically: ${pathname}`);
      }
      const backup = path.join(root, ...pathname.split("/"));
      await mkdir(path.dirname(backup), { recursive: true });
      await rename(source, backup);
      moved.push(pathname);
    }
    return { root, paths };
  } catch (error) {
    let restorationError: string | null = null;
    for (const pathname of moved.reverse()) {
      const backup = path.join(root, ...pathname.split("/"));
      const destination = path.join(persistencePath, ...pathname.split("/"));
      try {
        if ((await pathMetadata(destination)) !== null) {
          throw new Error(`persistence path reappeared during snapshot: ${pathname}`);
        }
        await mkdir(path.dirname(destination), { recursive: true });
        await rename(backup, destination);
      } catch (restoreError) {
        restorationError ??= boundedGitText(
          restoreError instanceof Error ? restoreError.message : String(restoreError),
        );
      }
    }
    if (restorationError === null) {
      await rm(root, { recursive: true, force: true });
    }
    throw new CollabOpError(
      "git_error",
      `could not snapshot persistence paths for landing rollback: ${boundedGitText(error instanceof Error ? error.message : String(error))}`,
      undefined,
      restorationError === null ? undefined : { restoration_error: restorationError },
    );
  }
}

async function restoreLandingSnapshot(
  persistencePath: string,
  snapshot: LandingWorktreeSnapshot,
): Promise<void> {
  for (const pathname of snapshot.paths) {
    const backup = path.join(snapshot.root, ...pathname.split("/"));
    const destination = path.join(persistencePath, ...pathname.split("/"));
    await rm(destination, { recursive: true, force: true });
    await mkdir(path.dirname(destination), { recursive: true });
    await rename(backup, destination);
  }
}

async function discardLandingSnapshot(
  snapshot: LandingWorktreeSnapshot,
): Promise<void> {
  await rm(snapshot.root, { recursive: true, force: true });
}

// Apply the preflight-proven tracked tree over exactly the accepted
// transition paths, then put the accepted integration tree in the index.
// Scoping the worktree restore keeps unchanged paths — including local
// directory replacements of files the integration does not touch — from
// being rewritten, while no-overlay deletions still clear cleanly tracked
// paths the transition deleted. This keeps local merged content unstaged
// without using a stash or a reset.
async function restoreLandingWorktree(
  repo: Repository,
  persistencePath: string,
  worktreeTree: string,
  indexTree: string,
  transitionPaths: readonly string[],
  signal?: AbortSignal,
): Promise<void> {
  await requireGit(
    repo.git,
    persistencePath,
    [
      "restore",
      "--source",
      worktreeTree,
      "--staged",
      "--worktree",
      "--no-overlay",
      "--",
      ...maximalRestorePaths(transitionPaths),
    ],
    signal,
  );
  await requireGit(
    repo.git,
    persistencePath,
    ["restore", "--source", indexTree, "--staged", "--", "."],
    signal,
  );
}

async function integrationLand(
  run: GitRunner,
  cwd: string,
  request: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<Record<string, unknown>> {
  const repo = await discoverRepository(run, cwd, signal);
  const taskId = requireIdentifier(request.task_id, "task id");
  const task = new TaskLayout(repo, taskId);
  const persistBranch = await taskPersistenceBranch(repo, task, signal);
  const message = requireLandingMessage(request.message, taskId);
  const integration = await requireManagedIntegration(controlRepository(repo), task, signal);
  const integrationSha = integration.tip;
  const persistence = await requirePersistenceCheckout(repo, task, persistBranch, signal);
  const persistenceWorktree = persistence.record.worktree!;
  // S4 native checkout contract: refuse staged, unstaged tracked, ordinary untracked before mutation
  if (await hasMergeOrConflictState(repo, persistenceWorktree, signal)) {
    throw new CollabOpError(
      "dirty_worktree",
      "persistence worktree has an active merge or conflict state",
      "Finish or abort the persistence merge before landing.",
    );
  }
  if (!(await persistenceIndexClean(repo, persistenceWorktree, signal))) {
    throw new CollabOpError(
      "dirty_index",
      "persistence index contains staged changes",
      "Commit or unstage persistence index changes before landing.",
    );
  }
  const ordinaryUntracked = await nulPathList(repo, persistenceWorktree, ["ls-files", "--others", "--exclude-standard", "-z", "--"], signal);
  if (ordinaryUntracked.length > 0) {
    throw new CollabOpError(
      "path_collision",
      "persistence worktree has ordinary untracked files",
      "Move or clean the untracked persistence paths before landing; ignored files are allowed.",
      { paths: [...new Set(ordinaryUntracked)].slice(0, 32) },
    );
  }
  const unstagedTracked = await nulPathList(repo, persistenceWorktree, ["diff", "--name-only", "-z", "--"], signal);
  if (unstagedTracked.length > 0) {
    throw new CollabOpError(
      "dirty_worktree",
      "persistence worktree has unstaged tracked changes",
      "Commit or discard the unstaged tracked changes in the persistence checkout before landing.",
      { paths: [...new Set(unstagedTracked)].slice(0, 32) },
    );
  }
  if (!(await isAncestor(controlRepository(repo), persistence.tip, integrationSha, signal))) {
    throw new CollabOpError(
      "stale_persistence",
      "persistence branch is ahead of integration",
      "Reconcile persistence into integration before landing.",
    );
  }
  const integrationTree = await treeAt(repo, integrationSha, signal);
  const persistenceTree = await treeAt(repo, persistence.tip, signal);
  if (integrationTree === persistenceTree) {
    throw new CollabOpError(
      "no_tree_change",
      "current integration would not change the persistence tree",
    );
  }
  const beforeSha = persistence.tip;
  // S1: create a non-fast-forward merge commit with ordered parents, hooks run natively
  const mergeResult = await repo.git(
    persistenceWorktree,
    ["merge", "--no-ff", "-m", `${message}\n\nTask: ${taskId}\nLanded: ${integrationSha}`, integrationSha],
    signal,
  );
  if (mergeResult.code !== 0) {
    // S4/S5: expose Git's resulting state without synthetic rollback
    throw new CollabOpError(
      "git_error",
      `Git merge failed: ${boundedGitText(mergeResult.stderr || mergeResult.stdout) || `exit ${mergeResult.code}`}`,
      "Resolve the reported Git state (conflict, hook failure, or merge error) and retry.",
      { stdout: boundedGitText(mergeResult.stdout), stderr: boundedGitText(mergeResult.stderr), code: mergeResult.code },
    );
  }
  const afterSha = await commitAt(controlRepository(repo), persistBranch.ref, signal);
  if (afterSha === null) {
    throw new CollabOpError("git_error", "landing merge did not produce a persistence commit");
  }
  // Verify S1 invariants: tree equals integration tree, parents ordered, message matches
  const afterTree = await treeAt(repo, afterSha, signal);
  if (afterTree !== integrationTree) {
    // Decision stop: hook may have changed tree away from accepted integration tree
    throw new CollabOpError(
      "git_error",
      "landing merge commit tree does not match the accepted integration tree (hook may have modified it)",
      "Inspect the hook-modified commit; landing requires the merge tree to equal the integration tree without disabling hooks.",
      { expected_tree: integrationTree, actual_tree: afterTree, persistence_sha: afterSha, integration_sha: integrationSha },
    );
  }
  const parentsLine = await requireGit(repo.git, mutationCwd(repo), ["rev-list", "--parents", "-n", "1", afterSha], signal);
  const parents = parentsLine.split(" ");
  if (parents.length !== 3 || parents[1] !== beforeSha || parents[2] !== integrationSha) {
    throw new CollabOpError(
      "git_error",
      "landing merge commit does not have the required ordered parents",
      "The merge commit's first parent must be the previous persistence head and second parent the integration head.",
      { expected_parents: [beforeSha, integrationSha], actual_parents: parents.slice(1), merge_sha: afterSha },
    );
  }
  if (!(await landingMessageMatches(repo, afterSha, message, taskId, integrationSha))) {
    throw new CollabOpError(
      "git_error",
      "landing commit message did not match the required subject and trailers",
      "The merge commit message must be the landing subject followed by Task and Landed trailers.",
      { expected_subject: message, task_id: taskId, integration_sha: integrationSha, merge_sha: afterSha },
    );
  }
  // Advance integration branch to the shared merge commit
  const integrationRef = `refs/heads/${task.integrationBranch}`;
  const casResult = await repo.git(mutationCwd(repo), ["update-ref", "--no-deref", integrationRef, afterSha, integrationSha], signal);
  if (casResult.code !== 0) {
    throw new CollabOpError(
      "git_error",
      `could not advance integration to the landed merge: ${boundedGitText(casResult.stderr || casResult.stdout)}`,
      "Verify the integration branch still points to the expected head and retry.",
      { integration_sha: integrationSha, merge_sha: afterSha },
    );
  }
  const reset = await repo.git(task.integrationPath, ["reset", "--hard", afterSha], signal);
  if (reset.code !== 0) {
    // Do not claim synthetic rollback; expose Git state
    throw new CollabOpError(
      "git_error",
      `could not synchronize the integration worktree: ${boundedGitText(reset.stderr || reset.stdout)}`,
      "Synchronize the integration worktree to the merge commit manually.",
      { integration_sha: integrationSha, merge_sha: afterSha },
    );
  }
  const persisted = await commitAt(controlRepository(repo), persistBranch.ref, signal);
  const integrated = await commitAt(controlRepository(repo), integrationRef, signal);
  if (persisted !== afterSha || integrated !== afterSha) {
    throw new CollabOpError(
      "git_error",
      "persistence and integration branches are not at the shared merge commit after landing",
      "Verify both branches point to the merge commit and retry if needed.",
      { expected: afterSha, persistence: persisted, integration: integrated },
    );
  }
  const warnings: string[] = [];
  const telemetryWarning = await recordEvent(task, "integration-land", "success", {
    integration_sha: integrationSha,
    persistence_sha: afterSha,
  });
  if (telemetryWarning) warnings.push(telemetryWarning);
  return {
    ok: true,
    operation: "integration-land",
    tool_version: TOOL_VERSION,
    ...(warnings.length ? { warnings } : {}),
  };
}

async function telemetryFileForTask(
  task: TaskLayout,
): Promise<string | null> {
  const stateRoot = path.join(task.repo.controlRoot, ".agent_state");
  for (const container of [
    path.join(stateRoot, "plans", task.taskId),
    path.join(stateRoot, "archives", task.taskId),
  ]) {
    if (await pathIsDirectory(container)) return path.join(container, ".collab_op", "telemetry.jsonl");
  }
  return null;
}

async function writeAtomicReportFile(
  destination: string,
  contents: string,
): Promise<void> {
  const existing = await pathMetadata(destination);
  if (existing?.isSymbolicLink()) throw new CollabOpError("report_collision", "report destination is a symlink");
  const temporary = `${destination}.tmp`;
  const temporaryExisting = await pathMetadata(temporary);
  if (temporaryExisting !== null) throw new CollabOpError("report_collision", "report temporary path already exists");
  await mkdir(path.dirname(destination), { recursive: true });
  const handle = await open(
    temporary,
    fsConstants.O_CREAT | fsConstants.O_EXCL | fsConstants.O_WRONLY | fsConstants.O_NOFOLLOW,
    0o600,
  );
  try {
    await handle.writeFile(contents, { encoding: "utf8" });
  } finally {
    await handle.close();
  }
  await rename(temporary, destination);
}

type RemovalReportSnapshot = {
  telemetry: string;
  baseSha: string | null;
  integrationSha: string | null;
  integrationDiff: Record<string, unknown> | null;
};

async function captureRemovalReportSnapshot(
  task: TaskLayout,
  signal?: AbortSignal,
): Promise<RemovalReportSnapshot> {
  const source = await telemetryFileForTask(task);
  let telemetry = "";
  if (source !== null && (await pathMetadata(source)) !== null) {
    try {
      telemetry = await readFile(source, "utf8");
    } catch (error) {
      throw new CollabOpError(
        "report_error",
        `telemetry could not be read for reporting: ${boundedGitText(error instanceof Error ? error.message : String(error))}`,
      );
    }
  }
  const baseSha = await commitAt(controlRepository(task.repo), task.integrationBaseRef, signal);
  const integrationSha = await commitAt(
    controlRepository(task.repo),
    `refs/heads/${task.integrationBranch}`,
    signal,
  );
  let integrationDiff: Record<string, unknown> | null = null;
  if (baseSha !== null && integrationSha !== null) {
    const commits = Number.parseInt(
      await requireGit(
        task.repo.git,
        mutationCwd(task.repo),
        ["rev-list", "--count", `${baseSha}..${integrationSha}`],
        signal,
      ),
      10,
    );
    const files = await nulPathList(
      task.repo,
      mutationCwd(task.repo),
      ["diff", "--name-only", "-z", baseSha, integrationSha, "--"],
      signal,
    );
    integrationDiff = { base_sha: baseSha, integration_sha: integrationSha, commits, files };
  }
  return { telemetry, baseSha, integrationSha, integrationDiff };
}

async function writeRemovalReport(
  task: TaskLayout,
  outputDir: string,
  facts: Record<string, unknown>,
  snapshot?: RemovalReportSnapshot,
  signal?: AbortSignal,
): Promise<{ reportPath: string; telemetryPath: string }> {
  const destination = path.resolve(task.repo.controlRoot, outputDir);
  const metadata = await pathMetadata(destination);
  if (metadata?.isSymbolicLink() || (metadata !== null && !metadata.isDirectory())) {
    throw new CollabOpError("report_collision", "report destination is not a regular directory");
  }
  await mkdir(destination, { recursive: true });
  const reportPath = path.join(destination, "collab-report.json");
  const telemetryPath = path.join(destination, "collab-telemetry.jsonl");
  const captured = snapshot ?? await captureRemovalReportSnapshot(task, signal);
  const telemetry = captured.telemetry;
  const events: Record<string, unknown>[] = [];
  const reportWarnings = Array.isArray(facts.warnings)
    ? facts.warnings.filter((value): value is string => typeof value === "string").slice(0, 32)
    : [];
  for (const [index, line] of telemetry.split(/\r?\n/).entries()) {
    if (!line) continue;
    try {
      const event = JSON.parse(line);
      if (event && typeof event === "object" && !Array.isArray(event)) {
        events.push(event as Record<string, unknown>);
      } else if (reportWarnings.length < 32) {
        reportWarnings.push(`telemetry line ${index + 1} is not an event object`);
      }
    } catch {
      if (reportWarnings.length < 32) reportWarnings.push(`telemetry line ${index + 1} is invalid JSON`);
    }
  }
  const operationCounts: Record<string, number> = {};
  const outcomeCounts: Record<string, number> = {};
  const laneStarts = new Map<string, number>();
  const laneDurations: Array<{ lane_id: string; seconds: number }> = [];
  const times: number[] = [];
  for (const event of events) {
    const operation = typeof event.operation === "string" ? event.operation : "unknown";
    const outcome = typeof event.outcome === "string" ? event.outcome : "unknown";
    operationCounts[operation] = (operationCounts[operation] ?? 0) + 1;
    outcomeCounts[outcome] = (outcomeCounts[outcome] ?? 0) + 1;
    const at = typeof event.at === "string" ? Date.parse(event.at) : Number.NaN;
    if (Number.isFinite(at)) times.push(at);
    const laneId = typeof event.lane_id === "string" ? event.lane_id : null;
    if (laneId && operation === "lane-create" && Number.isFinite(at)) laneStarts.set(laneId, at);
    if (laneId && operation === "lane-drop" && Number.isFinite(at)) {
      const start = laneStarts.get(laneId);
      if (start !== undefined) {
        laneDurations.push({ lane_id: laneId, seconds: Math.max(0, (at - start) / 1000) });
        laneStarts.delete(laneId);
      }
    }
  }
  const taskTiming = times.length
    ? {
        started_at: new Date(Math.min(...times)).toISOString(),
        finished_at: new Date(Math.max(...times)).toISOString(),
        seconds: Math.max(0, (Math.max(...times) - Math.min(...times)) / 1000),
      }
    : null;
  const report = {
    report_version: 1,
    tool_version: TOOL_VERSION,
    task_id: task.taskId,
    ...facts,
    counts: { operations: operationCounts, outcomes: outcomeCounts },
    integration_diff: captured.integrationDiff,
    lane_durations: laneDurations,
    task_timing: taskTiming,
    warnings: reportWarnings,
    timeline: events,
  };
  await writeAtomicReportFile(reportPath, `${JSON.stringify(report)}\n`);
  await writeAtomicReportFile(telemetryPath, telemetry);
  return { reportPath, telemetryPath };
}

async function collabReport(
  run: GitRunner,
  cwd: string,
  request: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<Record<string, unknown>> {
  const repo = await discoverRepository(run, cwd, signal);
  const taskId = requireIdentifier(request.task_id, "task id");
  const outputDir = request.output_dir;
  if (typeof outputDir !== "string" || outputDir.length === 0) {
    throw new CollabOpError(
      "invalid_output_dir",
      "output_dir must be a non-empty path",
      "Pass a non-empty report destination; relative paths resolve from the repository control root.",
    );
  }

  const task = new TaskLayout(repo, taskId);
  const captured = await withTaskLock(repo, taskId, async () => {
    const state = await status(run, cwd, taskId, signal);
    const reportSnapshot = await captureRemovalReportSnapshot(task, signal);
    const lanes = state.lanes && typeof state.lanes === "object"
      ? Object.keys(state.lanes as Record<string, unknown>).sort()
      : [];
    const warnings = Array.isArray(state.warnings)
      ? state.warnings.filter((value): value is string => typeof value === "string")
      : [];
    return {
      snapshot: reportSnapshot,
      facts: {
        integration_sha: reportSnapshot.integrationSha,
        base_sha: reportSnapshot.baseSha,
        lanes,
        warnings,
      },
      warnings,
    };
  });
  await writeRemovalReport(task, outputDir, captured.facts, captured.snapshot, signal);
  return {
    ok: true,
    tool_version: TOOL_VERSION,
    ...(captured.warnings.length > 0 ? { warnings: captured.warnings } : {}),
  };
}

function removalLaneIds(
  task: TaskLayout,
  ownedBranches: readonly string[],
): string[] {
  const ids = new Set<string>();
  const branchPrefix = `refs/heads/wave/${task.taskId}/`;
  for (const name of ownedBranches) {
    const laneId = laneIdFromRef(name, branchPrefix);
    if (laneId) ids.add(laneId);
  }
  return [...ids].sort();
}

async function removeIntegrationWorktree(
  repo: Repository,
  task: TaskLayout,
): Promise<string | null> {
  const records = await worktreeRecords(controlRepository(repo));
  const matches = records.filter((record) => record.branch === `refs/heads/${task.integrationBranch}`);
  if (
    matches.length !== 1 ||
    matches[0].worktree !== task.integrationPath ||
    !(await pathMetadata(task.integrationPath))?.isDirectory() ||
    !(await pathMetadata(path.dirname(task.integrationPath)))?.isDirectory()
  ) {
    return "integration worktree identity is incomplete or unsafe";
  }
  const removed = await repo.git(mutationCwd(repo), ["worktree", "remove", "--force", task.integrationPath]);
  if (removed.code !== 0) return boundedGitText(removed.stderr || removed.stdout) || "integration worktree could not be removed";
  await removeEmptyDirectory(task.integrationPath);
  return null;
}

async function integrationRemoveBestEffort(
  run: GitRunner,
  cwd: string,
  request: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<Record<string, unknown>> {
  const repo = await discoverRepository(run, cwd, signal);
  const taskId = requireIdentifier(request.task_id, "task id");
  const task = new TaskLayout(repo, taskId);
  const warnings: string[] = [];
  const inventory = await taskInventory(controlRepository(repo), task, signal);
  const integrationBranchRef = `refs/heads/${task.integrationBranch}`;
  const hasRecognizableTaskResource =
    inventory.ownedRefs.some(
      (ref) => ref === task.integrationBaseRef || ref === task.persistenceRef,
    ) ||
    inventory.ownedBranches.some((ref) => ref === integrationBranchRef || laneIdFromRef(ref, `refs/heads/wave/${task.taskId}/`) !== null) ||
    inventory.registeredUnderRoot.length > 0;
  if (!hasRecognizableTaskResource) {
    throw new CollabOpError(
      "task_not_found",
      `managed task ${taskId} does not have recognizable current-layout resources`,
      "Use a current managed task identifier or inspect the repository inventory before retrying.",
    );
  }
  const laneIds = new Set(removalLaneIds(task, inventory.ownedBranches));
  const lanePrefix = `refs/heads/wave/${task.taskId}/`;
  for (const record of inventory.registeredUnderRoot) {
    if (record.branch?.startsWith(lanePrefix)) {
      const laneId = laneIdFromRef(record.branch, lanePrefix);
      if (laneId) laneIds.add(laneId);
    }
  }

  for (const laneId of [...laneIds].sort()) {
    try {
      const lane = await laneInventory(repo, task, laneId, signal);
      const dropped = await laneAbandon(repo, task, laneId, lane, signal);
      warnings.push(...(Array.isArray(dropped.warnings) ? dropped.warnings.map((warning) => `lane ${laneId}: ${warning}`) : []));
    } catch (error) {
      warnings.push(`lane ${laneId}: ${boundedGitText(error instanceof Error ? error.message : String(error))}`);
    }
  }

  try {
    const removalError = await removeIntegrationWorktree(repo, task);
    if (removalError) warnings.push(removalError);
  } catch (error) {
    warnings.push(`integration worktree: ${boundedGitText(error instanceof Error ? error.message : String(error))}`);
  }

  try {
    const records = await worktreeRecords(controlRepository(repo), signal);
    if (records.some((record) => record.branch === integrationBranchRef)) {
      warnings.push("integration branch retained: worktree registration remains");
    } else {
      const names = await refNames(controlRepository(repo), integrationBranchRef, signal);
      if (names.length === 1 && names[0] === integrationBranchRef) {
        const tip = await commitAt(controlRepository(repo), integrationBranchRef, signal);
        if (tip === null) {
          warnings.push("integration branch retained: it does not resolve to a commit");
        } else {
          const removed = await repo.git(
            mutationCwd(repo),
            ["update-ref", "--no-deref", "-d", integrationBranchRef, tip],
            signal,
          );
          if (removed.code !== 0) {
            warnings.push(`integration branch retained: ${boundedGitText(removed.stderr || removed.stdout)}`);
          }
        }
      } else if (names.length > 0) {
        warnings.push("integration branch retained: ref inventory is incomplete or colliding");
      }
    }
  } catch (error) {
    warnings.push(`integration branch: ${boundedGitText(error instanceof Error ? error.message : String(error))}`);
  }

  const removableRefs = [task.integrationBaseRef];
  for (const ref of removableRefs) {
    try {
      const names = await refNames(controlRepository(repo), ref, signal);
      if (names.length === 0) continue;
      if (names.length !== 1 || names[0] !== ref || (await symbolicRefTarget(controlRepository(repo), ref, signal)) !== null) {
        warnings.push(`ref retained: ${ref}`);
        continue;
      }
      const value = await commitAt(controlRepository(repo), ref, signal);
      if (value === null) {
        warnings.push(`ref retained: ${ref} does not resolve to a commit`);
        continue;
      }
      const removed = await repo.git(
        mutationCwd(repo),
        ["update-ref", "--no-deref", "-d", ref, value],
        signal,
      );
      if (removed.code !== 0) warnings.push(`ref retained: ${ref}`);
    } catch (error) {
      warnings.push(`ref ${ref}: ${boundedGitText(error instanceof Error ? error.message : String(error))}`);
    }
  }

  try {
    const names = await refNames(controlRepository(repo), task.persistenceRef, signal);
    if (names.length > 0) {
      const target = await symbolicRefTarget(controlRepository(repo), task.persistenceRef, signal);
      if (names.length !== 1 || names[0] !== task.persistenceRef || target === null) {
        warnings.push(`persistence ref retained: ${task.persistenceRef}`);
      } else {
        const removed = await repo.git(
          mutationCwd(repo),
          ["symbolic-ref", "--delete", task.persistenceRef],
          signal,
        );
        if (removed.code !== 0) warnings.push(`persistence ref retained: ${task.persistenceRef}`);
      }
    }
  } catch (error) {
    warnings.push(`persistence ref: ${boundedGitText(error instanceof Error ? error.message : String(error))}`);
  }

  const knownRefs = new Set([task.integrationBaseRef, task.persistenceRef]);
  const unknownRefs = inventory.ownedRefs.filter((ref) => !knownRefs.has(ref));
  if (unknownRefs.length > 0) {
    warnings.push(`unrecognized task refs retained: ${unknownRefs.slice(0, 8).join(", ")}`);
  }
  const unknownBranches = inventory.ownedBranches.filter(
    (ref) => ref !== integrationBranchRef && laneIdFromRef(ref, lanePrefix) === null,
  );
  if (unknownBranches.length > 0) {
    warnings.push(`unrecognized task branches retained: ${unknownBranches.slice(0, 8).join(", ")}`);
  }

  await removeEmptyDirectory(path.join(task.root, "lanes"));
  await removeEmptyDirectory(task.root);
  await removeEmptyDirectory(path.join(repo.controlRoot, ".agent_state", "worktrees"));
  const telemetryWarning = await recordEvent(task, "integration-remove", "success", {
    warnings: warnings.slice(0, 32),
  });
  if (telemetryWarning) warnings.push(telemetryWarning);
  return {
    ok: true,
    tool_version: TOOL_VERSION,
    ...(warnings.length ? { warnings: warnings.slice(0, 64) } : {}),
  };
}

async function status(
  run: GitRunner,
  cwd: string,
  taskValue: unknown,
  signal?: AbortSignal,
): Promise<Record<string, unknown>> {
  const repo = await discoverRepository(run, cwd, signal);
  if (taskValue === undefined) {
    return { tool_version: TOOL_VERSION, tasks: await taskIds(repo, signal), warnings: [] };
  }

  const taskId = requireIdentifier(taskValue, "task id");
  const task = new TaskLayout(repo, taskId);
  const refs = await refSnapshot(
    repo,
    [`refs/orchestrate/${taskId}/`, `refs/heads/wave/${taskId}/`],
    signal,
  );
  const base = refs.get(task.integrationBaseRef)?.object ?? null;
  if (base === null) {
    throw new CollabOpError("task_not_found", `managed task ${taskId} does not exist`);
  }

  const warnings: string[] = [];
  const integrationHead = refs.get(`refs/heads/${task.integrationBranch}`)?.object ?? null;
  const records = await worktreeRecords(repo, signal);

  if (integrationHead === null) {
    warnings.push("integration branch is missing");
  } else {
    await warnManagedWorktree(
      repo,
      records,
      task.integrationPath,
      task.integrationBranch,
      integrationHead,
      "integration",
      warnings,
      signal,
    );
  }

  let stale = true;
  const persistenceTarget = refs.get(task.persistenceRef)?.symbolicTarget ?? null;
  if (!persistenceTarget?.startsWith("refs/heads/")) {
    warnings.push("integration freshness could not be proven: persistence ref is missing or invalid");
  } else if (integrationHead !== null) {
    const persistenceHead = await commitAt(repo, persistenceTarget, signal);
    if (persistenceHead === null) {
      warnings.push("integration freshness could not be proven: persistence branch is missing");
    } else {
      stale = !(await isAncestor(repo, persistenceHead, integrationHead, signal));
    }
  }

  const laneIds = new Set<string>();
  const laneBranchPrefix = `refs/heads/wave/${taskId}/`;
  for (const name of refs.keys()) {
    const laneId = laneIdFromRef(name, laneBranchPrefix);
    if (laneId) laneIds.add(laneId);
  }

  const lanes: Record<string, { worktree: string; HEAD: string | null }> = {};
  for (const laneId of [...laneIds].sort()) {
    const lanePath = task.lanePath(laneId);
    const laneHead = refs.get(`refs/heads/${task.laneBranch(laneId)}`)?.object ?? null;
    lanes[laneId] = { worktree: lanePath, HEAD: laneHead };
    if (laneHead === null) {
      warnings.push(`lane ${laneId} inventory is incomplete`);
      continue;
    }
    await warnManagedWorktree(
      repo,
      records,
      lanePath,
      task.laneBranch(laneId),
      laneHead,
      `lane ${laneId}`,
      warnings,
      signal,
    );
  }

  return {
    tool_version: TOOL_VERSION,
    task_id: taskId,
    integration: { worktree: task.integrationPath, HEAD: integrationHead, stale },
    lanes,
    warnings,
  };
}

const registeredTaskId = {
  type: "string",
  pattern: IDENTIFIER.source,
  description: "Lowercase task identifier for the Git-managed task.",
} as const;

const registeredBranch = {
  type: "string",
  minLength: 1,
  pattern: "^(?!-)(?!refs/)[^\\u0000-\\u001f\\u007f]+$",
  description: "Short name of an existing local branch below refs/heads/; remote refs are invalid.",
} as const;

const registeredBaseSha = {
  type: "string",
  minLength: 40,
  maxLength: 64,
  pattern: "^[0-9a-f]{40,64}$",
  description: "Full lowercase commit ID that exists and is an ancestor of both branch tips.",
} as const;

const registeredOutputDir = {
  type: "string",
  minLength: 1,
  description: "Non-empty report destination; relative paths resolve from the repository control root.",
} as const;

const registeredRepo = {
  type: "string",
  minLength: 1,
  description: "Optional repository selector; omit it to resolve from the session working directory, otherwise pass an absolute path whose symlink-resolved value is exactly a Git worktree root.",
} as const;

const registeredLaneId = {
  type: "string",
  pattern: IDENTIFIER.source,
  not: { const: "integration" },
  description: "Lowercase lane identifier for the Git-managed task; integration is reserved.",
} as const;

const registeredLaneComment = {
  type: "string",
  minLength: 1,
  maxLength: 500,
  description: "Optional for create only: trimmed 1-500 Unicode characters without control characters.",
} as const;

const registeredLaneParameters = {
  type: "object",
  additionalProperties: false,
  properties: {
    repo: registeredRepo,
    action: {
      type: "string",
      enum: ["create", "reconcile", "collect", "drop"],
      description: "Lane action to perform.",
    },
    task_id: registeredTaskId,
    lane_id: registeredLaneId,
    comment: registeredLaneComment,
  },
  required: ["action", "task_id", "lane_id"],
} as const;

const registeredIntegrationCreateParameters = {
  type: "object",
  additionalProperties: false,
  properties: {
    repo: registeredRepo,
    task_id: registeredTaskId,
  },
  required: ["task_id"],
} as const;

const registeredIntegrationAdoptParameters = {
  type: "object",
  additionalProperties: false,
  properties: {
    repo: registeredRepo,
    task_id: registeredTaskId,
    source_branch: registeredBranch,
    persist: registeredBranch,
    base_sha: registeredBaseSha,
  },
  required: ["task_id", "source_branch", "persist", "base_sha"],
} as const;

const registeredIntegrationReconcileParameters = {
  type: "object",
  additionalProperties: false,
  properties: {
    repo: registeredRepo,
    task_id: registeredTaskId,
    lane_id: registeredLaneId,
  },
  required: ["task_id", "lane_id"],
} as const;

const registeredIntegrationLandParameters = {
  type: "object",
  additionalProperties: false,
  properties: {
    repo: registeredRepo,
    task_id: registeredTaskId,
    message: {
      type: "string",
      minLength: 1,
      maxLength: 200,
      description: "Optional single-line landing subject of 1-200 characters without control characters.",
    },
  },
  required: ["task_id"],
} as const;

const registeredIntegrationRemoveParameters = {
  type: "object",
  additionalProperties: false,
  properties: {
    repo: registeredRepo,
    task_id: registeredTaskId,
  },
  required: ["task_id"],
} as const;

const registeredStatusParameters = {
  type: "object",
  additionalProperties: false,
  properties: {
    repo: registeredRepo,
    task_id: registeredTaskId,
  },
} as const;

const registeredReportParameters = {
  type: "object",
  additionalProperties: false,
  properties: {
    repo: registeredRepo,
    task_id: registeredTaskId,
    output_dir: registeredOutputDir,
  },
  required: ["task_id", "output_dir"],
} as const;

function validateRegisteredRequest(
  request: Record<string, unknown>,
  toolName: string,
  required: readonly string[],
  allowed: readonly string[],
): Record<string, unknown> {
  const unknown = Object.keys(request).filter((key) => !allowed.includes(key));
  if (unknown.length > 0) {
    throw new CollabOpError(
      "invalid_parameters",
      `${toolName} does not accept parameter(s): ${unknown.join(", ")}`,
      `Remove unsupported parameter(s) and pass only: ${allowed.join(", ")}.`,
    );
  }
  const missing = required.filter((key) => request[key] === undefined);
  if (missing.length > 0) {
    throw new CollabOpError(
      "invalid_parameters",
      `${toolName} requires parameter(s): ${missing.join(", ")}`,
      `Provide the required parameter(s): ${missing.join(", ")}.`,
    );
  }
  return request;
}

function registeredErrorEnvelope(error: unknown): Record<string, unknown> {
  const known = error instanceof CollabOpError;
  const message = known
    ? error.message
    : error instanceof Error && error.message
      ? error.message
      : "The operation failed unexpectedly.";
  const body: Record<string, unknown> = {
    code: known ? error.code : "git_error",
    message,
    repair:
      known && error.repair?.trim()
        ? error.repair
        : "Inspect the repository Git and filesystem state, correct the reported condition, and retry.",
  };
  if (known && error.details && Object.keys(error.details).length > 0) body.details = error.details;
  return { ok: false, tool_version: TOOL_VERSION, error: body };
}

async function registeredRepositoryCwd(
  run: GitRunner,
  fallbackCwd: string,
  value: unknown,
  signal?: AbortSignal,
): Promise<string> {
  if (value === undefined) return fallbackCwd;
  if (typeof value !== "string" || !value || !path.isAbsolute(value)) {
    throw new CollabOpError(
      "invalid_repo",
      "repo must be an absolute path to an existing Git worktree root",
      "Pass the absolute path reported by git rev-parse --show-toplevel, or omit repo to resolve from the session working directory.",
      { repo: value },
    );
  }
  let canonicalInput: string;
  try {
    if (!(await stat(value)).isDirectory()) throw new Error("path is not a directory");
    canonicalInput = await realpath(value);
  } catch (error) {
    throw new CollabOpError(
      "invalid_repo",
      `repo is not an existing directory: ${value}`,
      "Pass the absolute path to an existing Git worktree root.",
      { repo: value, cause: error instanceof Error ? error.message : String(error) },
    );
  }
  const repo = await discoverRepository(run, canonicalInput, signal);
  const canonicalRoot = await realpath(repo.worktreeRoot);
  if (canonicalInput !== canonicalRoot) {
    throw new CollabOpError(
      "repo_not_worktree_root",
      `repo must name the exact Git worktree root: ${canonicalRoot}`,
      `Pass ${canonicalRoot} as repo.`,
      { repo: value, worktree_root: canonicalRoot },
    );
  }
  return canonicalRoot;
}

async function executeRegisteredTool(
  run: GitRunner,
  request: Record<string, unknown>,
  ctx: ExtensionContext,
  handler: (
    request: Record<string, unknown>,
    signal: AbortSignal | undefined,
    cwd: string,
  ) => Promise<Record<string, unknown>>,
  signal: AbortSignal | undefined,
): Promise<Record<string, unknown>> {
  try {
    const { repo, ...operationRequest } = request;
    const cwd = await registeredRepositoryCwd(run, ctx.cwd, repo, signal);
    return await handler(operationRequest, signal, cwd);
  } catch (error) {
    throw new Error(JSON.stringify(registeredErrorEnvelope(error)));
  }
}

function registeredMutationResult(
  result: Record<string, unknown>,
  fields: readonly string[] = [],
): Record<string, unknown> {
  const output: Record<string, unknown> = { ok: true, tool_version: TOOL_VERSION };
  for (const field of fields) {
    if (result[field] !== undefined) output[field] = result[field];
  }
  if (Array.isArray(result.warnings) && result.warnings.length > 0) {
    output.warnings = result.warnings;
  }
  return output;
}

export default function collabOpExtension(pi: ExtensionAPI): void {
  const runGit = gitRunner(pi);
  // Every task-mutating handler executes under one shared task-scoped exclusive
  // lock so independent tools cannot interleave resource mutations.
  // The Task mutation lock Module durable declaration above owns fail-fast default, lane-create-only bounded-wait, FIFO, cancellation, timeout, ownership-safe release and placement revalidation.
  function taskLocked(
    handler: (
      request: Record<string, unknown>,
      signal: AbortSignal | undefined,
      cwd: string,
    ) => Promise<Record<string, unknown>>,
  ): (
    request: Record<string, unknown>,
    signal: AbortSignal | undefined,
    cwd: string,
  ) => Promise<Record<string, unknown>> {
    return async (request, signal, cwd) => {
      const repo = await discoverRepository(runGit, cwd, signal);
      const taskId = requireIdentifier(request.task_id, "task id");
      return withTaskLock(repo, taskId, () => handler(request, signal, cwd));
    };
  }

  pi.registerTool({
    name: "collab_integration_create",
    label: "Create Collab integration",
    description: "Create a Git-managed integration worktree from the acting worktree's attached local branch and HEAD; that attached branch becomes the task persistence branch. Omit repo to act from the session working directory; otherwise pass an absolute path whose symlink-resolved value is exactly a Git worktree root. Unless the repository already ignores .agent_state, this first appends /.agent_state/ to info/exclude in the repository's common Git directory, verifies the result, and reports the write in warnings; if a higher-precedence .gitignore rule keeps .agent_state un-ignored, it refuses before creating managed resources and reports whether the appended line remains in info/exclude.",
    parameters: registeredIntegrationCreateParameters,
    async execute(_toolCallId, request, signal, _onUpdate, ctx: ExtensionContext) {
      const result = await executeRegisteredTool(
        runGit,
        request as Record<string, unknown>,
        ctx,
        (value, innerSignal, innerCwd) => {
          const params = validateRegisteredRequest(
            value,
            "collab_integration_create",
            ["task_id"],
            ["task_id"],
          );
          return taskLocked((lockedRequest, lockedSignal, lockedCwd) =>
            integrationCreate(runGit, lockedCwd, lockedRequest, lockedSignal).then((created) =>
              registeredMutationResult(created),
            ),
          )(params, innerSignal, innerCwd);
        },
        signal,
      );
      return {
        content: [{ type: "text" as const, text: JSON.stringify(result) }],
        details: result,
      };
    },
  });

  pi.registerTool({
    name: "collab_integration_adopt",
    label: "Adopt Collab integration",
    description: "Adopt an existing local branch into a Git-managed integration using an exact common base commit. Omit repo to act from the session working directory; otherwise pass an absolute path whose symlink-resolved value is exactly a Git worktree root. Unless the repository already ignores .agent_state, this first appends /.agent_state/ to info/exclude in the repository's common Git directory, verifies the result, and reports the write in warnings; if a higher-precedence .gitignore rule keeps .agent_state un-ignored, it refuses before creating managed resources and reports whether the appended line remains in info/exclude.",
    parameters: registeredIntegrationAdoptParameters,
    async execute(_toolCallId, request, signal, _onUpdate, ctx: ExtensionContext) {
      const result = await executeRegisteredTool(
        runGit,
        request as Record<string, unknown>,
        ctx,
        (value, innerSignal, innerCwd) => {
          const params = validateRegisteredRequest(
            value,
            "collab_integration_adopt",
            ["task_id", "source_branch", "persist", "base_sha"],
            ["task_id", "source_branch", "persist", "base_sha"],
          );
          return taskLocked((lockedRequest, lockedSignal, lockedCwd) =>
            integrationAdopt(runGit, lockedCwd, lockedRequest, lockedSignal).then((adopted) =>
              registeredMutationResult(adopted, ["source_branch", "integration_branch"]),
            ),
          )(params, innerSignal, innerCwd);
        },
        signal,
      );
      return {
        content: [{ type: "text" as const, text: JSON.stringify(result) }],
        details: result,
      };
    },
  });

  pi.registerTool({
    name: "collab_integration_reconcile",
    label: "Reconcile Collab integration",
    description: "Reconcile the task-owned persistence branch into a Git-managed lane. Omit repo to act from the session working directory; otherwise pass an absolute path whose symlink-resolved value is exactly a Git worktree root.",
    parameters: registeredIntegrationReconcileParameters,
    async execute(_toolCallId, request, signal, _onUpdate, ctx: ExtensionContext) {
      const result = await executeRegisteredTool(
        runGit,
        request as Record<string, unknown>,
        ctx,
        (value, innerSignal, innerCwd) => {
          const params = validateRegisteredRequest(
            value,
            "collab_integration_reconcile",
            ["task_id", "lane_id"],
            ["task_id", "lane_id"],
          );
          return taskLocked((lockedRequest, lockedSignal, lockedCwd) =>
            integrationReconcile(runGit, lockedCwd, lockedRequest, lockedSignal).then((reconciled) =>
              registeredMutationResult(reconciled, ["state", "lane_id", "lane_sha"]),
            ),
          )(params, innerSignal, innerCwd);
        },
        signal,
      );
      return {
        content: [{ type: "text" as const, text: JSON.stringify(result) }],
        details: result,
      };
    },
  });

  pi.registerTool({
    name: "collab_integration_land",
    label: "Land Collab integration",
    description: "Land the current integration into the task-owned persistence branch. Omit repo to act from the session working directory; otherwise pass an absolute path whose symlink-resolved value is exactly a Git worktree root.",
    parameters: registeredIntegrationLandParameters,
    async execute(_toolCallId, request, signal, _onUpdate, ctx: ExtensionContext) {
      const result = await executeRegisteredTool(
        runGit,
        request as Record<string, unknown>,
        ctx,
        (value, innerSignal, innerCwd) => {
          const params = validateRegisteredRequest(
            value,
            "collab_integration_land",
            ["task_id"],
            ["task_id", "message"],
          );
          return taskLocked((lockedRequest, lockedSignal, lockedCwd) =>
            integrationLand(runGit, lockedCwd, lockedRequest, lockedSignal).then((landed) =>
              registeredMutationResult(landed),
            ),
          )(params, innerSignal, innerCwd);
        },
        signal,
      );
      return {
        content: [{ type: "text" as const, text: JSON.stringify(result) }],
        details: result,
      };
    },
  });

  pi.registerTool({
    name: "collab_integration_remove",
    label: "Remove Collab integration",
    description: "Best-effort force-removal of a task's recognizable managed integration resources. Omit repo to act from the session working directory; otherwise pass an absolute path whose symlink-resolved value is exactly a Git worktree root.",
    parameters: registeredIntegrationRemoveParameters,
    async execute(_toolCallId, request, signal, _onUpdate, ctx: ExtensionContext) {
      const result = await executeRegisteredTool(
        runGit,
        request as Record<string, unknown>,
        ctx,
        (value, innerSignal, innerCwd) => {
          const params = validateRegisteredRequest(
            value,
            "collab_integration_remove",
            ["task_id"],
            ["task_id"],
          );
          return taskLocked((lockedRequest, lockedSignal, lockedCwd) =>
            integrationRemoveBestEffort(runGit, lockedCwd, lockedRequest, lockedSignal).then((removed) =>
              registeredMutationResult(removed),
            ),
          )(params, innerSignal, innerCwd);
        },
        signal,
      );
      return {
        content: [{ type: "text" as const, text: JSON.stringify(result) }],
        details: result,
      };
    },
  });

  pi.registerTool({
    name: "collab_status",
    label: "Inspect Collab status",
    description: "Inspect Git-managed task status, or list discoverable managed tasks when task_id is omitted. Omit repo to act from the session working directory; otherwise pass an absolute path whose symlink-resolved value is exactly a Git worktree root.",
    parameters: registeredStatusParameters,
    async execute(_toolCallId, request, signal, _onUpdate, ctx: ExtensionContext) {
      const result = await executeRegisteredTool(
        runGit,
        request as Record<string, unknown>,
        ctx,
        (value, innerSignal, innerCwd) => {
          const params = validateRegisteredRequest(
            value,
            "collab_status",
            [],
            ["task_id"],
          );
          return status(runGit, innerCwd, params.task_id, innerSignal);
        },
        signal,
      );
      return {
        content: [{ type: "text" as const, text: JSON.stringify(result) }],
        details: result,
      };
    },
  });

  pi.registerTool({
    name: "collab_report",
    label: "Report Collab state",
    description: "Snapshot task state and telemetry to fixed report artifacts; no cleanup or readiness judgement is performed. Omit repo to act from the session working directory; otherwise pass an absolute path whose symlink-resolved value is exactly a Git worktree root.",
    parameters: registeredReportParameters,
    async execute(_toolCallId, request, signal, _onUpdate, ctx: ExtensionContext) {
      const result = await executeRegisteredTool(
        runGit,
        request as Record<string, unknown>,
        ctx,
        (value, innerSignal, innerCwd) => {
          const params = validateRegisteredRequest(
            value,
            "collab_report",
            ["task_id", "output_dir"],
            ["task_id", "output_dir"],
          );
          return collabReport(runGit, innerCwd, params, innerSignal);
        },
        signal,
      );
      return {
        content: [{ type: "text" as const, text: JSON.stringify(result) }],
        details: result,
      };
    },
  });

  pi.registerTool({
    name: "collab_lane",
    label: "Manage Collab lane",
    description:
      "Manage a task lane. Omit repo to act from the session working directory; otherwise pass an absolute path whose symlink-resolved value is exactly a Git worktree root. `create` makes a branch and worktree at the integration tip (optional comment only for create). `reconcile` merges integration into the lane. `collect` fast-forwards integration to the lane tip and force-retires the lane worktree — untracked or ignored files there are lost, tracked dirt or merge conflict keeps the lane with a warning. `drop` force-retires the lane without collecting, discarding uncollected work and warning if dirty, conflicted or incomplete.",
    parameters: registeredLaneParameters,
    async execute(_toolCallId, request, signal, _onUpdate, ctx: ExtensionContext) {
      const result = await executeRegisteredTool(
        runGit,
        request as Record<string, unknown>,
        ctx,
        async (value, innerSignal, innerCwd) => {
          const params = validateRegisteredRequest(
            value,
            "collab_lane",
            ["action", "task_id", "lane_id"],
            ["action", "task_id", "lane_id", "comment"],
          );
          const action = params.action as string;
          if (!["create", "reconcile", "collect", "drop"].includes(action)) {
            throw new CollabOpError(
              "invalid_parameters",
              "action must be one of create, reconcile, collect, drop",
              "Pass action as create, reconcile, collect, or drop.",
              { action },
            );
          }
          if (params.comment !== undefined && action !== "create") {
            throw new CollabOpError(
              "invalid_parameters",
              "comment is only valid for action create",
              "Omit comment for reconcile, collect, and drop, or use action create.",
              { action },
            );
          }
          if (action === "create") {
            const repo = await discoverRepository(runGit, innerCwd, innerSignal);
            const taskId = requireIdentifier(params.task_id, "task id");
            return withTaskLock(
              repo,
              taskId,
              async () => {
                const created = await laneCreate(
                  runGit,
                  innerCwd,
                  { task_id: params.task_id, lane_id: params.lane_id, comment: params.comment },
                  innerSignal,
                );
                return registeredMutationResult(created);
              },
              { policy: "bounded-wait", signal: innerSignal, timeoutMs: LANE_CREATE_BOUNDED_WAIT_MS },
            );
          }
          if (action === "reconcile") {
            const repo = await discoverRepository(runGit, innerCwd, innerSignal);
            const taskId = requireIdentifier(params.task_id, "task id");
            return withTaskLock(repo, taskId, async () => {
              const reconciled = await laneReconcile(
                runGit,
                innerCwd,
                { task_id: params.task_id, lane_id: params.lane_id },
                innerSignal,
              );
              return registeredMutationResult(reconciled, ["state"]);
            });
          }
          if (action === "collect") {
            const repo = await discoverRepository(runGit, innerCwd, innerSignal);
            const taskId = requireIdentifier(params.task_id, "task id");
            return withTaskLock(repo, taskId, async () => {
              const collected = await laneCollect(
                runGit,
                innerCwd,
                { task_id: params.task_id, lane_id: params.lane_id },
                innerSignal,
                true,
              );
              return registeredMutationResult(collected, ["state"]);
            });
          }
          const repo = await discoverRepository(runGit, innerCwd, innerSignal);
          const taskId = requireIdentifier(params.task_id, "task id");
          return withTaskLock(repo, taskId, async () => {
            const laneId = requireLaneId(params.lane_id);
            const task = new TaskLayout(repo, taskId);
            const inventory = await laneInventory(repo, task, laneId, innerSignal);
            const dropped = await laneAbandon(repo, task, laneId, inventory, innerSignal);
            return registeredMutationResult(dropped);
          });
        },
        signal,
      );
      return {
        content: [{ type: "text" as const, text: JSON.stringify(result) }],
        details: result,
      };
    },
  });
}
