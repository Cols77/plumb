export const meta = {
  name: 'intent-build',
  description: "Build an intent that passed its clarify gate: write the plan's acceptance tests and pass the plan gate, build each plan item, then prove it and close the intent",
  whenToUse: "Run after stage A of /plumb intent passed and the owner opted in to a workflow. args: {intent, plan: [{id, sr, summary}], worktree, session, notes, models}. notes (optional) is what every agent should know from the main session. models (optional) sets the model of a level: {haiku, sonnet, opus, fable}. It asks the owner nothing: a changed meaning comes back as a question.",
  phases: [
    { title: 'Plan', detail: 'failing acceptance tests, then the plan gate' },
    { title: 'Build', detail: 'implement each plan item, then test and review it' },
    { title: 'Prove', detail: 'covering tests, repin, proofs, intent done' },
  ],
}

const input = typeof args === 'string' ? JSON.parse(args) : (args || {})
// the four capability levels (owner, 2026-11-06); args.models sets the model of a level
const LEVEL = Object.assign({ haiku: 'haiku', sonnet: 'sonnet', opus: 'opus', fable: 'fable' }, input.models || {})
const intent = input.intent || ''
const plan = input.plan || []
const worktree = input.worktree || ''
const session = input.session || ''
const notes = input.notes || ''
if (!intent || !plan.length || !worktree) {
  return { built: [], failed: [], questions: [], done: false, error: 'args need intent, plan and worktree' }
}

const HEAVY = [
  'Heavy jobs go one at a time across every session, under the one-heavy-job lock (plumb-heavy.lock).',
  'plumb takes it itself for {plumb} tests run, {plumb} merge-check --run, {plumb} repin --after-tests, {plumb} align and {plumb} debug fix: run those plainly, never inside a lock of your own.',
  'Any other heavy command (a pytest run) goes through it as: {plumb} heavy -- <command>',
  'A command that waits says what it waits for: let it wait, in the background when it is long. Never create or remove the lock file yourself.',
  'Never run pytest with more than -n 2, and never the whole suite unless the item is about it.',
].join('\n')
const WORKTREE = [
  'Work ONLY in the worktree ' + worktree + ': begin every shell command with cd ' + worktree + ' &&',
  'and give edit tools absolute paths under it. Run plumb as PYTHONPATH=' + worktree + '/src {plumb} ...',
  'and tests with PYTHONPATH=' + worktree + '/src. Never edit the main checkout.',
].join('\n')
const QUESTION = [
  'You ask the owner nothing. If the work would change what a confirmed requirement means,',
  'stop and return it as a question with options and what each option does.',
].join('\n')
const STATE = [
  'You are one agent of the plumb workflow intent-build, building the intent: ' + intent + '.',
  'Stage A (clarifying the intent with the owner) is finished; the records are written. Session: ' + session + '.',
  notes ? 'From the main session: ' + notes : '',
].join('\n')
const SESSION = session ? ' --session ' + session : ''
const itemText = (it) => 'Plan item ' + it.id + (it.sr ? ' (requirement ' + it.sr + ')' : '') + ': ' + it.summary
const planText = plan.map(itemText).join('\n')

const STEP = {
  type: 'object',
  properties: {
    ok: { type: 'boolean' },
    finding: { type: 'string' },
    question: {
      type: 'object',
      properties: { question: { type: 'string' }, options: { type: 'array', items: { type: 'string' } } },
      required: ['question', 'options'],
    },
  },
  required: ['ok', 'finding'],
}
const GATE = {
  type: 'object',
  properties: { exitCode: { type: 'number' }, finding: { type: 'string' } },
  required: ['exitCode', 'finding'],
}

// Plan: failing tests, then the gate
phase('Plan')
const tests = await agent([
  STATE, '', WORKTREE, '', HEAVY, '', QUESTION, '',
  'The plan:', planText, '',
  'Write the acceptance tests of these items, from the examples of each requirement ({plumb} show <SR>), each marked with its requirement. Run them: they must FAIL now for the right reason (the feature is missing), never for a typo.',
  'Write no implementation. Return ok and a finding naming the test files.',
].join('\n'), { label: 'plan tests', phase: 'Plan', model: LEVEL.sonnet, schema: STEP })
if (!tests || !tests.ok) {
  return { built: [], failed: [], questions: tests && tests.question ? [tests.question] : [], done: false, stopped: 'plan tests: ' + (tests ? tests.finding : 'no result') }
}
const gate = await agent([
  STATE, '', WORKTREE, '',
  'The plan:', planText, '',
  'Write your findings for the plan gate (open conflicts, unanswered questions, plan items with no failing test) to a file,',
  'a JSON list of {"level": "high" | "medium" | "low", "what": "..."} (an empty list when there is none), then run:',
  '{plumb} intent gate plan --intent ' + intent + ' --findings <file>' + SESSION,
  'Then report it to the owner band: {plumb} intent progress --task "plan gate passed" (or "plan gate failed") --done 1 --total 3' + SESSION,
  'Return exitCode (the gate command exit code) and finding (what the gate printed, plainly).',
].join('\n'), { label: 'plan gate', phase: 'Plan', model: LEVEL.sonnet, schema: GATE })
if (!gate || gate.exitCode !== 0) {
  log('plan gate did not pass: stopping before Build')
  return { built: [], failed: [], questions: [], done: false, stopped: 'plan gate: ' + (gate ? gate.finding : 'no result') }
}

