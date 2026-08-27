import fs from 'node:fs/promises'

const [workflowPath, argsJson, scenarioName = 'available'] = process.argv.slice(2)
if (!workflowPath || argsJson === undefined) {
  throw new Error('usage: harness WORKFLOW_PATH ARGS_JSON [scenario]')
}

const source = await fs.readFile(workflowPath, 'utf8')
const metaMatch = source.match(/^export const meta = ([\s\S]*?\n})\n/)
if (!metaMatch) throw new Error('workflow metadata declaration was not found')

const meta = Function(`return (${metaMatch[1]})`)()
const body = source.slice(metaMatch[0].length)
const calls = []
const logs = []
const phases = []

function completedWorker(
  summary = 'The bounded behavior matches the supplied Interface.',
) {
  return {
    outcome: 'COMPLETED',
    residualRisks: [],
  }
}

function blockedWorker(
  blocker = 'The bounded change cannot be completed within the supplied authority.',
) {
  return {
    outcome: 'BLOCKED',
    residualRisks: [],
    blocker,
  }
}

function decisionWorker() {
  return {
    outcome: 'NEEDS_DECISION',
    residualRisks: [],
    decision: {
      why: 'The requested behavior requires an unapproved seam decision.',
      question: 'Which bounded seam should carry this behavior?',
    },
  }
}

function passReviewer() {
  return {
    verdict: 'PASS',
    residualRisks: [],
  }
}

function blockedReviewer(where = 'reviewed behavior') {
  return {
    verdict: 'BLOCKED',
    blockers: [
      {
        where,
        why: 'The protected lane does not satisfy one supplied expectation.',
        howToFix: 'Correct the bounded behavior before another review.',
        trigger: 'A reviewer inspects the delegated scope and finds the gap directly reachable.',
      },
    ],
    residualRisks: [],
  }
}

function decisionReviewer(includeSuggestion = true) {
  const decision = {
    why: 'The review found an architecture question outside mechanical correction.',
    question: 'Should the Orchestrator authorize a seam change?',
  }
  if (includeSuggestion) decision.suggestion = 'Keep the decision with the Orchestrator.'
  return {
    verdict: 'NEEDS_DECISION',
    decision,
    residualRisks: [],
  }
}

