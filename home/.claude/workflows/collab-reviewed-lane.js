export const meta = {
  name: 'collab-reviewed-lane',
  description: 'Run one bounded Collab implementation and fresh protected-lane review',
  phases: [
    {
      title: 'Validate',
      detail: 'Validate the five-value input before native role dispatch.',
    },
    {
      title: 'Implement',
      detail: 'Dispatch one exact collab-implementer against the assigned lane.',
    },
    {
      title: 'Review',
      detail: 'Dispatch one fresh exact collab-acceptor only after canonical completion.',
    },
    {
      title: 'Correct',
      detail: 'Dispatch one bounded correction only for an initial reviewer blocker with remaining authority.',
    },
    {
      title: 'Rereview',
      detail: 'Dispatch one fresh exact collab-acceptor against the corrected protected lane.',
    },
  ],
}

const INPUT_KEYS = ['lane', 'startingHead', 'ticket', 'envelope', 'correctionBudget', 'operatorNotes']
const REQUIRED_KEYS = [...INPUT_KEYS]
const EXACT_ROLES = ['collab-implementer', 'collab-acceptor']
const NATIVE_DISPATCH = 'native-child-agent'
const MAX_TEXT = 4096
const MAX_ARRAY_ITEMS = 32
const MAX_BLOCKERS = 16

const TEXT_SCHEMA = {
  type: 'string',
  minLength: 1,
  maxLength: MAX_TEXT,
}

const RESIDUAL_RISKS_SCHEMA = {
  type: 'array',
  maxItems: MAX_ARRAY_ITEMS,
  items: { ...TEXT_SCHEMA },
}

const WORKER_DECISION_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['why', 'question'],
  properties: {
    why: { ...TEXT_SCHEMA },
    question: { ...TEXT_SCHEMA },
  },
}



const REVIEW_BLOCKERS_SCHEMA = {
  type: 'array',
  minItems: 1,
  maxItems: MAX_BLOCKERS,
  items: {
    type: 'object',
    additionalProperties: false,
    required: ['where', 'why', 'howToFix', 'trigger'],
    properties: {
      where: { ...TEXT_SCHEMA },
      why: { ...TEXT_SCHEMA },
      howToFix: { ...TEXT_SCHEMA },
      trigger: {
        ...TEXT_SCHEMA,
        description: 'The concrete input or call sequence that produces the defect, and the existing entry point it reaches from.',
      },
    },
  },
}

const REVIEW_DECISION_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['why', 'question'],
  properties: {
    why: { ...TEXT_SCHEMA },
    question: { ...TEXT_SCHEMA },
    suggestion: { ...TEXT_SCHEMA },
  },
}

// A tool input_schema may not carry oneOf/allOf/anyOf at any level, so the
// three closed worker branches are flattened into one object schema. Only
// the fields common to every branch are required; the branch-specific
// fields (blocker, decision) are declared optional with their existing
// sub-schemas unchanged. The closed-branch (exact-keys-per-outcome)
// guarantee remains enforced by validWorkerResult below, not by this schema.
// S3: worker Validation is absent; COMPLETED is binary attestation that required mechanical gates passed;
// residualRisks carries optional non-blocking findings, efficiencyFeedback remains process feedback.
const WORKER_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['outcome'],
  properties: {
    outcome: { enum: ['COMPLETED', 'BLOCKED', 'NEEDS_DECISION'] },
    residualRisks: RESIDUAL_RISKS_SCHEMA,
    blocker: { ...TEXT_SCHEMA },
    decision: WORKER_DECISION_SCHEMA,
  },
}

