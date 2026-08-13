import { randomUUID } from "node:crypto";
import { constants as fsConstants } from "node:fs";
import { lstat, mkdir, open, readdir, readFile, rename, rm, rmdir, unlink } from "node:fs/promises";
import path from "node:path";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
const TOOL_VERSION = 1;
const IDENTIFIER = /^[a-z0-9][a-z0-9._-]*$/;
const METHODS = [
  "integration_create",
  "integration_adopt",
  "integration_land",
  "integration_reconcile",
  "integration_remove",
  "integration_migrate",
  "lane_create",
  "lane_collect",
  "lane_reconcile",
  "lane_drop",
  "status",
] as const;

type GitResult = { code: number; stdout: string; stderr: string };
type WorktreeRecord = {
  worktree?: string;
  HEAD?: string;
  branch?: string;
  detached?: boolean;
};

type RefRecord = {
  object: string | null;
  symbolicTarget: string | null;
};

type GitRunner = (
  cwd: string,
  args: readonly string[],
  signal?: AbortSignal,
) => Promise<GitResult>;

type Repository = {
  worktreeRoot: string;
  controlRoot: string;
  gitDir: string;
  git: GitRunner;
};

class TaskLayout {
  readonly root: string;
  readonly integrationBranch: string;
  readonly integrationBaseRef: string;
  readonly integrationPath: string;
  readonly persistenceRef: string;
  readonly landedRef: string;
  readonly acceptedRef: string;
  readonly acceptanceOpenRef: string;
  readonly legacyUserAcceptedRef: string;
  readonly acceptancePath: string;

