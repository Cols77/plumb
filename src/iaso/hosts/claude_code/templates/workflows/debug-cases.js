export const meta = {
  name: 'debug-cases',
  description: "Fix iaso's open debug cases, one pipeline per case: fix, then verify, then one more round one level up if the case is not resolved",
  whenToUse: "Run when a 'iaso:' line lists open debug cases. args: {cases: [{id, kind, target, detail}], worktree, models}. models (optional) sets the model of a level: {haiku, sonnet, opus, fable}. Not for a case that needs an owner choice: those come back as questions.",
  phases: [
    { title: 'Fix', detail: 'one agent per case repins, relinks or reruns' },
    { title: 'Verify', detail: 'a second agent reruns the case check' },
  ],
}

const input = typeof args === 'string' ? JSON.parse(args) : (args || {})
// the four capability levels (owner, 2026-11-06); args.models sets the model of a level
const LEVEL = Object.assign({ haiku: 'haiku', sonnet: 'sonnet', opus: 'opus', fable: 'fable' }, input.models || {})
const cases = input.cases || []
const worktree = input.worktree || ''
if (!cases.length || !worktree) {
  return { resolved: [], open: [], questions: [], error: 'args need cases and worktree' }
}

const HEAVY = [
  'Heavy jobs go one at a time across every session, under the one-heavy-job lock (iaso-heavy.lock).',
  'iaso takes it itself for {iaso} tests run, {iaso} merge-check --run, {iaso} repin --after-tests, {iaso} align and {iaso} debug fix: run those plainly, never inside a lock of your own.',
  'Any other heavy command (a pytest run) goes through it as: {iaso} heavy -- <command>',
  'A command that waits says what it waits for: let it wait, in the background when it is long. Never create or remove the lock file yourself.',
  'Never run pytest with more than -n 2, and never the whole suite unless the case is about it.',
].join('\n')
const WORKTREE = [
  'Work ONLY in the worktree ' + worktree + ': begin every shell command with cd ' + worktree + ' &&',
  'and give edit tools absolute paths under it. Run iaso as PYTHONPATH=' + worktree + '/src {iaso} ...',
  'and tests with PYTHONPATH=' + worktree + '/src. Never edit the main checkout.',
].join('\n')
const QUESTION = [
  'You ask the owner nothing. If a fix would change what a requirement means (a link whose meaning changed),',
  'stop on that case and return it as a question with options and what each option does.',
].join('\n')
const STATE = 'You are one agent of the iaso workflow debug-cases, fixing one open debug case of iaso itself. Other agents work on other cases at the same time; touch only what your case needs.'

const RESULT = {
  type: 'object',
  properties: {
    resolved: { type: 'boolean' },
    finding: { type: 'string' },
    question: {
      type: 'object',
      properties: { question: { type: 'string' }, options: { type: 'array', items: { type: 'string' } } },
      required: ['question', 'options'],
    },
  },
  required: ['resolved', 'finding'],
}

const caseText = (c) => 'Case ' + c.id + ' (' + c.kind + ') on ' + c.target + ': ' + c.detail

const fixPrompt = (c, earlier) => [
  STATE, '', WORKTREE, '', HEAVY, '', QUESTION, '',
  caseText(c), '',
  'Fix it: repin after its tests pass ({iaso} repin --after-tests), relink when the code moved,',
  'rerun a test that failed (or fix the test or code it exposes), rerun a failed judge job.',
  'When the case is resolved run {iaso} understand debug done ' + c.id + '.',
  earlier ? '\nThe earlier round did not resolve it. Its finding: ' + earlier + '\nDo not repeat what it tried.' : '',
  'Return resolved (true only if you ran done) and finding (what you did and what is left, plainly).',
].join('\n')

const verifyPrompt = (c, fix) => [
  STATE, 'You verify; you do not fix.', '', WORKTREE, '', HEAVY, '',
  caseText(c), '',
  'The fixing agent says: ' + fix.finding, '',
  'Rerun the case check ({iaso} debug, or the failing step the case names) and say whether the case is resolved now, with why.',
  'Return resolved and finding.',
].join('\n')

const FIRST = { model: LEVEL.sonnet }
// retry path: the first round did not resolve the case, so the fix agent runs one level up
const RETRY = { model: LEVEL.opus }

const round = async (c, earlier, tier) => {
  const fix = await agent(fixPrompt(c, earlier), { label: 'fix ' + c.id, phase: 'Fix', ...tier, schema: RESULT })
  if (!fix) return { resolved: false, finding: 'the fix agent returned nothing' }
  if (fix.question) return fix
  const check = await agent(verifyPrompt(c, fix), { label: 'verify ' + c.id, phase: 'Verify', model: LEVEL.sonnet, schema: RESULT })
  return check || { resolved: false, finding: 'the verify agent returned nothing' }
}

const results = await pipeline(cases, async (c) => {
  const first = await round(c, '', FIRST)
  if (first.resolved || first.question) return { c, out: first }
  // the case is not resolved: one more round one level up, told why the first failed
  const again = await round(c, first.finding, RETRY)
  return { c, out: again }
})

const resolved = [], open = [], questions = []
results.forEach((r, i) => {
  const c = cases[i]
  if (!r) open.push({ id: c.id, finding: 'the pipeline for this case failed' })
  else if (r.out.question) questions.push({ id: c.id, question: r.out.question.question, options: r.out.question.options })
  else if (r.out.resolved) resolved.push(c.id)
  else open.push({ id: c.id, finding: r.out.finding })
})
return { resolved, open, questions }