// Build: one pipeline per item
phase('Build')
const FIRST = { model: LEVEL.sonnet }
// retry path: the first build of the item failed its tests or review, so it runs again one level up
const RETRY = { model: LEVEL.opus }

const buildPrompt = (it, earlier) => [
  STATE, '', WORKTREE, '', QUESTION, '',
  'The whole plan, for context:', planText, '',
  'Build ' + itemText(it) + '. Read its requirement ({plumb} show ' + (it.sr || '<SR>') + ') and make its acceptance tests pass with the smallest complete change; touch only what this item needs (other agents build other items at once).',
  'Do not run the tests: the next agent does, under the heavy lock.',
  earlier ? '\nThe first build failed. Its tests or review found: ' + earlier + '\nFix exactly that.' : '',
  'Return ok and a finding (what you changed, in plain words).',
].join('\n')
const checkPrompt = (it, built) => [
  STATE, 'You test and review; you do not implement.', '', WORKTREE, '', HEAVY, '',
  itemText(it), 'The builder says: ' + built.finding, '',
  'Run the item tests under the lock, then review the diff (git diff HEAD) against the examples of the requirement ({plumb} show ' + (it.sr || '<SR>') + '). Other items are built in the same tree at the same time: judge only what this item changed. Say ok only if the tests pass and this item does what every example says and nothing else.',
  'Return ok and a finding (what failed or what you checked).',
].join('\n')

const round = async (it, earlier, tier) => {
  const built = await agent(buildPrompt(it, earlier), { label: 'build ' + it.id, phase: 'Build', ...tier, schema: STEP })
  if (!built) return { ok: false, finding: 'the builder returned nothing' }
  if (built.question) return built
  const checked = await agent(checkPrompt(it, built), { label: 'check ' + it.id, phase: 'Build', model: LEVEL.sonnet, schema: STEP })
  return checked || { ok: false, finding: 'the checker returned nothing' }
}
const outcomes = await pipeline(plan, async (it) => {
  const first = await round(it, '', FIRST)
  if (first.ok || first.question) return first
  return await round(it, first.finding, RETRY)
})
const built = [], failed = [], questions = []
outcomes.forEach((o, i) => {
  const it = plan[i]
  if (!o) failed.push({ id: it.id, finding: 'the pipeline for this item failed' })
  else if (o.question) questions.push(Object.assign({ id: it.id }, o.question))
  else if (o.ok) built.push(it.id)
  else failed.push({ id: it.id, finding: o.finding })
})
if (failed.length || questions.length) {
  log('Build left ' + failed.length + ' failed items and ' + questions.length + ' questions: stopping before Prove')
  return { built, failed, questions, done: false }
}

// Prove
phase('Prove')
const proof = await agent([
  STATE, '', WORKTREE, '', HEAVY, '', QUESTION, '',
  'Every plan item is built:', planText, '',
  '1. Run the tests that cover these requirements under the lock.',
  '2. Repin the links the work moved, under the lock: {plumb} repin --after-tests',
  '3. Record the proof the owner stated for each requirement: {plumb} proof <SR> --evidence <file holding the output> --summary "<what it shows>" --passed (or --failed)',
  '4. Commit the work on this branch, never on main: the message through a file (git commit -F <file>) with one trailer line SR: <SR> per requirement; bypass no hook.',
  '5. Close the loop: {plumb} intent done --intent ' + intent + SESSION + '. Report the gate to the band: {plumb} intent progress --task "prove gate passed" (or failed) --done 3 --total 3' + SESSION,
  'Return exitCode (of intent done) and finding (the gate output, plainly, and which proofs are still open).',
].join('\n'), { label: 'prove', phase: 'Prove', model: LEVEL.sonnet, schema: GATE })
return { built, failed, questions, done: !!proof && proof.exitCode === 0, finding: proof ? proof.finding : 'no result' }