function namedScenario(name) {
  switch (name) {
    case 'available':
    case 'happy':
    case 'reviewer-pass':
      return { steps: [completedWorker(), passReviewer()] }
    case 'worker-blocked':
      return { steps: [blockedWorker()] }
    case 'worker-needs-decision':
      return { steps: [decisionWorker()] }
    case 'reviewer-blocked':
      return { steps: [completedWorker(), blockedReviewer()] }
    case 'reviewer-blocked-missing-trigger':
      return {
        steps: [
          completedWorker(),
          {
            verdict: 'BLOCKED',
            blockers: [
              {
                where: 'reviewed behavior',
                why: 'The protected lane does not satisfy one supplied expectation.',
                howToFix: 'Correct the bounded behavior before another review.',
              },
            ],
            residualRisks: [],
          },
        ],
      }
    case 'reviewer-needs-decision':
      return { steps: [completedWorker(), decisionReviewer()] }
    case 'reviewer-needs-decision-no-suggestion':
      return { steps: [completedWorker(), decisionReviewer(false)] }
    case 'correction-rereview-pass':
      return {
        steps: [
          completedWorker(),
          blockedReviewer(),
          completedWorker('The bounded correction matches the supplied Interface.'),
          passReviewer(),
        ],
      }
    case 'correction-rereview-needs-decision':
      return {
        steps: [
          completedWorker(),
          blockedReviewer(),
          completedWorker('The bounded correction matches the supplied Interface.'),
          decisionReviewer(),
        ],
      }
    case 'correction-rereview-blocked':
      return {
        steps: [
          completedWorker(),
          blockedReviewer(),
          completedWorker('The bounded correction matches the supplied Interface.'),
          blockedReviewer('rereviewed behavior'),
        ],
      }
    case 'correction-worker-blocked':
      return {
        steps: [
          completedWorker(),
          blockedReviewer(),
          blockedWorker('The bounded correction remains blocked within the supplied authority.'),
        ],
      }
    case 'correction-worker-needs-decision':
      return { steps: [completedWorker(), blockedReviewer(), decisionWorker()] }
    case 'correction-null':
      return { steps: [completedWorker(), blockedReviewer(), null] }
    case 'correction-interrupt':
      return {
        steps: [completedWorker(), blockedReviewer(), { throw: 'interrupt' }],
      }
    case 'correction-runtime-error':
      return {
        steps: [completedWorker(), blockedReviewer(), { throw: 'error' }],
      }
    case 'correction-capability-failure':
      return {
        steps: [completedWorker(), blockedReviewer(), { throw: 'capability' }],
      }
    case 'correction-invalid':
      return {
        steps: [
          completedWorker(),
          blockedReviewer(),
          {
            outcome: 'COMPLETED',
            residualRisks: [],
            structuredOutput: completedWorker(),
          },
        ],
      }
    case 'rereview-null':
      return {
        steps: [
          completedWorker(),
          blockedReviewer(),
          completedWorker('The bounded correction matches the supplied Interface.'),
          null,
        ],
      }
    case 'rereview-interrupt':
      return {
        steps: [
          completedWorker(),
          blockedReviewer(),
          completedWorker('The bounded correction matches the supplied Interface.'),
          { throw: 'interrupt' },
        ],
      }
    case 'rereview-runtime-error':
      return {
        steps: [
          completedWorker(),
          blockedReviewer(),
          completedWorker('The bounded correction matches the supplied Interface.'),
          { throw: 'error' },
        ],
      }
    case 'rereview-capability-failure':
      return {
        steps: [
          completedWorker(),
          blockedReviewer(),
          completedWorker('The bounded correction matches the supplied Interface.'),
          { throw: 'capability' },
        ],
      }
    case 'rereview-invalid':
      return {
        steps: [
          completedWorker(),
          blockedReviewer(),
          completedWorker('The bounded correction matches the supplied Interface.'),
          { verdict: 'PASS', residualRisks: [], blockers: [] },
        ],
      }
    case 'null':
    case 'null-worker':
      return { steps: [null] }
    case 'null-reviewer':
      return { steps: [completedWorker(), null] }
    case 'interrupt':
    case 'interrupt-worker':
      return { steps: [{ throw: 'interrupt' }] }
    case 'interrupt-reviewer':
      return { steps: [completedWorker(), { throw: 'interrupt' }] }
    case 'runtime-error':
    case 'error':
      return { steps: [{ throw: 'error' }] }
    case 'runtime-error-reviewer':
      return { steps: [completedWorker(), { throw: 'error' }] }
    case 'capability-failure':
    case 'capability':
      return { steps: [{ throw: 'capability' }] }
    case 'capability-failure-reviewer':
    case 'capability-reviewer':
      return { steps: [completedWorker(), { throw: 'capability' }] }
    case 'invalid-worker':
      return {
        steps: [
          {
            outcome: 'COMPLETED',
            residualRisks: [],
            structuredOutput: completedWorker(),
          },
        ],
      }
    case 'invalid-reviewer':
      return {
        steps: [
          completedWorker(),
          { verdict: 'PASS', residualRisks: [], blockers: [] },
        ],
      }
    case 'invalid-worker-completed-with-blocker':
      // Now that the dispatched schema permits blocker as an optional
      // property on every branch, only validWorkerResult's hasExactKeys
      // check still rejects a COMPLETED result carrying a branch-foreign key.
      return {
        steps: [
          {
            ...completedWorker(),
            blocker: 'This key does not belong on a COMPLETED result.',
          },
        ],
      }
    case 'invalid-worker-blocked-missing-blocker':
      return {
        steps: [
          {
            outcome: 'BLOCKED',
            residualRisks: [],
          },
        ],
      }
    case 'invalid-worker-needs-decision-with-blocker':
      return {
        steps: [
          {
            ...decisionWorker(),
            blocker: 'This key does not belong on a NEEDS_DECISION result.',
          },
        ],
      }
    case 'invalid-reviewer-pass-with-blockers':
      return {
        steps: [
          completedWorker(),
          {
            ...passReviewer(),
            blockers: [
              {
                where: 'reviewed behavior',
                why: 'This key does not belong on a PASS result.',
                howToFix: 'Remove the branch-foreign key.',
              },
            ],
          },
        ],
      }
    case 'invalid-reviewer-blocked-missing-blockers':
      return {
        steps: [
          completedWorker(),
          { verdict: 'BLOCKED', residualRisks: [] },
        ],
      }
    case 'invalid-reviewer-needs-decision-with-blockers':
      return {
        steps: [
          completedWorker(),
          {
            ...decisionReviewer(),
            blockers: [],
          },
        ],
      }
    case 'invalid-reviewer-decision-extra':
      return {
        steps: [
          completedWorker(),
          {
            verdict: 'NEEDS_DECISION',
            decision: {
              why: 'The review found an architecture question outside mechanical correction.',
              question: 'Should the Orchestrator authorize a seam change?',
              extra: 'Unknown fields remain rejected.',
            },
            residualRisks: [],
          },
        ],
      }
    case 'structured-happy':
      return {
        steps: [
          { structuredOutput: completedWorker(), output: 'ignored free-form text' },
          { structuredOutput: passReviewer(), output: 'ignored free-form text' },
        ],
      }
    case 'missing':
      return { missing: true, steps: [] }
    default:
      break
  }

  try {
    const parsed = JSON.parse(name)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed
    }
  } catch {
    // The workflow reports the controlled child failure; malformed scenario text is
    // not an input to the Workflow itself.
  }
  throw new Error(`unknown harness scenario: ${name}`)
}

function throwForStep(kind) {
  if (kind === 'interrupt') {
    const error = new Error('controlled child interruption')
    error.name = 'AbortError'
    error.code = 'ABORT_ERR'
    throw error
  }
  if (kind === 'capability') {
    const error = new Error('controlled exact role capability failure')
    error.code = 'CAPABILITY_UNAVAILABLE'
    throw error
  }
  throw new Error('controlled child runtime failure')
}

const scenario = namedScenario(scenarioName)
let stepIndex = 0
const agent = scenario.missing
  ? undefined
  : async (...invocation) => {
      calls.push(invocation)
      const step = scenario.steps[stepIndex++]
      if (step === undefined) return null
      if (
        step &&
        typeof step === 'object' &&
        !Array.isArray(step) &&
        Object.prototype.hasOwnProperty.call(step, 'throw')
      ) {
        throwForStep(step.throw)
      }
      return step
    }

const run = Function(
  'args',
  'agent',
  'log',
  'phase',
  `return (async () => {\n${body}\n})()`,
)
const result = await run(
  JSON.parse(argsJson),
  agent,
  (message) => logs.push(message),
  (title) => phases.push(title),
)

process.stdout.write(
  JSON.stringify({
    meta,
    result,
    calls: calls.length,
    invocations: calls,
    logs,
    phases,
  }),
)