// Same flattening for the reviewer's three closed branches; the closed-branch
// guarantee remains enforced by validReviewerResult below.
// S1/S3: reviewer carries optional residualRisks for all non-blocking findings; outOfEnvelopeFindings is removed;
// initial BLOCKED may carry internal correctionBase (runtime-owned, never projected to public terminal).
const REVIEWER_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['verdict'],
  properties: {
    verdict: { enum: ['PASS', 'BLOCKED', 'NEEDS_DECISION'] },
    residualRisks: RESIDUAL_RISKS_SCHEMA,
    blockers: REVIEW_BLOCKERS_SCHEMA,
    correctionBase: { ...TEXT_SCHEMA, description: 'Internal correction base SHA of the reviewed lane HEAD at initial BLOCKED; runtime-owned, never projected to public terminal.' },
    decision: REVIEW_DECISION_SCHEMA,
  },
}

function usableText(value, maximum = MAX_TEXT) {
  return (
    typeof value === 'string' &&
    value.length <= maximum &&
    value.trim().length > 0 &&
    !Array.from(value).some((character) => {
      const code = character.charCodeAt(0)
      return code < 32 || code === 127
    })
  )
}

function absolutePathText(value) {
  return usableText(value) && value.startsWith('/')
}

// operatorNotes carries a multi-section execution record, so it alone permits the newline (code 10)
// and carriage-return (code 13) characters a pasted multi-line note actually contains — enough to
// represent Unix and Windows line endings — while every other control character, including tab,
// still fails it. Every other bounded text field keeps the strict single-line `usableText` check.
function usableMultilineText(value, maximum = MAX_TEXT) {
  return (
    typeof value === 'string' &&
    value.length <= maximum &&
    value.trim().length > 0 &&
    !Array.from(value).some((character) => {
      const code = character.charCodeAt(0)
      return (code < 32 && code !== 10 && code !== 13) || code === 127
    })
  )
}

function keysExcept(keys, allowed) {
  return keys.filter((key) => !allowed.includes(key))
}