  constructor(
    readonly repo: Repository,
    readonly taskId: string,
  ) {
    this.root = path.join(repo.controlRoot, ".agent_state", "worktrees", taskId);
    this.integrationBranch = `wave/${taskId}/integration`;
    this.integrationBaseRef = `refs/orchestrate/${taskId}/integration/base`;
    this.integrationPath = path.join(this.root, "integration");
    this.persistenceRef = `refs/orchestrate/${taskId}/persistence`;
    this.landedRef = `refs/orchestrate/${taskId}/landed`;
    this.acceptedRef = `refs/orchestrate/${taskId}/accepted`;
    this.acceptanceOpenRef = `refs/orchestrate/${taskId}/acceptance-open`;
    this.legacyUserAcceptedRef = `refs/orchestrate/${taskId}/user-accepted`;
    this.acceptancePath = path.join(this.root, "acceptance");
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

function shellRunner(pi: ExtensionAPI): GitRunner {
  return async (cwd, args, signal) => {
    const result = await pi.exec("sh", [...args], { cwd, signal });
    return { code: result.code, stdout: result.stdout, stderr: result.stderr };
  };
}

const TASK_LOCK_TTL_MS = 24 * 60 * 60 * 1000;

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

async function withTaskLock<T>(
  repo: Repository,
  taskId: string,
  body: () => Promise<T>,
): Promise<T> {
  const { lockPath, token } = await acquireTaskLock(repo, taskId);
  try {
    return await body();
  } finally {
    await releaseTaskLock(lockPath, token);
  }
}

// Every public task mutator (all except status) refuses while any migration
// sentinel namespace resource exists; only integration_migrate may advance a
// committed migration.
async function assertNoMigrationSentinel(
  repo: Repository,
  taskId: string,
  signal?: AbortSignal,
): Promise<void> {
  const names = await refNames(
    controlRepository(repo),
    `refs/orchestrate/${taskId}/migration`,
    signal,
  );
  if (names.length > 0) {
    throw new CollabOpError(
      "task_recovery_required",
      `task ${taskId} has an incomplete migration that must be resumed or resolved first`,
      "Run integration_migrate for the task to resume and finish the migration.",
      { task_id: taskId },
    );
  }
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

async function discoverRepository(
  run: GitRunner,
  cwd: string,
  signal?: AbortSignal,
): Promise<Repository> {
  const rootProbe = await run(cwd, ["rev-parse", "--show-toplevel"], signal);
  if (rootProbe.code !== 0 || !rootProbe.stdout.trim()) {
    throw new CollabOpError("not_git_repository", "current directory is not a Git repository");
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

async function isDirty(
  repo: Repository,
  worktree: string,
  signal?: AbortSignal,
): Promise<boolean> {
  const result = await repo.git(
    worktree,
    ["status", "--porcelain=v1", "--untracked-files=all"],
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

async function isFullyClean(
  repo: Repository,
  worktree: string,
  signal?: AbortSignal,
): Promise<boolean> {
  const result = await repo.git(
    worktree,
    ["status", "--porcelain=v1", "--untracked-files=all", "--ignored=matching"],
    signal,
  );
  if (result.code !== 0) {
    throw new CollabOpError(
      "git_error",
      `could not inspect worktree state: ${result.stderr.trim() || result.stdout.trim()}`,
    );
  }
  return result.stdout.length === 0;
}

function operationFor(method: string): string {
  return method.replaceAll("_", "-");
}

function errorEnvelope(method: string, error: unknown): Record<string, unknown> {
  const known = error instanceof CollabOpError;
  const body: Record<string, unknown> = {
    code: known ? error.code : "git_error",
    message: known ? error.message : error instanceof Error ? error.message : String(error),
  };
  if (known && error.repair) body.repair = error.repair;
  if (known && error.details && Object.keys(error.details).length > 0) body.details = error.details;
  return {
    ok: false,
    operation: operationFor(method),
    tool_version: TOOL_VERSION,
    error: body,
  };
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
  if (await isDirty(repo, expectedPath, signal)) warnings.push(`${label} worktree is dirty`);
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
  if (typeof value !== "string" || value.length === 0 || value.startsWith("-")) {
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
      if (record && (await isFullyClean(repo, task.integrationPath))) {
        const removal = await repo.git(repo.worktreeRoot, [
          "worktree",
          "remove",
          "--force",
          task.integrationPath,
        ]);
        removedWorktree = removal.code === 0;
      }
    } catch {
      // Never remove a worktree when its identity or cleanliness is uncertain.
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
    await repo.git(repo.worktreeRoot, ["worktree", "remove", "--force", task.integrationPath]);
    await repo.git(
      repo.worktreeRoot,
      ["update-ref", "-d", `refs/heads/${task.integrationBranch}`, head],
    );
    try {
      await rm(task.integrationPath, { recursive: true, force: true });
    } catch {
      // The parent may itself be the failing obstruction; preserve it.
    }
    try {
      await rmdir(task.root);
    } catch {
      // Preserve any concurrently introduced or otherwise unknown inventory.
    }
    throw error;
  }

  const warnings: string[] = [];
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
  if (request.dry_run !== undefined && typeof request.dry_run !== "boolean") {
    throw new CollabOpError(
      "invalid_dry_run",
      "dry_run must be a boolean when provided",
      "Pass true to preview adoption or omit dry_run to perform adoption.",
    );
  }
  const dryRun = request.dry_run === true;
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
    if (!(await isFullyClean(repo, task.integrationPath, signal))) {
      throw new CollabOpError(
        "task_resource_collision",
        "canonical integration worktree is not clean",
        "Clean the canonical integration worktree before adopting it.",
      );
    }
  }

  if (dryRun) {
    return {
      ok: true,
      operation: "integration-adopt",
      tool_version: TOOL_VERSION,
      dry_run: true,
      source_branch: sourceBranch.name,
      source_sha: sourceSha,
      integration_branch: task.integrationBranch,
      integration_sha: sourceSha,
      base_sha: baseSha,
      persist: persistBranch.name,
      planned: {
        create_integration_worktree: !sourceWasCanonical,
        create_integration_branch: !sourceWasCanonical,
        create_base_ref: !basePresent,
        create_persistence_ref: !persistencePresent,
      },
    };
  }

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

  const warnings: string[] = [];
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

async function requireManagedIntegration(
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

async function laneInventory(
  repo: Repository,
  task: TaskLayout,
  laneId: string,
  signal?: AbortSignal,
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
      worktreeRecords(gitRepo, signal),
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
    const clean = await isFullyClean(repo, current.lanePath);
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
  let mergeResult: GitResult;
  try {
    mergeResult = await repo.git(
      task.lanePath(laneId),
      ["merge", "--no-ff", "-m", `Reconcile lane ${laneId} with integration`, integrationTip],
      signal,
    );
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
  if (!(await isFullyClean(repo, lane.lanePath, signal))) {
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
  if (!(await isFullyClean(repo, inventory.lanePath))) {
    warnings.push(`lane ${laneId} retained: worktree is dirty`);
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
): Promise<Record<string, unknown>> {
  const repo = await discoverRepository(run, cwd, signal);
  const taskId = requireIdentifier(request.task_id, "task id");
  const laneId = requireLaneId(request.lane_id);
  const requestedSha = await exactSha(repo, request.sha, "sha", signal);
  const judgedIntegrationSha = await exactSha(
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
  if (laneSha !== requestedSha) {
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
  if (!(await isFullyClean(repo, task.integrationPath, signal))) {
    throw new CollabOpError(
      "dirty_worktree",
      "integration worktree is dirty",
      "Clean the canonical integration worktree before collecting a lane.",
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
  const comparisonMatches = judgedIntegrationSha === integration.tip;

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
    if (!(await isFullyClean(repo, lane.lanePath, signal))) {
      throw new CollabOpError(
        "dirty_worktree",
        "lane worktree is dirty",
        "Clean the lane worktree so it can be synchronized with current integration.",
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
    isActualDirectory(inventory.laneMetadata) &&
    await isFullyClean(repo, inventory.lanePath)
  ) {
    const removed = await repo.git(mutationCwd(repo), [
      "worktree",
      "remove",
      "--force",
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
  const persistBranch = await requireLocalBranch(repo, request.persist, "persist", signal);
  const task = new TaskLayout(repo, taskId);
  const integration = await requireManagedIntegration(controlRepository(repo), task, signal);
  if (!(await isFullyClean(repo, task.integrationPath, signal))) {
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

function laneIsComplete(
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

async function laneDrop(
  run: GitRunner,
  cwd: string,
  request: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<Record<string, unknown>> {
  const repo = await discoverRepository(run, cwd, signal);
  const taskId = requireIdentifier(request.task_id, "task id");
  const laneId = requireLaneId(request.lane_id);
  if (request.abandon !== undefined && typeof request.abandon !== "boolean") {
    throw new CollabOpError("invalid_abandon", "abandon must be a boolean when provided");
  }
  const abandon = request.abandon === true;
  const task = new TaskLayout(repo, taskId);
  const inventory = await laneInventory(repo, task, laneId, signal);
  if (abandon) {
    return laneAbandon(repo, task, laneId, inventory, signal);
  }

  if (!laneCoreIsComplete(inventory)) {
    throw new CollabOpError(
      "lane_inventory_incomplete",
      `managed lane ${taskId}/${laneId} inventory is incomplete`,
      "Restore the complete canonical lane branch and worktree before retrying.",
    );
  }
  if (!laneIsComplete(inventory)) {
    throw new CollabOpError(
      "worktree_identity_mismatch",
      "lane worktree registration does not match its canonical branch and path",
      "Restore the canonical lane worktree registration before retrying.",
    );
  }
  const laneSha = inventory.branchTip as string;
  const integration = await requireManagedIntegration(controlRepository(repo), task, signal);
  if (!(await isFullyClean(repo, inventory.lanePath, signal)) || (await hasMergeOrConflictState(repo, inventory.lanePath, signal))) {
    throw new CollabOpError(
      "dirty_worktree",
      "lane worktree is dirty or has an active merge/conflict state",
      "Clean the lane worktree and finish or abort its merge before retiring it.",
    );
  }
  if (!(await isAncestor(controlRepository(repo), laneSha, integration.tip, signal))) {
    throw new CollabOpError(
      "lane_uncollected",
      "lane contains commits that are not reachable from integration",
      "Collect or abandon the lane before retiring it.",
    );
  }

  const retired = await retireCollectedLane(repo, task, laneId, laneSha);
  if (!retired.cleaned) {
    throw new CollabOpError(
      "git_error",
      retired.warnings[0] || "lane could not be retired",
    );
  }

  const warnings: string[] = [];
  const telemetryWarning = await recordEvent(task, "lane-drop", "success", {
    lane_id: laneId,
    lane_sha: laneSha,
    disposition: "retired",
  });
  if (telemetryWarning) warnings.push(telemetryWarning);
  return {
    ok: true,
    operation: "lane-drop",
    tool_version: TOOL_VERSION,
    lane_sha: laneSha,
    disposition: "retired",
    ...(warnings.length ? { warnings } : {}),
  };
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
      dirty = !(await isFullyClean(repo, inventory.lanePath, signal));
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

async function persistenceIndexClean(
  repo: Repository,
  worktree: string,
  signal?: AbortSignal,
): Promise<boolean> {
  const result = await repo.git(worktree, ["diff", "--cached", "--quiet"], signal);
  if (result.code === 0) return true;
  if (result.code === 1) return false;
  throw new CollabOpError(
    "git_error",
    `could not inspect persistence index: ${result.stderr.trim() || result.stdout.trim()}`,
  );
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

async function rollbackLanding(
  repo: Repository,
  task: TaskLayout,
  persistBranch: { ref: string },
  persistencePath: string,
  beforeSha: string,
  landingSha: string | null,
  previousLanded: string | null,
  landedChanged: boolean,
): Promise<Record<string, unknown>> {
  const evidence: Record<string, unknown> = {
    persistence_sha_before: beforeSha,
    landing_sha: landingSha,
  };
  try {
    const current = await commitAt(controlRepository(repo), persistBranch.ref);
    const records = await worktreeRecords(controlRepository(repo));
    const matches = records.filter((record) => record.branch === persistBranch.ref);
    const persistenceRecord = matches.length === 1 ? matches[0] : undefined;
    const canReset =
      (landingSha === null ? current === beforeSha : current === landingSha) &&
      persistenceRecord?.worktree === persistencePath &&
      (await pathMetadata(persistencePath))?.isDirectory() === true;
    evidence.safe_to_reset = canReset;
    if (canReset) {
      const reset = await repo.git(persistenceRecord!.worktree!, ["reset", "--merge", beforeSha]);
      evidence.reset = reset.code === 0;
      if (reset.code !== 0) evidence.reset_error = boundedGitText(reset.stderr || reset.stdout);
    }
    if (landedChanged) {
      const currentLanded = await commitAt(controlRepository(repo), task.landedRef);
      if (currentLanded !== null) {
        const restored = previousLanded === null
          ? await repo.git(mutationCwd(repo), ["update-ref", "--no-deref", "-d", task.landedRef, currentLanded])
          : await repo.git(mutationCwd(repo), ["update-ref", "--no-deref", task.landedRef, previousLanded, currentLanded]);
        evidence.landed_restored = restored.code === 0;
      }
    }
    const after = await commitAt(controlRepository(repo), persistBranch.ref);
    const afterRecords = await worktreeRecords(controlRepository(repo));
    const afterMatch = afterRecords.filter((record) => record.branch === persistBranch.ref);
    evidence.persistence_sha_after = after;
    evidence.persistence_index_clean =
      afterMatch.length === 1 && afterMatch[0].worktree !== undefined
        ? await persistenceIndexClean(repo, afterMatch[0].worktree)
        : false;
    evidence.restored =
      after === beforeSha &&
      afterMatch.length === 1 &&
      afterMatch[0].HEAD === beforeSha &&
      evidence.persistence_index_clean === true;
  } catch (error) {
    evidence.restored = false;
    evidence.rollback_error = boundedGitText(error instanceof Error ? error.message : String(error));
  }
  return evidence;
}

async function integrationLand(
  run: GitRunner,
  cwd: string,
  request: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<Record<string, unknown>> {
  const repo = await discoverRepository(run, cwd, signal);
  const taskId = requireIdentifier(request.task_id, "task id");
  const persistBranch = await requireLocalBranch(repo, request.persist, "persist", signal);
  const message = requireLandingMessage(request.message, taskId);
  const task = new TaskLayout(repo, taskId);
  const integration = await requireManagedIntegration(controlRepository(repo), task, signal);
  const integrationSha = integration.tip;
  const persistence = await requirePersistenceCheckout(repo, task, persistBranch, signal);
  if (!(await persistenceIndexClean(repo, persistence.record.worktree!, signal))) {
    throw new CollabOpError(
      "dirty_index",
      "persistence index contains staged changes",
      "Commit or unstage persistence index changes before landing.",
    );
  }
  if (!(await isAncestor(controlRepository(repo), persistence.tip, integrationSha, signal))) {
    throw new CollabOpError(
      "stale_persistence",
      "persistence branch is ahead of integration",
      "Reconcile persistence into integration before landing.",
    );
  }
  const previousLanded = await directAuthority(repo, task.landedRef, "landed", signal);
  if (previousLanded === integrationSha) {
    throw new CollabOpError(
      "duplicate_landing",
      "current integration has already been landed",
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
  const changedPaths = await nulPathList(
    repo,
    controlRepository(repo).worktreeRoot,
    ["diff", "--name-only", "-z", persistence.tip, integrationSha, "--"],
    signal,
  );
  const trackedDirt = await nulPathList(
    repo,
    persistence.record.worktree!,
    ["diff", "--name-only", "-z", "--"],
    signal,
  );
  const untrackedDirt = [
    ...(await nulPathList(
      repo,
      persistence.record.worktree!,
      ["ls-files", "--others", "--exclude-standard", "-z", "--"],
      signal,
    )),
    ...(await nulPathList(
      repo,
      persistence.record.worktree!,
      ["ls-files", "--others", "--ignored", "--exclude-standard", "-z", "--"],
      signal,
    )),
  ];
  const integrationPaths = new Set(
    await nulPathList(
      repo,
      controlRepository(repo).worktreeRoot,
      ["ls-tree", "-r", "--name-only", "-z", integrationSha],
      signal,
    ),
  );
  const collisions = [
    ...trackedDirt.filter((dirty) => changedPaths.some((changed) => pathOverlaps(dirty, changed))),
    ...untrackedDirt.filter(
      (dirty) =>
        changedPaths.some((changed) => pathOverlaps(dirty, changed)) ||
        [...integrationPaths].some((pathname) => pathOverlaps(dirty, pathname)),
    ),
  ];
  if (collisions.length > 0) {
    throw new CollabOpError(
      "path_collision",
      "existing persistence dirt collides with the integration tree transition",
      "Move or clean the colliding persistence paths before landing.",
      { paths: [...new Set(collisions)].slice(0, 32) },
    );
  }

  let landingSha: string | null = null;
  let landedChanged = false;
  try {
    const checkout = await repo.git(
      persistence.record.worktree!,
      ["checkout", "--no-overlay", integrationSha, "--", ...changedPaths],
      signal,
    );
    if (checkout.code !== 0) {
      throw new CollabOpError(
        "git_error",
        `Git command failed: ${checkout.stderr.trim() || checkout.stdout.trim()}`,
      );
    }
    const commit = await repo.git(
      persistence.record.worktree!,
      ["commit", "-m", message, "-m", `Task: ${taskId}\nLanded: ${integrationSha}`],
      signal,
    );
    if (commit.code !== 0) {
      throw new CollabOpError(
        "git_error",
        `Git command failed: ${commit.stderr.trim() || commit.stdout.trim()}`,
      );
    }
    landingSha = await commitAt(controlRepository(repo), persistBranch.ref, signal);
    if (landingSha === null || (await treeAt(repo, landingSha, signal)) !== integrationTree) {
      throw new CollabOpError(
        "git_error",
        "landing commit did not preserve the integration tree",
      );
    }
    if (!(await landingMessageMatches(repo, landingSha, message, taskId, integrationSha))) {
      throw new CollabOpError(
        "git_error",
        "landing commit message did not match the required subject and trailers",
      );
    }
    await requireGit(
      repo.git,
      mutationCwd(repo),
      [
        "update-ref",
        "--no-deref",
        task.landedRef,
        integrationSha,
        previousLanded ?? "0".repeat(integrationSha.length),
      ],
      signal,
    );
    landedChanged = true;
  } catch (error) {
    const rollback = await rollbackLanding(
      repo,
      task,
      persistBranch,
      persistence.record.worktree!,
      persistence.tip,
      landingSha,
      previousLanded,
      landedChanged,
    );
    throw new CollabOpError(
      "git_error",
      error instanceof Error ? error.message : String(error),
      undefined,
      { rollback },
    );
  }

  const warnings: string[] = [];
  const telemetryWarning = await recordEvent(task, "integration-land", "success", {
    integration_sha: integrationSha,
    persistence_sha: landingSha,
    landed_sha: integrationSha,
  });
  if (telemetryWarning) warnings.push(telemetryWarning);
  return {
    ok: true,
    operation: "integration-land",
    tool_version: TOOL_VERSION,
    integration_sha: integrationSha,
    persistence_sha: landingSha,
    landed_sha: integrationSha,
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

async function writeRemovalReport(
  task: TaskLayout,
  outputDir: string,
  facts: Record<string, unknown>,
): Promise<{ reportPath: string; telemetryPath: string }> {
  const destination = path.resolve(task.repo.controlRoot, outputDir);
  const metadata = await pathMetadata(destination);
  if (metadata?.isSymbolicLink() || (metadata !== null && !metadata.isDirectory())) {
    throw new CollabOpError("report_collision", "report destination is not a regular directory");
  }
  await mkdir(destination, { recursive: true });
  const reportPath = path.join(destination, "collab-report.json");
  const telemetryPath = path.join(destination, "collab-telemetry.jsonl");
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
  const baseSha = await commitAt(controlRepository(task.repo), task.integrationBaseRef);
  const integrationSha = await commitAt(
    controlRepository(task.repo),
    `refs/heads/${task.integrationBranch}`,
  );
  let integrationDiff: Record<string, unknown> | null = null;
  if (baseSha !== null && integrationSha !== null) {
    const commits = Number.parseInt(
      await requireGit(
        task.repo.git,
        mutationCwd(task.repo),
        ["rev-list", "--count", `${baseSha}..${integrationSha}`],
      ),
      10,
    );
    const files = await nulPathList(
      task.repo,
      mutationCwd(task.repo),
      ["diff", "--name-only", "-z", baseSha, integrationSha, "--"],
    );
    integrationDiff = { base_sha: baseSha, integration_sha: integrationSha, commits, files };
  }
  const authorities = {
    landed: await commitAt(controlRepository(task.repo), task.landedRef),
  };
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
    integration_diff: integrationDiff,
    authorities,
    lane_durations: laneDurations,
    task_timing: taskTiming,
    warnings: reportWarnings,
    timeline: events,
  };
  await writeAtomicReportFile(reportPath, `${JSON.stringify(report)}\n`);
  await writeAtomicReportFile(telemetryPath, telemetry);
  return { reportPath, telemetryPath };
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

async function integrationRemove(
  run: GitRunner,
  cwd: string,
  request: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<Record<string, unknown>> {
  const repo = await discoverRepository(run, cwd, signal);
  const taskId = requireIdentifier(request.task_id, "task id");
  const task = new TaskLayout(repo, taskId);
  const abandon = request.abandon === true;
  if (request.abandon !== undefined && typeof request.abandon !== "boolean") {
    throw new CollabOpError("invalid_abandon", "abandon must be a boolean when provided");
  }
  const outputValue = request.output_dir;
  const noReport = request.no_report === true;
  if ((outputValue !== undefined && noReport) || (outputValue === undefined && !noReport)) {
    throw new CollabOpError(
      "invalid_report_choice",
      "choose exactly one of output_dir or no_report",
      "Pass a report destination or set no_report to true.",
    );
  }
  if (outputValue !== undefined && (typeof outputValue !== "string" || outputValue.length === 0)) {
    throw new CollabOpError("invalid_report_choice", "output_dir must be a non-empty path");
  }

  const inventory = await taskInventory(controlRepository(repo), task, signal);
  const laneIds = removalLaneIds(task, inventory.ownedBranches);
  const integrationTip = await commitAt(controlRepository(repo), `refs/heads/${task.integrationBranch}`, signal);
  const baseSha = await commitAt(controlRepository(repo), task.integrationBaseRef, signal);
  if (integrationTip === null || baseSha === null) {
    throw new CollabOpError("task_state_invalid", `managed task ${taskId} is missing its integration branch or base ref`);
  }

  if (!abandon) {
    const integration = await requireManagedIntegration(controlRepository(repo), task, signal);
    const persistenceTarget = await symbolicRefTarget(controlRepository(repo), task.persistenceRef, signal);
    if (persistenceTarget === null || !persistenceTarget.startsWith("refs/heads/")) {
      throw new CollabOpError("task_state_invalid", "persistence symbolic ref is missing or invalid");
    }
    await requirePersistenceCheckout(
      repo,
      task,
      { name: persistenceTarget.slice("refs/heads/".length), ref: persistenceTarget },
      signal,
    );
    if (!(await isFullyClean(repo, task.integrationPath, signal)) || (await hasMergeOrConflictState(repo, task.integrationPath, signal))) {
      throw new CollabOpError("dirty_worktree", "integration worktree is dirty or conflicted");
    }
    if (laneIds.length > 0) {
      throw new CollabOpError("active_lanes", "managed lanes are still active");
    }
    const unexpectedRegistrations = inventory.registeredUnderRoot.filter(
      (record) => record.worktree !== task.integrationPath,
    );
    if (unexpectedRegistrations.length > 0) {
      throw new CollabOpError("task_inventory_incomplete", "managed task worktree inventory is incomplete");
    }
    const landed = await directAuthority(repo, task.landedRef, "landed", signal);
    const baseTree = await treeAt(repo, baseSha, signal);
    const integrationTree = await treeAt(repo, integration.tip, signal);
    const unchanged = baseTree === integrationTree;
    if (!unchanged && landed !== integration.tip) {
      throw new CollabOpError("task_not_ready", "integration is neither reverted to base nor landed");
    }
    const allowedRefs = new Set([
      task.integrationBaseRef,
      task.persistenceRef,
      task.landedRef,
    ]);
    if (inventory.ownedRefs.some((name) => !allowedRefs.has(name))) {
      throw new CollabOpError("task_inventory_incomplete", "managed task refs contain unknown resources");
    }
    const facts = {
      integration_sha: integration.tip,
      base_sha: baseSha,
      landed_sha: landed,
      lanes: [],
      warnings: unchanged ? ["task reverted to its integration base"] : [],
    };
    const report = outputValue === undefined ? null : await writeRemovalReport(task, outputValue as string, facts);
    const removalError = await removeIntegrationWorktree(repo, task);
    if (removalError) throw new CollabOpError("git_error", removalError);
    await requireGit(repo.git, mutationCwd(repo), ["update-ref", "--no-deref", "-d", `refs/heads/${task.integrationBranch}`, integration.tip]);
    for (const ref of [task.integrationBaseRef, task.landedRef]) {
      const value = await commitAt(controlRepository(repo), ref);
      if (value !== null) await requireGit(repo.git, mutationCwd(repo), ["update-ref", "--no-deref", "-d", ref, value]);
    }
    if (persistenceTarget !== null) await requireGit(repo.git, mutationCwd(repo), ["symbolic-ref", "--delete", task.persistenceRef]);
    await removeEmptyDirectory(path.join(task.root, "lanes"));
    await removeEmptyDirectory(task.root);
    await removeEmptyDirectory(path.join(repo.controlRoot, ".agent_state", "worktrees"));
    const warnings = [...(facts.warnings as string[])];
    const telemetryWarning = await recordEvent(task, "integration-remove", "success", facts);
    if (telemetryWarning) warnings.push(telemetryWarning);
    return {
      ok: true,
      operation: "integration-remove",
      tool_version: TOOL_VERSION,
      ...(report ? { report_dir: path.dirname(report.reportPath) } : {}),
      ...(warnings.length ? { warnings } : {}),
    };
  }

  const warnings: string[] = [];
  const report = outputValue === undefined
    ? null
    : await writeRemovalReport(task, outputValue as string, { disposition: "abandoned", warnings: [] });
  for (const laneId of laneIds) {
    try {
      const lane = await laneInventory(repo, task, laneId, signal);
      const pathResult = await retireLaneWorktree(repo, lane, true);
      warnings.push(...pathResult.warnings.map((warning) => `lane ${laneId}: ${warning}`));
      if (lane.branchNames.length === 1 && lane.branchNames[0] === lane.branchRef && lane.branchTip !== null) {
        const result = await repo.git(mutationCwd(repo), ["update-ref", "--no-deref", "-d", lane.branchRef, lane.branchTip]);
        if (result.code !== 0) warnings.push(`lane ${laneId}: branch retained`);
      }
    } catch (error) {
      warnings.push(`lane ${laneId}: ${boundedGitText(error instanceof Error ? error.message : String(error))}`);
    }
  }
  const integrationBranchRef = `refs/heads/${task.integrationBranch}`;
  const integrationRecords = (await worktreeRecords(controlRepository(repo), signal)).filter(
    (record) => record.branch === integrationBranchRef,
  );
  if (
    integrationRecords.length === 1 &&
    integrationRecords[0].worktree === task.integrationPath &&
    isActualDirectory(await pathMetadata(task.integrationPath))
  ) {
    if (await isFullyClean(repo, task.integrationPath, signal)) {
      const integrationRemoval = await removeIntegrationWorktree(repo, task);
      if (integrationRemoval) warnings.push(integrationRemoval);
    } else {
      warnings.push("integration retained: worktree is dirty");
    }
  } else {
    warnings.push("integration worktree registration is incomplete or unsafe; path preserved");
  }
  const remainingIntegrationRecords = (await worktreeRecords(controlRepository(repo), signal)).filter(
    (record) => record.branch === integrationBranchRef,
  );
  if (remainingIntegrationRecords.length > 0) {
    warnings.push("integration branch retained: worktree registration remains");
  } else {
    const branchNames = await refNames(controlRepository(repo), integrationBranchRef, signal);
    if (branchNames.length === 1 && branchNames[0] === integrationBranchRef) {
      const tip = await commitAt(controlRepository(repo), integrationBranchRef, signal);
      const result = tip === null
        ? await repo.git(mutationCwd(repo), ["update-ref", "--no-deref", "-d", integrationBranchRef])
        : await repo.git(mutationCwd(repo), ["update-ref", "--no-deref", "-d", integrationBranchRef, tip]);
      if (result.code !== 0) warnings.push("integration branch retained");
    }
  }
  if (await symbolicRefTarget(controlRepository(repo), task.persistenceRef, signal)) {
    const result = await repo.git(mutationCwd(repo), ["symbolic-ref", "--delete", task.persistenceRef]);
    if (result.code !== 0) warnings.push("persistence symbolic ref retained");
  }
  for (const ref of [task.integrationBaseRef, task.landedRef]) {
    const names = await refNames(controlRepository(repo), ref, signal);
    if (names.length === 1 && names[0] === ref) {
      const value = await commitAt(controlRepository(repo), ref, signal);
      const result = value === null
        ? await repo.git(mutationCwd(repo), ["update-ref", "--no-deref", "-d", ref])
        : await repo.git(mutationCwd(repo), ["update-ref", "--no-deref", "-d", ref, value]);
      if (result.code !== 0) warnings.push(`ref retained: ${ref}`);
    }
  }
  await removeEmptyDirectory(path.join(task.root, "lanes"));
  await removeEmptyDirectory(task.root);
  await removeEmptyDirectory(path.join(repo.controlRoot, ".agent_state", "worktrees"));
  const facts = { disposition: "abandoned", warnings: warnings.slice(0, 32) };
  const telemetryWarning = await recordEvent(task, "integration-remove", "success", facts);
  if (telemetryWarning) warnings.push(telemetryWarning);
  return {
    ok: true,
    operation: "integration-remove",
    tool_version: TOOL_VERSION,
    disposition: "abandoned",
    ...(report ? { report_dir: path.dirname(report.reportPath) } : {}),
    warnings: warnings.slice(0, 33),
  };
}

type MigrationLegacyRef = { ref: string; sha: string };

type MigrationBaseline = {
  integrationSha: string;
  integrationBaseSha: string;
  persistenceTarget: string;
  landedSha: string | null;
  acceptancePresent: boolean;
  acceptanceSha: string | null;
  legacyRefs: MigrationLegacyRef[];
};

type MigrationDescriptor = {
  version: 1;
  task_id: string;
  nonce: string;
  acceptance_present: boolean;
  integration_sha: string;
  integration_base_sha: string;
  persistence_target: string;
  landed_sha: string | null;
  acceptance_sha: string | null;
  legacy_refs: MigrationLegacyRef[];
};

// Exact canonical descriptor key set, in canonical serialization order.
const DESCRIPTOR_KEYS = [
  "version",
  "task_id",
  "nonce",
  "acceptance_present",
  "integration_sha",
  "integration_base_sha",
  "persistence_target",
  "landed_sha",
  "acceptance_sha",
  "legacy_refs",
];

function migrationSentinelRef(taskId: string): string {
  return `refs/orchestrate/${taskId}/migration`;
}

function serializeMigrationDescriptor(descriptor: MigrationDescriptor): string {
  return `${JSON.stringify({
    version: descriptor.version,
    task_id: descriptor.task_id,
    nonce: descriptor.nonce,
    acceptance_present: descriptor.acceptance_present,
    integration_sha: descriptor.integration_sha,
    integration_base_sha: descriptor.integration_base_sha,
    persistence_target: descriptor.persistence_target,
    landed_sha: descriptor.landed_sha,
    acceptance_sha: descriptor.acceptance_sha,
    legacy_refs: descriptor.legacy_refs.map(({ ref, sha }) => ({ ref, sha })),
  })}\n`;
}

async function exactObjectIdPattern(
  repo: Repository,
  signal?: AbortSignal,
): Promise<RegExp> {
  const length = (await repositoryObjectFormat(repo, signal)) === "sha256" ? 64 : 40;
  return new RegExp(`^[0-9a-f]{${length}}$`);
}

// Strict canonical parsing: exact key set and types, exact object-id lengths
// for the repository format, recognized sorted unique legacy refs, consistent
// acceptance identity pairing, and byte-identical canonical serialization
// (duplicate keys, reordered keys, extra whitespace, or trailing content are
// malformed).
async function parseMigrationDescriptor(
  repo: Repository,
  task: TaskLayout,
  content: string,
  signal?: AbortSignal,
): Promise<MigrationDescriptor> {
  const fail = (reason: string, details?: Record<string, unknown>): never => {
    throw new CollabOpError(
      "migration_recovery_required",
      `the migration descriptor for this task is malformed or from an unsupported version: ${reason}`,
      "Inspect and resolve the sentinel namespace only after verifying the task's refs and worktrees.",
      { sentinel: migrationSentinelRef(task.taskId), task_id: task.taskId, ...(details ?? {}) },
    );
  };
  const gitRepo = controlRepository(repo);
  let parsed: unknown;
  try {
    parsed = JSON.parse(content);
  } catch (error) {
    return fail("descriptor is not valid JSON", {
      error: boundedGitText(error instanceof Error ? error.message : String(error)),
    });
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    return fail("descriptor is not a JSON object");
  }
  const raw = parsed as Record<string, unknown>;
  const keys = Object.keys(raw);
  if (
    keys.length !== DESCRIPTOR_KEYS.length ||
    keys.some((key) => !DESCRIPTOR_KEYS.includes(key))
  ) {
    return fail("descriptor key set is not exact", { fields: keys });
  }
  if (raw.version !== 1) {
    return fail("unsupported descriptor version", { version: raw.version });
  }
  if (raw.task_id !== task.taskId) {
    return fail("descriptor task does not match the task", { task_id: raw.task_id });
  }
  if (typeof raw.nonce !== "string" || !UUID_PATTERN.test(raw.nonce)) {
    return fail("nonce is malformed");
  }
  if (typeof raw.acceptance_present !== "boolean") {
    return fail("acceptance_present is not a boolean");
  }
  const exactOid = await exactObjectIdPattern(repo, signal);
  const integrationSha = raw.integration_sha;
  if (typeof integrationSha !== "string" || !exactOid.test(integrationSha)) {
    return fail("integration_sha is not a full object id");
  }
  const integrationBaseSha = raw.integration_base_sha;
  if (typeof integrationBaseSha !== "string" || !exactOid.test(integrationBaseSha)) {
    return fail("integration_base_sha is not a full object id");
  }
  const persistenceTarget = raw.persistence_target;
  if (
    typeof persistenceTarget !== "string" ||
    !persistenceTarget.startsWith("refs/heads/") ||
    (await repo.git(gitRepo.worktreeRoot, ["check-ref-format", persistenceTarget], signal)).code !== 0
  ) {
    return fail("persistence_target is not a valid direct branch ref");
  }
  const landedSha = raw.landed_sha;
  if (landedSha !== null && (typeof landedSha !== "string" || !exactOid.test(landedSha))) {
    return fail("landed_sha is malformed");
  }
  const acceptanceSha = raw.acceptance_sha;
  if (acceptanceSha !== null && (typeof acceptanceSha !== "string" || !exactOid.test(acceptanceSha))) {
    return fail("acceptance_sha is malformed");
  }
  if (raw.acceptance_present !== (acceptanceSha !== null)) {
    return fail("acceptance_present is inconsistent with acceptance_sha");
  }
  const legacyRefsValue = raw.legacy_refs;
  if (!Array.isArray(legacyRefsValue) || legacyRefsValue.length === 0) {
    return fail("legacy_refs must be a non-empty array");
  }
  const laneBasePrefix = `refs/orchestrate/${task.taskId}/`;
  const legacyRefs: MigrationLegacyRef[] = [];
  for (const item of legacyRefsValue) {
    if (typeof item !== "object" || item === null || Array.isArray(item)) {
      return fail("legacy ref entry is not an object");
    }
    const entry = item as Record<string, unknown>;
    const entryKeys = Object.keys(entry);
    if (entryKeys.length !== 2 || !entryKeys.includes("ref") || !entryKeys.includes("sha")) {
      return fail("legacy ref entry key set is not exact");
    }
    const ref = entry.ref;
    const sha = entry.sha;
    if (typeof ref !== "string" || typeof sha !== "string" || !exactOid.test(sha)) {
      return fail("legacy ref entry is malformed");
    }
    const recognized =
      ref === task.acceptedRef ||
      ref === task.acceptanceOpenRef ||
      ref === task.legacyUserAcceptedRef ||
      laneIdFromRef(ref, laneBasePrefix, "/base") !== null;
    if (!recognized) {
      return fail("legacy ref name is not recognized", { ref });
    }
    legacyRefs.push({ ref, sha });
  }
  for (let index = 1; index < legacyRefs.length; index += 1) {
    if (legacyRefs[index].ref <= legacyRefs[index - 1].ref) {
      return fail("legacy refs must be sorted with unique names");
    }
  }
  const openEntry = legacyRefs.find((item) => item.ref === task.acceptanceOpenRef);
  if (raw.acceptance_present !== (openEntry !== undefined)) {
    return fail("acceptance_present is inconsistent with the recorded legacy refs");
  }
  if (acceptanceSha !== null && openEntry !== undefined && openEntry.sha !== acceptanceSha) {
    return fail("acceptance_sha does not match the acceptance-open legacy ref");
  }
  const descriptor: MigrationDescriptor = {
    version: 1,
    task_id: task.taskId,
    nonce: raw.nonce as string,
    acceptance_present: raw.acceptance_present as boolean,
    integration_sha: integrationSha as string,
    integration_base_sha: integrationBaseSha as string,
    persistence_target: persistenceTarget as string,
    landed_sha: landedSha as string | null,
    acceptance_sha: acceptanceSha as string | null,
    legacy_refs: legacyRefs,
  };
  if (serializeMigrationDescriptor(descriptor) !== content) {
    return fail("descriptor is not canonically serialized");
  }
  return descriptor;
}

type MigrationSentinel =
  | { state: "absent" }
  | { state: "exact"; blob: string; content: string; descriptor: MigrationDescriptor }
  | { state: "invalid"; details: Record<string, unknown> };

// The sentinel must be exactly one direct ref to a blob in the migration
// namespace; any colliding, multiple, symbolic, wrong-type, unreadable, or
// malformed resource stops without mutation.
async function inspectMigrationSentinel(
  repo: Repository,
  task: TaskLayout,
  signal?: AbortSignal,
): Promise<MigrationSentinel> {
  const gitRepo = controlRepository(repo);
  const sentinelRef = migrationSentinelRef(task.taskId);
  const snapshot = await refSnapshot(gitRepo, [sentinelRef], signal);
  const names = [...snapshot.keys()].sort();
  if (names.length === 0) return { state: "absent" };
  if (names.length !== 1 || names[0] !== sentinelRef) {
    return { state: "invalid", details: { sentinel: sentinelRef, refs: names.slice(0, 32) } };
  }
  const record = snapshot.get(sentinelRef);
  if (record === undefined || record.symbolicTarget !== null) {
    return { state: "invalid", details: { sentinel: sentinelRef, kind: "symbolic" } };
  }
  const oid = record.object;
  if (oid === null) {
    return { state: "invalid", details: { sentinel: sentinelRef, kind: "unresolvable" } };
  }
  const type = await repo.git(gitRepo.worktreeRoot, ["cat-file", "-t", oid], signal);
  if (type.code !== 0 || type.stdout.trim() !== "blob") {
    return {
      state: "invalid",
      details: {
        sentinel: sentinelRef,
        kind: "wrong-type",
        object: oid,
        type: type.stdout.trim() || null,
      },
    };
  }
  const contentResult = await repo.git(gitRepo.worktreeRoot, ["cat-file", "blob", oid], signal);
  if (contentResult.code !== 0) {
    return { state: "invalid", details: { sentinel: sentinelRef, kind: "unreadable", object: oid } };
  }
  let descriptor: MigrationDescriptor;
  try {
    descriptor = await parseMigrationDescriptor(repo, task, contentResult.stdout, signal);
  } catch (error) {
    if (error instanceof CollabOpError && error.code === "migration_recovery_required") {
      return {
        state: "invalid",
        details: { sentinel: sentinelRef, object: oid, ...(error.details ?? {}) },
      };
    }
    throw error;
  }
  return { state: "exact", blob: oid, content: contentResult.stdout, descriptor };
}

// Live lane detection: any wave branch for the task except the canonical
// integration branch, and any worktree registration under the task root
// except the canonical integration and acceptance paths (and caller-provided
// exclusions).
async function liveLaneViolations(
  repo: Repository,
  task: TaskLayout,
  signal?: AbortSignal,
  extraExclusions: readonly string[] = [],
): Promise<{ branches: string[]; worktrees: string[] }> {
  const gitRepo = controlRepository(repo);
  const wavePrefix = `refs/heads/wave/${task.taskId}`;
  const integrationBranchRef = `refs/heads/${task.integrationBranch}`;
  const waveRefs = await refNames(gitRepo, wavePrefix, signal);
  const branches = waveRefs.filter((name) => name !== integrationBranchRef);
  const records = await worktreeRecords(gitRepo, signal);
  const excluded = new Set<string>([
    task.acceptancePath,
    task.integrationPath,
    ...extraExclusions,
  ]);
  const underRoot = records.filter(
    (record) =>
      record.worktree === task.root ||
      record.worktree?.startsWith(`${task.root}${path.sep}`),
  );
  const worktrees = underRoot
    .filter((record) => {
      if (record.worktree === undefined) return false;
      return ![...excluded].some(
        (candidate) =>
          record.worktree === candidate ||
          record.worktree?.startsWith(`${candidate}${path.sep}`),
      );
    })
    .map((record) => record.worktree ?? "");
  return { branches, worktrees };
}

async function assertNoLiveLanes(
  repo: Repository,
  task: TaskLayout,
  signal?: AbortSignal,
  extraExclusions: readonly string[] = [],
): Promise<void> {
  const violations = await liveLaneViolations(repo, task, signal, extraExclusions);
  if (violations.branches.length > 0 || violations.worktrees.length > 0) {
    throw new CollabOpError(
      "active_lanes",
      "managed lanes are still active",
      "Drop or collect every lane before migrating legacy state.",
      {
        branches: violations.branches.slice(0, 32),
        worktrees: violations.worktrees.slice(0, 32),
      },
    );
  }
}

// Full read-only preflight: exact clean canonical integration custody,
// meaningful base/persistence/landed identities, no live lanes, no unknown
// task ref, registration, or task-root entry, only exact recognized direct
// legacy refs, and the acceptance-open/worktree pair both absent or both
// present at an identical exact OID/path/registration.
async function assessMigrationBaseline(
  repo: Repository,
  task: TaskLayout,
  signal?: AbortSignal,
): Promise<MigrationBaseline> {
  const gitRepo = controlRepository(repo);
  const integration = await requireManagedIntegration(gitRepo, task, signal);
  if (!(await isFullyClean(repo, task.integrationPath, signal))) {
    throw new CollabOpError(
      "dirty_worktree",
      "integration worktree is dirty",
      "Clean the canonical integration worktree before migrating it.",
    );
  }
  if (await hasMergeOrConflictState(repo, task.integrationPath, signal)) {
    throw new CollabOpError(
      "dirty_worktree",
      "integration worktree has an active merge or conflict state",
      "Finish or abort the integration merge before migrating it.",
    );
  }
  const persistenceTarget = await symbolicRefTarget(gitRepo, task.persistenceRef, signal);
  if (
    persistenceTarget === null ||
    !persistenceTarget.startsWith("refs/heads/") ||
    (await repo.git(gitRepo.worktreeRoot, ["check-ref-format", persistenceTarget], signal)).code !== 0
  ) {
    throw new CollabOpError("task_state_invalid", "persistence symbolic ref is missing or invalid");
  }
  const landedSha = await directAuthority(repo, task.landedRef, "landed", signal);

  const orchestratePrefix = `refs/orchestrate/${task.taskId}`;
  const [orchestrateRefs, records] = await Promise.all([
    refNames(gitRepo, orchestratePrefix, signal),
    worktreeRecords(gitRepo, signal),
  ]);
  // Exact recognized direct legacy refs; anything symbolic, blob-pointing,
  // colliding, or unknown refuses without mutation. Canonical integration
  // head is the sole accepted state; legacy accepted values are exact
  // resources to retire, never sources of truth.
  const accepted = await directAuthority(repo, task.acceptedRef, "accepted", signal);
  const acceptanceOpen = await directAuthority(repo, task.acceptanceOpenRef, "acceptance-open", signal);
  const userAccepted = await directAuthority(repo, task.legacyUserAcceptedRef, "user-accepted", signal);
  const laneBaseRefs = orchestrateRefs
    .filter((name) => laneIdFromRef(name, `${orchestratePrefix}/`, "/base") !== null)
    .sort();
  const laneBases: MigrationLegacyRef[] = [];
  for (const ref of laneBaseRefs) {
    const sha = await directAuthority(repo, ref, "lane-base ref", signal);
    laneBases.push({ ref, sha });
  }
  const knownRefs = new Set<string>([
    task.integrationBaseRef,
    task.persistenceRef,
    task.landedRef,
    task.acceptedRef,
    task.acceptanceOpenRef,
    task.legacyUserAcceptedRef,
    ...laneBaseRefs,
  ]);
  for (const name of orchestrateRefs) {
    if (!knownRefs.has(name)) {
      throw new CollabOpError(
        "task_inventory_incomplete",
        "managed task refs contain unrecognized resources",
        undefined,
        { refs: [name] },
      );
    }
  }
  await assertNoLiveLanes(repo, task, signal);

  const legacyRefs = [
    ...(accepted === null ? [] : [{ ref: task.acceptedRef, sha: accepted }]),
    ...(acceptanceOpen === null ? [] : [{ ref: task.acceptanceOpenRef, sha: acceptanceOpen }]),
    ...(userAccepted === null ? [] : [{ ref: task.legacyUserAcceptedRef, sha: userAccepted }]),
    ...laneBases,
  ].sort((left, right) => (left.ref < right.ref ? -1 : left.ref > right.ref ? 1 : 0));

  // Acceptance-open and the canonical detached acceptance worktree must be
  // both absent or both present at an identical exact OID/path/registration.
  const acceptanceRecords = records.filter((record) => record.worktree === task.acceptancePath);
  const acceptanceDescendants = records.filter(
    (record) => record.worktree?.startsWith(`${task.acceptancePath}${path.sep}`),
  );
  const acceptanceMetadata = await pathMetadata(task.acceptancePath);
  const acceptancePresent =
    acceptanceRecords.length > 0 ||
    acceptanceDescendants.length > 0 ||
    acceptanceMetadata !== null;
  let acceptanceSha: string | null = null;
  if (acceptancePresent) {
    const recordedHead = acceptanceRecords[0]?.HEAD ?? null;
    const registrationExact =
      acceptanceRecords.length === 1 &&
      acceptanceDescendants.length === 0 &&
      acceptanceRecords[0].detached === true &&
      acceptanceRecords[0].branch === undefined &&
      typeof recordedHead === "string" &&
      /^[0-9a-f]{40,64}$/.test(recordedHead) &&
      (await commitAt(gitRepo, recordedHead, signal)) === recordedHead &&
      isActualDirectory(acceptanceMetadata);
    if (!registrationExact || acceptanceOpen === null || acceptanceOpen !== recordedHead) {
      throw new CollabOpError(
        "worktree_identity_mismatch",
        "acceptance-open and the canonical detached acceptance worktree must be both present at an identical exact commit",
        "Restore the exact detached acceptance worktree at the acceptance-open subject, or close the gate before migrating.",
        { path: task.acceptancePath },
      );
    }
    if (!(await isFullyClean(repo, task.acceptancePath, signal))) {
      throw new CollabOpError(
        "dirty_worktree",
        "acceptance worktree is dirty",
        "Clean the legacy acceptance worktree before migrating it.",
      );
    }
    if (await hasMergeOrConflictState(repo, task.acceptancePath, signal)) {
      throw new CollabOpError(
        "dirty_worktree",
        "acceptance worktree has an active merge or conflict state",
        "Finish or abort the legacy acceptance worktree merge before migrating it.",
      );
    }
    acceptanceSha = acceptanceOpen;
  } else if (acceptanceOpen !== null) {
    throw new CollabOpError(
      "worktree_identity_mismatch",
      "acceptance-open is present without the canonical acceptance worktree",
      "Restore the exact detached acceptance worktree at the acceptance-open subject, or remove the orphaned gate ref.",
      { ref: task.acceptanceOpenRef },
    );
  }

  const rootEntries = await readdir(task.root);
  for (const entry of rootEntries) {
    if (entry === "integration" || entry === "acceptance") continue;
    if (entry === "lanes") {
      const lanesPath = path.join(task.root, "lanes");
      const lanesMetadata = await pathMetadata(lanesPath);
      if (!isActualDirectory(lanesMetadata) || (await readdir(lanesPath)).length > 0) {
        throw new CollabOpError("task_inventory_incomplete", "lanes path contains unrecognized contents");
      }
      continue;
    }
    throw new CollabOpError(
      "task_inventory_incomplete",
      "managed task resources contain unrecognized entries",
      undefined,
      { entries: [entry] },
    );
  }

  return {
    integrationSha: integration.tip,
    integrationBaseSha: integration.base,
    persistenceTarget,
    landedSha,
    acceptancePresent,
    acceptanceSha,
    legacyRefs,
  };
}

// Write the descriptor as an unreferenced immutable Git blob; a crash here
// leaves only harmless unreachable object data.
async function writeDescriptorBlob(
  repo: Repository,
  task: TaskLayout,
  content: string,
  signal?: AbortSignal,
): Promise<string> {
  const directory = lockDirectory(repo);
  const pathname = path.join(directory, `${task.taskId}.migration-descriptor`);
  await mkdir(directory, { recursive: true, mode: 0o700 });
  const stale = await pathMetadata(pathname);
  if (stale !== null) {
    try {
      await unlink(pathname);
    } catch {
      // A concurrent writer owns the path; the create below fails explicitly.
    }
  }
  const handle = await open(
    pathname,
    fsConstants.O_CREAT | fsConstants.O_EXCL | fsConstants.O_WRONLY | fsConstants.O_NOFOLLOW,
    0o600,
  );
  try {
    await handle.writeFile(content, { encoding: "utf8" });
  } finally {
    await handle.close();
  }
  try {
    const result = await repo.git(mutationCwd(repo), ["hash-object", "-w", pathname], signal);
    if (result.code !== 0) {
      throw new CollabOpError(
        "git_error",
        `could not write the migration descriptor blob: ${boundedGitText(result.stderr || result.stdout) || `exit ${result.code}`}`,
      );
    }
    const blob = result.stdout.trim();
    if (!/^[0-9a-f]{40,64}$/.test(blob)) {
      throw new CollabOpError("git_error", "the migration descriptor blob has an invalid object id");
    }
    return blob;
  } finally {
    try {
      await unlink(pathname);
    } catch {
      // The descriptor file is transient coordination state.
    }
  }
}

function migrationRecoveryError(reason: string, details?: Record<string, unknown>): CollabOpError {
  return new CollabOpError(
    "migration_recovery_required",
    `migration recovery is required: ${reason}`,
    "Resolve the reported state, then re-run integration_migrate to resume or finish.",
    details,
  );
}

// Forward-only resume inventory: every recorded legacy ref absent, fixed
// identities exactly equal to the descriptor, no live lane or unknown ref,
// registration, or task-root resource, and exact clean canonical integration
// custody.
async function assertResumeInventory(
  repo: Repository,
  task: TaskLayout,
  descriptor: MigrationDescriptor,
  signal?: AbortSignal,
): Promise<void> {
  const gitRepo = controlRepository(repo);
  for (const { ref } of descriptor.legacy_refs) {
    if ((await refNames(gitRepo, ref, signal)).length > 0) {
      throw migrationRecoveryError(`legacy ref ${ref} reappeared after the migration transaction`, {
        ref,
      });
    }
  }
  const tip = await commitAt(gitRepo, `refs/heads/${task.integrationBranch}`, signal);
  const base = await commitAt(gitRepo, task.integrationBaseRef, signal);
  const persistenceTarget = await symbolicRefTarget(gitRepo, task.persistenceRef, signal);
  const landed = await directAuthority(repo, task.landedRef, "landed", signal);
  if (
    tip !== descriptor.integration_sha ||
    base !== descriptor.integration_base_sha ||
    persistenceTarget !== descriptor.persistence_target ||
    landed !== descriptor.landed_sha
  ) {
    throw migrationRecoveryError("fixed task identities changed since the migration descriptor", {
      expected: {
        integration_sha: descriptor.integration_sha,
        integration_base_sha: descriptor.integration_base_sha,
        persistence_target: descriptor.persistence_target,
        landed_sha: descriptor.landed_sha,
      },
      observed: {
        integration_sha: tip,
        integration_base_sha: base,
        persistence_target: persistenceTarget,
        landed_sha: landed,
      },
    });
  }
  await assertNoLiveLanes(repo, task, signal);
  const orchestrateRefs = await refNames(gitRepo, `refs/orchestrate/${task.taskId}`, signal);
  const known = new Set<string>([
    task.integrationBaseRef,
    task.persistenceRef,
    task.landedRef,
    migrationSentinelRef(task.taskId),
  ]);
  for (const name of orchestrateRefs) {
    if (!known.has(name)) {
      throw migrationRecoveryError("an unknown managed ref exists", { refs: [name] });
    }
  }
  const rootEntries = await readdir(task.root);
  for (const entry of rootEntries) {
    if (entry === "integration" || entry === "acceptance") continue;
    if (entry === "lanes") {
      const lanesPath = path.join(task.root, "lanes");
      const lanesMetadata = await pathMetadata(lanesPath);
      if (!isActualDirectory(lanesMetadata) || (await readdir(lanesPath)).length > 0) {
        throw migrationRecoveryError("lanes path contains unrecognized contents");
      }
      continue;
    }
    throw migrationRecoveryError("an unknown task-root entry exists", { entries: [entry] });
  }
  const integration = await requireManagedIntegration(gitRepo, task, signal);
  if (
    integration.tip !== descriptor.integration_sha ||
    integration.base !== descriptor.integration_base_sha
  ) {
    throw migrationRecoveryError("canonical integration custody changed since the migration descriptor");
  }
  if (!(await isFullyClean(repo, task.integrationPath, signal))) {
    throw migrationRecoveryError("the canonical integration worktree is dirty");
  }
  // The canonical integration custody must also be free of any active merge
  // or unresolved conflict state (MERGE_HEAD or unmerged index entries). A
  // clean-index in-progress merge would otherwise pass the porcelain check
  // and let migration complete destructively; this is the same refusal the
  // initial preflight applies. assertResumeInventory runs both before
  // acceptance cleanup and again before the sentinel compare-and-swap
  // deletion, so one shared check guards both phases.
  if (await hasMergeOrConflictState(repo, task.integrationPath, signal)) {
    throw migrationRecoveryError(
      "the canonical integration worktree has an active merge or conflict state",
    );
  }
}

// One atomic compare-and-swap ref transaction via git update-ref --stdin with
// prepare/commit: every update applies or none does. A unique transaction file
// per attempt keeps a crashed transaction's input from ever colliding with a
// later one; stale files are inert coordination state. Output is captured to a
// file so an orphaned transaction surviving a crashed parent does not die on a
// closed pipe before its compare-and-swap commits.
async function atomicRefTransaction(
  repo: Repository,
  shell: GitRunner,
  taskId: string,
  updates: readonly { ref: string; newSha: string | null; oldSha: string | null }[],
  signal?: AbortSignal,
): Promise<void> {
  const zero = await zeroOidFor(repo, signal);
  const lines = ["start"];
  for (const { ref, newSha, oldSha } of updates) {
    lines.push(`update ${ref} ${newSha ?? zero} ${oldSha ?? zero}`);
  }
  lines.push("prepare");
  lines.push("commit");
  const directory = lockDirectory(repo);
  const txnPath = path.join(directory, `${taskId}.${process.pid}.${randomUUID()}.txn`);
  const outPath = `${txnPath}.out`;
  await mkdir(directory, { recursive: true, mode: 0o700 });
  const handle = await open(
    txnPath,
    fsConstants.O_CREAT | fsConstants.O_EXCL | fsConstants.O_WRONLY | fsConstants.O_NOFOLLOW,
    0o600,
  );
  try {
    await handle.writeFile(`${lines.join("\n")}\n`, { encoding: "utf8" });
  } finally {
    await handle.close();
  }
  try {
    const result = await shell(
      mutationCwd(repo),
      ["-c", `git update-ref --stdin < "$1" >"$2" 2>&1`, "collab-op", txnPath, outPath],
      signal,
    );
    if (result.code !== 0) {
      let detail = "";
      try {
        detail = (await readFile(outPath, "utf8")).trim();
      } catch {
        // The output file is best-effort diagnostics.
      }
      throw new CollabOpError(
        "git_error",
        `atomic legacy ref transaction failed: ${boundedGitText(detail) || `exit ${result.code}`}`,
      );
    }
  } finally {
    try {
      await unlink(txnPath);
    } catch {
      // The transaction file is ephemeral coordination state.
    }
    try {
      await unlink(outPath);
    } catch {
      // The output file is ephemeral coordination state.
    }
  }
}

// Forward-only cleanup with a committed sentinel: validate the descriptor
// baseline, remove only the exact clean canonical detached acceptance worktree
// without force (or accept already-completed cleanup), re-read the complete
// inventory, then compare-and-swap delete the exact sentinel. Never recreate
// legacy refs. Every dirt, mismatch, partial custody, unknown state, or failed
// removal preserves what remains plus the sentinel and returns
// migration_recovery_required.
async function forwardCleanup(
  repo: Repository,
  shell: GitRunner,
  task: TaskLayout,
  sentinel: { blob: string; descriptor: MigrationDescriptor },
  signal?: AbortSignal,
): Promise<Record<string, unknown>> {
  const gitRepo = controlRepository(repo);
  const descriptor = sentinel.descriptor;
  try {
    await assertResumeInventory(repo, task, descriptor, signal);
    const records = await worktreeRecords(gitRepo, signal);
    const canonicalRegistrations = records.filter(
      (record) =>
        record.worktree === task.acceptancePath ||
        record.worktree?.startsWith(`${task.acceptancePath}${path.sep}`),
    );
    const canonicalMetadata = await pathMetadata(task.acceptancePath);
    if (!descriptor.acceptance_present) {
      // Acceptance-absent mode: the canonical acceptance path and its
      // registrations must remain absent; any occupant is preserved.
      if (canonicalRegistrations.length > 0 || canonicalMetadata !== null) {
        throw migrationRecoveryError(
          "the canonical acceptance path is occupied in acceptance-absent mode; the occupant is preserved",
          {
            path: task.acceptancePath,
            registrations: canonicalRegistrations.slice(0, 16).map((record) => record.worktree),
            entries: canonicalMetadata?.isDirectory()
              ? (await readdir(task.acceptancePath)).slice(0, 16)
              : [],
          },
        );
      }
    } else if (canonicalRegistrations.length === 0 && canonicalMetadata === null) {
      // Cleanup already completed.
    } else {
      const exactRemovable =
        canonicalRegistrations.length === 1 &&
        canonicalRegistrations[0].worktree === task.acceptancePath &&
        canonicalRegistrations[0].detached === true &&
        canonicalRegistrations[0].branch === undefined &&
        canonicalRegistrations[0].HEAD === descriptor.acceptance_sha &&
        isActualDirectory(canonicalMetadata);
      if (!exactRemovable) {
        throw migrationRecoveryError(
          "the canonical acceptance worktree identity does not match the migration descriptor",
          {
            path: task.acceptancePath,
            expected_head: descriptor.acceptance_sha,
            registrations: canonicalRegistrations.map((record) => ({
              worktree: record.worktree,
              HEAD: record.HEAD ?? null,
            })),
          },
        );
      }
      if (!(await isFullyClean(repo, task.acceptancePath, signal))) {
        throw migrationRecoveryError("the canonical acceptance worktree is dirty and is preserved");
      }
      if (await hasMergeOrConflictState(repo, task.acceptancePath, signal)) {
        throw migrationRecoveryError(
          "the canonical acceptance worktree has an active merge or conflict state and is preserved",
        );
      }
      const removal = await repo.git(
        mutationCwd(repo),
        ["worktree", "remove", task.acceptancePath],
        signal,
      );
      if (removal.code !== 0) {
        throw migrationRecoveryError(
          `the canonical acceptance worktree could not be removed without force: ${boundedGitText(removal.stderr || removal.stdout) || `exit ${removal.code}`}`,
        );
      }
    }
    // Re-read the fixed identities, refs, and worktree inventory, and require
    // the canonical acceptance custody absent before deleting the sentinel.
    await assertResumeInventory(repo, task, descriptor, signal);
    const finalRecords = await worktreeRecords(gitRepo, signal);
    const finalRegistrations = finalRecords.filter(
      (record) =>
        record.worktree === task.acceptancePath ||
        record.worktree?.startsWith(`${task.acceptancePath}${path.sep}`),
    );
    if (finalRegistrations.length > 0 || (await pathMetadata(task.acceptancePath)) !== null) {
      throw migrationRecoveryError("canonical acceptance custody remains after cleanup");
    }
    try {
      await atomicRefTransaction(
        repo,
        shell,
        task.taskId,
        [{ ref: migrationSentinelRef(task.taskId), newSha: null, oldSha: sentinel.blob }],
        signal,
      );
    } catch (error) {
      const failure =
        error instanceof CollabOpError
          ? error
          : new CollabOpError("git_error", error instanceof Error ? error.message : String(error));
      throw migrationRecoveryError("the migration sentinel could not be deleted", {
        original_error: describeError(failure),
      });
    }
  } catch (error) {
    if (error instanceof CollabOpError && error.code === "migration_recovery_required") {
      throw error;
    }
    const failure =
      error instanceof CollabOpError
        ? error
        : new CollabOpError("git_error", error instanceof Error ? error.message : String(error));
    throw migrationRecoveryError(`migration could not be resumed: ${failure.message}`, {
      original_error: describeError(failure),
    });
  }
  return {
    ok: true,
    operation: "integration-migrate",
    tool_version: TOOL_VERSION,
    state: "migrated",
    integration_sha: descriptor.integration_sha,
  };
}

function describeError(error: unknown): { code: string; message: string; details?: Record<string, unknown> } {
  if (error instanceof CollabOpError) {
    return {
      code: error.code,
      message: error.message,
      ...(error.details && Object.keys(error.details).length > 0 ? { details: error.details } : {}),
    };
  }
  return { code: "git_error", message: error instanceof Error ? error.message : String(error) };
}

// No sentinel: complete the read-only preflight, write the descriptor as an
// unreferenced blob, then one compare-and-swap ref transaction creates the
// absent sentinel and deletes every recorded legacy ref, and the same
// invocation rolls the committed cleanup forward. Sentinel present: strict
// parse and roll forward only. Malformed, wrong-type, colliding, multiple, or
// inconsistent sentinel resources stop without mutation.
async function migrationRunOrResume(
  repo: Repository,
  shell: GitRunner,
  task: TaskLayout,
  signal?: AbortSignal,
): Promise<Record<string, unknown>> {
  const sentinel = await inspectMigrationSentinel(repo, task, signal);
  if (sentinel.state === "absent") {
    const baseline = await assessMigrationBaseline(repo, task, signal);
    if (baseline.legacyRefs.length === 0) {
      return {
        ok: true,
        operation: "integration-migrate",
        tool_version: TOOL_VERSION,
        state: "already_current",
        integration_sha: baseline.integrationSha,
      };
    }
    const descriptor: MigrationDescriptor = {
      version: 1,
      task_id: task.taskId,
      nonce: randomUUID(),
      acceptance_present: baseline.acceptancePresent,
      integration_sha: baseline.integrationSha,
      integration_base_sha: baseline.integrationBaseSha,
      persistence_target: baseline.persistenceTarget,
      landed_sha: baseline.landedSha,
      acceptance_sha: baseline.acceptanceSha,
      legacy_refs: baseline.legacyRefs.map(({ ref, sha }) => ({ ref, sha })),
    };
    const blob = await writeDescriptorBlob(
      repo,
      task,
      serializeMigrationDescriptor(descriptor),
      signal,
    );
    const updates: { ref: string; newSha: string | null; oldSha: string | null }[] = [
      { ref: migrationSentinelRef(task.taskId), newSha: blob, oldSha: null },
      ...baseline.legacyRefs.map(({ ref, sha }) => ({ ref, newSha: null, oldSha: sha })),
    ];
    // Transaction failure leaves the original refs and worktree intact and no
    // sentinel; there is no rollback. The committed transaction is the only
    // phase change.
    await atomicRefTransaction(repo, shell, task.taskId, updates, signal);
    return forwardCleanup(repo, shell, task, { blob, descriptor }, signal);
  }
  if (sentinel.state === "invalid") {
    throw new CollabOpError(
      "migration_recovery_required",
      "the migration sentinel namespace is malformed, colliding, or inconsistent",
      "Inspect and resolve the sentinel namespace only after verifying the task's refs and worktrees.",
      sentinel.details,
    );
  }
  return forwardCleanup(
    repo,
    shell,
    task,
    { blob: sentinel.blob, descriptor: sentinel.descriptor },
    signal,
  );
}
async function integrationMigrate(
  run: GitRunner,
  shell: GitRunner,
  cwd: string,
  request: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<Record<string, unknown>> {
  const repo = await discoverRepository(run, cwd, signal);
  const taskId = requireIdentifier(request.task_id, "task id");
  const task = new TaskLayout(repo, taskId);
  return withTaskLock(repo, taskId, () => migrationRunOrResume(repo, shell, task, signal));
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

  // Status is read-only: while the exact or malformed sentinel namespace is
  // present it reports only that recovery is required, never descriptor
  // contents.
  let recoveryRequired = false;
  if ((await refNames(repo, `refs/orchestrate/${taskId}/migration`, signal)).length > 0) {
    recoveryRequired = true;
  }

  return {
    tool_version: TOOL_VERSION,
    task_id: taskId,
    ...(recoveryRequired ? { recovery_required: true } : {}),
    integration: { worktree: task.integrationPath, HEAD: integrationHead, stale },
    lanes,
    warnings,
  };
}

const parameters = {
  type: "object",
  additionalProperties: false,
  properties: {
    method: { type: "string", enum: METHODS },
    task_id: { type: "string" },
    source_branch: { type: "string" },
    persist: { type: "string" },
    base_sha: { type: "string" },
    message: { type: "string" },
    output_dir: { type: "string" },
    no_report: { type: "boolean" },
    abandon: { type: "boolean" },
    dry_run: { type: "boolean" },
    lane_id: { type: "string" },
    comment: { type: "string" },
    sha: { type: "string" },
    integration_sha: { type: "string" },
  },
  required: ["method"],
} as const;

export default function collabOpExtension(pi: ExtensionAPI): void {
  const runGit = gitRunner(pi);
  const runShell = shellRunner(pi);
  // Every task-mutating handler (all except status) executes under one shared
  // task-scoped exclusive lock, and refuses while any migration sentinel
  // namespace resource exists; integration_migrate takes the same lock itself
  // so it can resume or finish that migration.
  function taskLocked(
    handler: (
      request: Record<string, unknown>,
      signal: AbortSignal | undefined,
      ctx: ExtensionContext,
    ) => Promise<Record<string, unknown>>,
  ): (
    request: Record<string, unknown>,
    signal: AbortSignal | undefined,
    ctx: ExtensionContext,
  ) => Promise<Record<string, unknown>> {
    return async (request, signal, ctx) => {
      const repo = await discoverRepository(runGit, ctx.cwd, signal);
      const taskId = requireIdentifier(request.task_id, "task id");
      return withTaskLock(repo, taskId, async () => {
        await assertNoMigrationSentinel(repo, taskId, signal);
        return handler(request, signal, ctx);
      });
    };
  }

  const handlers: Record<
    string,
    (
      request: Record<string, unknown>,
      signal: AbortSignal | undefined,
      ctx: ExtensionContext,
    ) => Promise<Record<string, unknown>>
  > = {
    integration_create: taskLocked((request, signal, ctx) =>
      integrationCreate(runGit, ctx.cwd, request, signal),
    ),
    integration_land: taskLocked((request, signal, ctx) =>
      integrationLand(runGit, ctx.cwd, request, signal),
    ),
    integration_remove: taskLocked((request, signal, ctx) =>
      integrationRemove(runGit, ctx.cwd, request, signal),
    ),
    integration_migrate: (request, signal, ctx) =>
      integrationMigrate(runGit, runShell, ctx.cwd, request, signal),
    integration_adopt: taskLocked((request, signal, ctx) =>
      integrationAdopt(runGit, ctx.cwd, request, signal),
    ),
    lane_create: taskLocked((request, signal, ctx) =>
      laneCreate(runGit, ctx.cwd, request, signal),
    ),
    integration_reconcile: taskLocked((request, signal, ctx) =>
      integrationReconcile(runGit, ctx.cwd, request, signal),
    ),
    lane_reconcile: taskLocked((request, signal, ctx) =>
      laneReconcile(runGit, ctx.cwd, request, signal),
    ),
    lane_collect: taskLocked((request, signal, ctx) =>
      laneCollect(runGit, ctx.cwd, request, signal),
    ),
    lane_drop: taskLocked((request, signal, ctx) =>
      laneDrop(runGit, ctx.cwd, request, signal),
    ),
    status: (request, signal, ctx) => status(runGit, ctx.cwd, request.task_id, signal),
  };

  pi.registerTool({
    name: "collab_op",
    label: "Collab operation",
    description: "Operate Orchestrator-gated lanes and the task-local integration, or inspect its status.",
    parameters,
    async execute(_toolCallId, request, signal, _onUpdate, ctx: ExtensionContext) {
      const method = String(request.method ?? "");
      try {
        const handler = handlers[method];
        if (!handler) {
          throw new CollabOpError(
            "method_not_implemented",
            `${method || "requested method"} is not implemented in this extension build`,
          );
        }
        const result = await handler(request, signal, ctx);
        return {
          content: [{ type: "text" as const, text: JSON.stringify(result) }],
          details: result,
        };
      } catch (error) {
        throw new Error(JSON.stringify(errorEnvelope(method || "unknown", error)));
      }
    },
  });
}
