import assert from 'node:assert/strict';
import { mkdtemp, mkdir, readFile, readlink, rm, symlink, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const piPackage = process.env.PI_PACKAGE ?? '/usr/lib/node_modules/@earendil-works/pi-coding-agent/dist/index.js';
const { createJiti } = createRequire(piPackage)('jiti');
const { default: register } = await createJiti(import.meta.url).import(
  fileURLToPath(new URL('../home/.pi/agent/extensions/collab-op/index.ts', import.meta.url)),
);
const base = '1'.repeat(40), accepted = '2'.repeat(40), merged = '3'.repeat(40);
const baseTree = '4'.repeat(40), acceptedTree = '5'.repeat(40), blob = '6'.repeat(40);
const persistRef = 'refs/heads/main', integrationRef = 'refs/heads/wave/demo/integration';
const ok = (stdout = '') => ({ code: 0, stdout, stderr: '' });
const fail = (stderr = '', code = 1) => ({ code, stdout: '', stderr });

// This adapter models Git responses, not Git's filesystem safety. Native Git
// collision/transition observations are a separate gate. Unknown commands fail.
async function fixture(t, options = {}) {
  const root = await mkdtemp(path.join(os.tmpdir(), 'collab-land-contract-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const integration = path.join(root, '.agent_state/worktrees/demo/integration');
  await mkdir(integration, { recursive: true });
  await mkdir(path.join(root, '.git'), { recursive: true });
  if (!options.noContainer) await mkdir(path.join(root, '.agent_state/plans/demo'), { recursive: true });
  const state = { persistence: base, integration: accepted, mergeHead: options.activeMerge ?? false, message: '', synced: false };
  const local = { 'stable.txt': 'unstaged work\n', 'untracked.txt': 'untracked work\n', 'ignored.tmp': 'ignored work\n', ...options.files };
  for (const [name, body] of Object.entries(local)) {
    await mkdir(path.dirname(path.join(root, name)), { recursive: true });
    await writeFile(path.join(root, name), body);
  }
  for (const [name, target] of Object.entries(options.symlinks ?? {})) await symlink(target, path.join(root, name));
  for (const name of options.directories ?? []) await mkdir(path.join(root, name), { recursive: true });
  const calls = [];
  const tools = new Map();
  register({
    registerTool(tool) { tools.set(tool.name, tool); },
    async exec(command, args, { cwd }) {
      assert.equal(command, 'git');
      assert.ok(cwd === root || cwd === integration, `unexpected cwd: ${cwd}`);
      calls.push({ cwd, args });
      const key = args.join(' ');
      if (key === 'rev-parse --show-toplevel') return ok(cwd);
      if (key === 'rev-parse --path-format=absolute --git-common-dir') return ok(path.join(root, '.git'));
      if (key === 'symbolic-ref --quiet refs/orchestrate/demo/persistence') return ok(persistRef);
      if (['symbolic-ref --quiet ' + persistRef, 'symbolic-ref --quiet ' + integrationRef,
        'symbolic-ref --quiet refs/orchestrate/demo/integration/base'].includes(key)) return fail();
      if (key === 'check-ref-format ' + persistRef) return ok();
      if (key === 'worktree list --porcelain') return ok(
        `worktree ${root}\nHEAD ${state.persistence}\nbranch ${persistRef}\n\n` +
        `worktree ${integration}\nHEAD ${state.integration}\nbranch ${integrationRef}\n`,
      );
      if (key === 'rev-parse --verify --quiet MERGE_HEAD') return state.mergeHead ? ok(accepted) : fail();
      if (key === 'ls-files --unmerged') return ok(options.conflict ? `100644 ${blob} 2\tstable.txt\n` : '');
      if (key === `diff --no-renames --name-only -z ${base} ${accepted} --`) return ok((options.changed ?? ['accepted.txt']).join('\0') + '\0');
      if (key === 'diff --name-only -z --') return ok((options.dirty ?? ['stable.txt']).join('\0') + '\0');
      if (key === `ls-tree -r --name-only -z ${base}`) return ok(['stable.txt', ...(options.tracked ?? [])].join('\0') + '\0');
      if (key === 'ls-tree -r -z HEAD') return ok(`100644 blob ${blob}\tstable.txt\0`);
      if (key === 'ls-files --cached --stage -z') {
        const clean = `100644 ${blob} 0\tstable.txt\0`;
        switch (options.index) {
          case 'addition': return ok(clean + `100644 ${blob} 0\tnew.txt\0`);
          case 'modification': return ok(`100644 ${accepted} 0\tstable.txt\0`);
          case 'deletion': return ok();
          case 'mode': return ok(`100755 ${blob} 0\tstable.txt\0`);
          case 'intent-to-add': return ok(clean + '100644 e69de29bb2d1d6434b8b29ae775ad8c2e48c5391 0\tnew.txt\0');
          default: return ok(clean);
        }
      }
      if (key === `merge-base --is-ancestor ${base} ${accepted}`) return options.stale ? fail() : ok();
      if (args.length === 4 && args.slice(0, 3).join(' ') === 'rev-parse --verify --quiet') {
        const values = {
          [`${persistRef}^{commit}`]: state.persistence,
          [`${integrationRef}^{commit}`]: state.integration,
          'refs/orchestrate/demo/integration/base^{commit}': options.stale ? accepted : base,
          [`${base}^{tree}`]: baseTree,
          [`${accepted}^{tree}`]: options.noTreeChange ? baseTree : acceptedTree,
          [`${merged}^{tree}`]: options.badTree ? baseTree : acceptedTree,
        };
        if (Object.hasOwn(values, args[3])) return ok(values[args[3]]);
      }
      if (key === `merge-base --is-ancestor ${accepted} ${accepted}`) return ok();
      if (args[0] === 'merge') {
        assert.equal(cwd, root);
        const messageIndex = args.indexOf('-m');
        assert.notEqual(messageIndex, -1);
        state.message = args[messageIndex + 1];
        if (options.mergeError) {
          state.mergeHead = options.hookFailure ?? false;
          return fail(options.mergeError);
        }
        state.persistence = merged;
        return ok('Merge made by the ort strategy.');
      }
      if (key === `rev-list --parents -n 1 ${merged}`) return ok(
        options.badParents ? `${merged} ${accepted} ${base}` : `${merged} ${base} ${accepted}`,
      );
      if (key === `show -s --format=%B ${merged}`) return ok(options.badMessage ? 'hook changed message\n' : state.message + '\n');
      if (key === `update-ref --no-deref ${integrationRef} ${merged} ${accepted}`) {
        if (options.publishFailure) return fail('cannot lock integration ref');
        state.integration = merged;
        return ok();
      }
      if (key === `reset --hard ${merged}` && cwd === integration) {
        if (options.resetFailure) return fail('cannot update integration worktree');
        state.synced = true;
        return ok();
      }
      throw new Error(`Unmodeled Git command: ${key}`);
    },
  });
  return {
    state, calls,
    async land(message) {
      const result = await tools.get('collab_integration').execute('test', {
        repo: root, action: 'land', task_id: 'demo', ...(message === undefined ? {} : { message }),
      }, undefined, undefined, { cwd: root });
      assert.deepEqual(JSON.parse(result.content[0].text), result.details);
      return result.details;
    },
    async localsPreserved() {
      for (const [name, body] of Object.entries(local)) assert.equal(await readFile(path.join(root, name), 'utf8'), body);
      for (const [name, target] of Object.entries(options.symlinks ?? {})) assert.equal(await readlink(path.join(root, name)), target);
    },
  };
}

async function errorFrom(operation, code) {
  try { await operation(); } catch (error) {
    const envelope = JSON.parse(error.message);
    assert.equal(envelope.ok, false);
    assert.equal(envelope.tool_version, 1);
    assert.equal(envelope.error.code, code);
    assert.ok(envelope.error.repair);
    return envelope.error;
  }
  assert.fail('expected the registered tool to throw an error envelope');
}

for (const message of [undefined, 'Accept local-state preservation']) {
  test(`lands with local files and exact native merge request (${message ?? 'default message'})`, async t => {
    const f = await fixture(t);
    assert.deepEqual(await f.land(message), { ok: true, tool_version: 1 });
    assert.equal(f.state.persistence, merged);
    assert.equal(f.state.integration, merged);
    assert.equal(f.state.synced, true);
    const merge = f.calls.find(call => call.args[0] === 'merge');
    assert.deepEqual(merge.args, ['merge', '--no-ff', '--no-overwrite-ignore', '-m',
      `${message ?? 'Land demo'}\n\nTask: demo\nLanded: ${accepted}`, accepted]);
    await f.localsPreserved();
  });
}

for (const [name, options, paths] of [
  ['tracked overlap', { changed: ['stable.txt'] }, ['stable.txt']],
  ['untracked exact', { changed: ['untracked.txt'] }, ['untracked.txt']],
  ['ignored exact', { changed: ['ignored.tmp'] }, ['ignored.tmp']],
  ['untracked ancestor', { changed: ['ignored.tmp/child'] }, ['ignored.tmp']],
  ['directory to file', { changed: ['pair/base.txt', 'pair'], tracked: ['pair/base.txt'], files: { 'pair/base.txt': 'tracked', 'pair/local.tmp': 'local' } }, ['pair/local.tmp']],
  ['local directory replacing changed leaf', { changed: ['pair', 'pair/new.txt'], tracked: ['pair'], files: { 'pair/local.tmp': 'local' } }, ['pair']],
  ['local directory replacing deleted leaf', { changed: ['pair'], tracked: ['pair'], files: { 'pair/local.tmp': 'local' } }, ['pair']],
  ['symlink ancestor', { changed: ['link/new.txt'], symlinks: { link: 'missing-target' } }, ['link']],
  ['symlink descendant', { changed: ['pair'], symlinks: { pair: 'ignored.tmp' } }, ['pair']],
  ['empty local directory', { changed: ['empty'], directories: ['empty'] }, ['empty/']],
]) {
  test(`preflight protects ${name}`, async t => {
    const f = await fixture(t, options);
    const error = await errorFrom(() => f.land(), 'path_collision');
    assert.deepEqual(error.details.paths, paths);
    assert.equal(f.state.persistence, base);
    assert.equal(f.state.integration, accepted);
    await f.localsPreserved();
  });
}
for (const [name, options] of [
  ['unrelated directory replacement', { tracked: ['pair'], files: { 'pair/local.tmp': 'local' } }],
  ['untracked sibling of new file', { changed: ['pair/new.txt'], files: { 'pair/local.tmp': 'local' } }],
  ['deleted tracked child with local sibling', { changed: ['pair/base.txt'], tracked: ['pair/base.txt'], files: { 'pair/base.txt': 'tracked', 'pair/local.tmp': 'local' } }],
  ['clean tracked change', { changed: ['stable.txt'], dirty: [] }],
]) {
  test(`admits ${name}`, async t => {
    const f = await fixture(t, options);
    assert.equal((await f.land()).ok, true);
    assert.equal(f.state.integration, merged);
    await f.localsPreserved();
  });
}

for (const index of ['addition', 'modification', 'deletion', 'mode', 'intent-to-add']) {
  test(`refuses ${index} in index before merge`, async t => {
    const f = await fixture(t, { index });
    await errorFrom(() => f.land(), 'dirty_index');
    assert.equal(f.state.persistence, base);
    assert.equal(f.state.integration, accepted);
    await f.localsPreserved();
  });
}
for (const [options, code] of [
  [{ activeMerge: true }, 'dirty_worktree'], [{ conflict: true }, 'dirty_worktree'],
  [{ stale: true }, 'stale_persistence'], [{ noTreeChange: true }, 'no_tree_change'],
]) {
  test(`refuses preflight ${JSON.stringify(options)}`, async t => {
    const f = await fixture(t, options);
    await errorFrom(() => f.land(), code);
    assert.equal(f.state.persistence, base);
    assert.equal(f.state.integration, accepted);
    await f.localsPreserved();
  });
}
for (const mergeError of [
  'Your local changes to stable.txt would be overwritten by merge.',
  'The following untracked working tree files would be overwritten by merge: untracked.txt',
  'The following untracked working tree files would be overwritten by merge: ignored.tmp',
]) {
  test(`surfaces native refusal: ${mergeError}`, async t => {
    const f = await fixture(t, { mergeError });
    const error = await errorFrom(() => f.land(), 'git_error');
    assert.equal(error.details.stderr, mergeError);
    assert.equal(error.details.code, 1);
    assert.equal(f.state.persistence, base);
    assert.equal(f.state.integration, accepted);
    await f.localsPreserved();
  });
}

test('hook failure exposes native output and retains resulting merge state', async t => {
  const f = await fixture(t, { hookFailure: true, mergeError: 'pre-merge hook failed' });
  const error = await errorFrom(() => f.land(), 'git_error');
  assert.equal(error.details.stderr, 'pre-merge hook failed');
  assert.equal(f.state.mergeHead, true);
  assert.equal(f.state.persistence, base);
  assert.equal(f.state.integration, accepted);
  await f.localsPreserved();
});
for (const fault of ['badTree', 'badParents', 'badMessage', 'publishFailure', 'resetFailure']) {
  test(`reports ${fault} without claiming rollback`, async t => {
    const f = await fixture(t, { [fault]: true });
    const error = await errorFrom(() => f.land(), 'git_error');
    assert.equal(error.details.merge_sha ?? error.details.persistence_sha, merged);
    assert.equal(f.state.persistence, merged);
    assert.equal(f.state.integration, fault === 'resetFailure' ? merged : accepted);
    assert.equal(f.state.synced, false);
    if (fault === 'badTree') assert.deepEqual(
      [error.details.expected_tree, error.details.actual_tree], [acceptedTree, baseTree],
    );
    if (fault === 'badParents') assert.deepEqual(error.details.actual_parents, [accepted, base]);
    await f.localsPreserved();
  });
}

test('missing telemetry container warns without preventing landing', async t => {
  const f = await fixture(t, { noContainer: true });
  const result = await f.land();
  assert.equal(result.ok, true);
  assert.match(result.warnings[0], /task container is unavailable/);
  assert.equal(f.state.integration, merged);
});
for (const message of ['', 'line\nbreak', 'a'.repeat(201)]) {
  test(`invalid subject is refused (${message.length} characters)`, async t => {
    const f = await fixture(t);
    await errorFrom(() => f.land(message), 'invalid_message');
    assert.equal(f.state.persistence, base);
    assert.equal(f.state.integration, accepted);
  });
}