function isRecord(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function hasExactKeys(value, required, allowed = required) {
  if (!isRecord(value)) return false
  const keys = Object.keys(value)
  return (
    keys.length === allowed.length &&
    required.every((key) => Object.prototype.hasOwnProperty.call(value, key)) &&
    keys.every((key) => allowed.includes(key))
  )
}

function boundedText(value) {
  return usableText(value)
}

function validValidation(value) {
  return (
    Array.isArray(value) &&
    value.length <= MAX_ARRAY_ITEMS &&
    value.every(
      (item) =>
        hasExactKeys(item, ['check', 'result', 'summary']) &&
        boundedText(item.check) &&
        ['PASSED', 'FAILED'].includes(item.result) &&
        boundedText(item.summary),
    )
  )
}

function validTextArray(value) {
  return (
    Array.isArray(value) &&
    value.length <= MAX_ARRAY_ITEMS &&
    value.every((item) => boundedText(item))
  )
}

function validWorkerDecision(value) {
  return (
    hasExactKeys(value, ['why', 'question']) &&
    boundedText(value.why) &&
    boundedText(value.question)
  )
}

function validWorkerResult(value) {
  if (!isRecord(value) || typeof value.outcome !== 'string') return false
  if ('validation' in value) return false
  if ('residualRisks' in value && !validTextArray(value.residualRisks)) return false
  if ('outOfEnvelopeFindings' in value) return false
  const allowedBase = new Set(['outcome', 'residualRisks', 'blocker', 'decision'])
  for (const k of Object.keys(value)) if (!allowedBase.has(k)) return false
  if (value.outcome === 'COMPLETED') {
    if ('blocker' in value || 'decision' in value) return false
    return true
  }
  if (value.outcome === 'BLOCKED') {
    if (!('blocker' in value) || 'decision' in value) return false
    return boundedText(value.blocker)
  }
  if (value.outcome === 'NEEDS_DECISION') {
    if (!('decision' in value) || 'blocker' in value) return false
    return validWorkerDecision(value.decision)
  }
  return false
}



function validReviewBlockers(value) {
  return (
    Array.isArray(value) &&
    value.length > 0 &&
    value.length <= MAX_BLOCKERS &&
    value.every(
      (blocker) =>
        hasExactKeys(blocker, ['where', 'why', 'howToFix', 'trigger']) &&
        boundedText(blocker.where) &&
        boundedText(blocker.why) &&
        boundedText(blocker.howToFix) &&
        boundedText(blocker.trigger),
    )
  )
}

function validReviewDecision(value) {
  if (!isRecord(value)) return false
  const hasValidShape =
    hasExactKeys(value, ['why', 'question']) ||
    hasExactKeys(value, ['why', 'question', 'suggestion'])
  if (
    !hasValidShape ||
    !boundedText(value.why) ||
    !boundedText(value.question)
  ) {
    return false
  }
  return (
    !Object.prototype.hasOwnProperty.call(value, 'suggestion') ||
    boundedText(value.suggestion)
  )
}

function validReviewerResult(value) {
  if (!isRecord(value) || typeof value.verdict !== 'string') return false
  if ('outOfEnvelopeFindings' in value) return false
  if ('validation' in value) return false
  if ('residualRisks' in value && !validTextArray(value.residualRisks)) return false
  if ('correctionBase' in value && !boundedText(value.correctionBase)) return false
  if ('blockers' in value && !validReviewBlockers(value.blockers)) return false
  if ('decision' in value && !validReviewDecision(value.decision)) return false
  const allowed = new Set(['verdict', 'residualRisks', 'blockers', 'correctionBase', 'decision'])
  for (const k of Object.keys(value)) if (!allowed.has(k)) return false
  if (value.verdict === 'PASS') {
    if ('blockers' in value || 'decision' in value || 'correctionBase' in value) return false
    return true
  }
  if (value.verdict === 'BLOCKED') {
    if (!('blockers' in value) || 'decision' in value) return false
    return validReviewBlockers(value.blockers)
  }
  if (value.verdict === 'NEEDS_DECISION') {
    if (!('decision' in value) || 'blockers' in value || 'correctionBase' in value) return false
    return validReviewDecision(value.decision)
  }
  return false
}

function terminal({
  execution,
  outcome,
  stoppedAt,
  stopReason,
  correctionsUsed = 0,
  workerResult = null,
  reviewResult = null,
  error,
  capability,
}) {
  const result = {
    type: 'collab-reviewed-lane-result',
    execution,
    outcome,
    stoppedAt,
    stopReason,
    correctionsUsed,
    workerResult,
    reviewResult,
  }
  if (error !== undefined) result.error = error
  if (capability !== undefined) result.capability = capability
  return result
}

function inputFailure(code, fields) {
  return terminal({
    execution: 'RUNTIME_GAP',
    outcome: null,
    stoppedAt: 'VALIDATE',
    stopReason: 'INVALID_INPUT',
    error: { code, fields },
    capability: { status: 'NOT_CHECKED' },
  })
}

function capabilityFailure(
  stoppedAt,
  workerResult,
  reviewResult,
  code,
  correctionsUsed = 0,
) {
  return terminal({
    execution: 'RUNTIME_GAP',
    outcome: null,
    stoppedAt,
    stopReason: 'CAPABILITY_UNAVAILABLE',
    correctionsUsed,
    workerResult,
    reviewResult,
    error: { code },
    capability: {
      status: 'RUNTIME_GAP',
      roles: [...EXACT_ROLES],
      dispatch: NATIVE_DISPATCH,
    },
  })
}

function interruptionFailure(
  stoppedAt,
  workerResult,
  reviewResult,
  correctionsUsed = 0,
) {
  return terminal({
    execution: 'INTERRUPTED',
    outcome: null,
    stoppedAt,
    stopReason: 'CHILD_INTERRUPTED',
    correctionsUsed,
    workerResult,
    reviewResult,
  })
}

function isInterruption(error) {
  return (
    error?.name === 'AbortError' ||
    error?.code === 'ABORT_ERR' ||
    error?.code === 'INTERRUPTED'
  )
}

function structuredOutput(value) {
  if (
    isRecord(value) &&
    Object.prototype.hasOwnProperty.call(value, 'structuredOutput') &&
    !Object.prototype.hasOwnProperty.call(value, 'outcome') &&
    !Object.prototype.hasOwnProperty.call(value, 'verdict')
  ) {
    return value.structuredOutput
  }
  return value
}

async function dispatchChild(agentType, prompt, schema, validate, stoppedAt, workerResult, reviewResult) {
  let raw
  try {
    raw = await agent(prompt, { agentType, schema })
  } catch (error) {
    if (isInterruption(error)) {
      return { kind: 'INTERRUPTED' }
    }
    return { kind: 'CAPABILITY_FAILURE', code: 'CHILD_RUNTIME_FAILURE' }
  }

  if (raw === null || raw === undefined) {
    return { kind: 'CAPABILITY_FAILURE', code: 'NULL_CHILD_RESULT' }
  }

  const result = structuredOutput(raw)
  if (!validate(result)) {
    return { kind: 'CAPABILITY_FAILURE', code: 'INVALID_CHILD_RESULT' }
  }
  return { kind: 'RESULT', result }
}

function inputForDispatch(supplied) {
  return {
    lane: supplied.lane,
    startingHead: supplied.startingHead,
    ticket: supplied.ticket,
    envelope: supplied.envelope,
    correctionBudget: supplied.correctionBudget,
    operatorNotes: supplied.operatorNotes,
  }
}

// Operator notes carry execution-record matter that has no home in a ticket.
// Their authority is closed: no scope, no Acceptance criterion, no mutation
// authority. Where a note and the ticket disagree, the ticket wins and the
// child returns NEEDS_DECISION instead of following the note. When notes are
// null, this returns no lines, so neither the notes nor this rule appears in
// any prompt.
function operatorNotesLines(input) {
  if (input.operatorNotes === null) return []
  return [
    `Operator notes: ${input.operatorNotes}`,
    'These operator notes carry no scope, no Acceptance criterion, and no mutation authority. Where a note and the ticket disagree, the ticket wins and you must return NEEDS_DECISION instead of following the note.',
  ]
}

function workerPrompt(input) {
  return [
    'Implement the bounded ticket as the sole writer in the assigned pre-provisioned lane.',
    'Read the ticket and its named supporting contract, remain inside the supplied envelope, validate semantic behavior, and stop mutation before review.',
    'Return only the canonical collab-implementer Result required by the supplied schema.',
    `Six-value Workflow input: ${JSON.stringify(input)}`,
    ...operatorNotesLines(input),
  ].join('\n')
}

function reviewerPrompt(input) {
  return [
    'Review the protected current lane read-only as a fresh collab-acceptor.',
    'Begin with the assigned ticket and the bounded lane change from startingHead to the protected current state; inspect no post-run task evidence or unrelated repository surface.',
    'Return only the canonical collab-acceptor Result required by the supplied schema.',
    `Six-value Workflow input: ${JSON.stringify(input)}`,
    ...operatorNotesLines(input),
  ].join('\n')
}

function correctionPrompt(input, blockers) {
  return [
    'Correct the bounded ticket as the sole writer in the assigned pre-provisioned lane.',
    'This is the one authorized correction after the initial reviewer BLOCKED result. Validate the whole applicable ticket state, commit the corrected lane, and stop mutation before rereview.',
    'Do not change ticket wording, lifecycle state, Resolution, or final judgement. Use only the current canonical typed reviewer blockers below as correction guidance; do not treat them as authority for a seam, architecture, schema, security, release, scope, or mutation-authority change.',
    `Six-value Workflow input: ${JSON.stringify(input)}`,
    `Current canonical reviewer blockers: ${JSON.stringify(blockers)}`,
    'Return only the canonical collab-implementer Result required by the supplied schema.',
    ...operatorNotesLines(input),
  ].join('\n')
}

function rereviewerPrompt(input) {
  return [
    'Review the changed protected lane read-only as one fresh collab-acceptor.',
    'Begin with the assigned ticket and the bounded lane change from startingHead to the changed protected current state; independently validate every supplied expectation and inspect no post-run task evidence or unrelated repository surface.',
    'The prior reviewer result does not cover the correction. Return only the canonical collab-acceptor Result required by the supplied schema.',
    `Six-value Workflow input: ${JSON.stringify(input)}`,
    ...operatorNotesLines(input),
  ].join('\n')
}

function failureFromChild(
  failure,
  stoppedAt,
  workerResult,
  reviewResult,
  correctionsUsed = 0,
) {
  if (failure.kind === 'INTERRUPTED') {
    return interruptionFailure(
      stoppedAt,
      workerResult,
      reviewResult,
      correctionsUsed,
    )
  }
  return capabilityFailure(
    stoppedAt,
    workerResult,
    reviewResult,
    failure.code,
    correctionsUsed,
  )
}

if (typeof phase === 'function') phase('Validate')

const supplied = args
if (
  supplied === null ||
  typeof supplied !== 'object' ||
  Array.isArray(supplied)
) {
  return inputFailure('INVALID_INPUT', ['args'])
}

const suppliedKeys = Object.keys(supplied)
const unknownKeys = keysExcept(suppliedKeys, INPUT_KEYS)
if (unknownKeys.length > 0) {
  return inputFailure('UNKNOWN_INPUT', unknownKeys)
}

const missingKeys = REQUIRED_KEYS.filter(
  (key) => !Object.prototype.hasOwnProperty.call(supplied, key),
)
if (missingKeys.length > 0) {
  return inputFailure('MISSING_INPUT', missingKeys)
}

const invalidKeys = []
for (const key of ['lane', 'ticket']) {
  if (!absolutePathText(supplied[key])) invalidKeys.push(key)
}
if (!usableText(supplied.startingHead)) invalidKeys.push('startingHead')
if (supplied.envelope !== null && !absolutePathText(supplied.envelope)) {
  invalidKeys.push('envelope')
}
if (supplied.operatorNotes !== null && !usableMultilineText(supplied.operatorNotes)) {
  invalidKeys.push('operatorNotes')
}
if (
  typeof supplied.correctionBudget !== 'number' ||
  !Number.isInteger(supplied.correctionBudget) ||
  ![0, 1].includes(supplied.correctionBudget)
) {
  invalidKeys.push('correctionBudget')
}
if (invalidKeys.length > 0) {
  return inputFailure('UNUSABLE_INPUT', invalidKeys)
}

if (typeof agent !== 'function') {
  return capabilityFailure('VALIDATE', null, null, 'NATIVE_DISPATCH_UNAVAILABLE')
}

const input = inputForDispatch(supplied)
if (typeof phase === 'function') phase('Implement')
const workerDispatch = await dispatchChild(
  'collab-implementer',
  workerPrompt(input),
  WORKER_SCHEMA,
  validWorkerResult,
  'IMPLEMENT',
  null,
  null,
)
if (workerDispatch.kind !== 'RESULT') {
  return failureFromChild(workerDispatch, 'IMPLEMENT', null, null)
}

const workerResult = workerDispatch.result
if (workerResult.outcome === 'BLOCKED') {
  return terminal({
    execution: 'COMPLETED',
    outcome: 'BLOCKED',
    stoppedAt: 'IMPLEMENT',
    stopReason: 'WORKER_BLOCKED',
    workerResult,
  })
}
if (workerResult.outcome === 'NEEDS_DECISION') {
  return terminal({
    execution: 'COMPLETED',
    outcome: 'NEEDS_DECISION',
    stoppedAt: 'IMPLEMENT',
    stopReason: 'DECISION_REQUIRED',
    workerResult,
  })
}

if (typeof phase === 'function') phase('Review')
const reviewDispatch = await dispatchChild(
  'collab-acceptor',
  reviewerPrompt(input),
  REVIEWER_SCHEMA,
  validReviewerResult,
  'REVIEW',
  workerResult,
  null,
)
if (reviewDispatch.kind !== 'RESULT') {
  return failureFromChild(reviewDispatch, 'REVIEW', workerResult, null)
}

const reviewResult = reviewDispatch.result
if (reviewResult.verdict === 'PASS') {
  return terminal({
    execution: 'COMPLETED',
    outcome: 'REVIEWED',
    stoppedAt: 'REVIEW',
    stopReason: 'REVIEW_PASS',
    workerResult,
    reviewResult,
  })
}
if (reviewResult.verdict === 'NEEDS_DECISION') {
  return terminal({
    execution: 'COMPLETED',
    outcome: 'NEEDS_DECISION',
    stoppedAt: 'REVIEW',
    stopReason: 'DECISION_REQUIRED',
    workerResult,
    reviewResult,
  })
}

if (supplied.correctionBudget === 0) {
  return terminal({
    execution: 'COMPLETED',
    outcome: 'BLOCKED',
    stoppedAt: 'REVIEW',
    stopReason: 'REVIEW_BLOCKED',
    workerResult,
    reviewResult,
  })
}

// correctionBudget === 1 is the sole finite correction branch. The counter is
// incremented at this transition and is never reset on any later terminal.
const correctionsUsed = 1
if (typeof phase === 'function') phase('Correct')
const correctionDispatch = await dispatchChild(
  'collab-implementer',
  correctionPrompt(input, reviewResult.blockers),
  WORKER_SCHEMA,
  validWorkerResult,
  'CORRECT',
  workerResult,
  reviewResult,
)
if (correctionDispatch.kind !== 'RESULT') {
  return failureFromChild(
    correctionDispatch,
    'CORRECT',
    workerResult,
    reviewResult,
    correctionsUsed,
  )
}

const correctedWorkerResult = correctionDispatch.result
if (correctedWorkerResult.outcome === 'BLOCKED') {
  return terminal({
    execution: 'COMPLETED',
    outcome: 'BLOCKED',
    stoppedAt: 'CORRECT',
    stopReason: 'WORKER_BLOCKED',
    correctionsUsed,
    workerResult: correctedWorkerResult,
    reviewResult,
  })
}
if (correctedWorkerResult.outcome === 'NEEDS_DECISION') {
  return terminal({
    execution: 'COMPLETED',
    outcome: 'NEEDS_DECISION',
    stoppedAt: 'CORRECT',
    stopReason: 'DECISION_REQUIRED',
    correctionsUsed,
    workerResult: correctedWorkerResult,
    reviewResult,
  })
}

if (typeof phase === 'function') phase('Rereview')
const rereviewDispatch = await dispatchChild(
  'collab-acceptor',
  rereviewerPrompt(input),
  REVIEWER_SCHEMA,
  validReviewerResult,
  'REREVIEW',
  correctedWorkerResult,
  reviewResult,
)
if (rereviewDispatch.kind !== 'RESULT') {
  return failureFromChild(
    rereviewDispatch,
    'REREVIEW',
    correctedWorkerResult,
    reviewResult,
    correctionsUsed,
  )
}

const rereviewResult = rereviewDispatch.result
if (rereviewResult.verdict === 'PASS') {
  return terminal({
    execution: 'COMPLETED',
    outcome: 'REVIEWED',
    stoppedAt: 'REREVIEW',
    stopReason: 'REVIEW_PASS',
    correctionsUsed,
    workerResult: correctedWorkerResult,
    reviewResult: rereviewResult,
  })
}
if (rereviewResult.verdict === 'NEEDS_DECISION') {
  return terminal({
    execution: 'COMPLETED',
    outcome: 'NEEDS_DECISION',
    stoppedAt: 'REREVIEW',
    stopReason: 'DECISION_REQUIRED',
    correctionsUsed,
    workerResult: correctedWorkerResult,
    reviewResult: rereviewResult,
  })
}

return terminal({
  execution: 'COMPLETED',
  outcome: 'BLOCKED',
  stoppedAt: 'REREVIEW',
  stopReason: 'CORRECTION_BUDGET_EXHAUSTED',
  correctionsUsed,
  workerResult: correctedWorkerResult,
  reviewResult: rereviewResult,
})
