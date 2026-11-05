export const meta = {
  name: 'land',
  description: "Make a plumb branch ready to land: merge main into it, run the full run, repin the moved links and run the merge check; it never merges into main",
  whenToUse: "Run when an intent branch is built and proven in its worktree. args: {branch, worktree}. It returns {ready, holds, questions}; the main session then lands the branch.",
  phases: [
    { title: 'Merge main in', detail: 'git merge main inside the worktree' },
    { title: 'Full run', detail: 'merge-check --run main under the heavy lock' },
    { title: 'Repin', detail: 'repin --after-tests for the links the merge moved' },
    { title: 'Merge check', detail: 'merge-check, report what holds' },
  ],
}

const input = typeof args === 'string' ? JSON.parse(args) : (args || {})
const branch = input.branch || ''
const worktree = input.worktree || ''
if (!branch || !worktree) {
  return { ready: false, holds: [], questions: [], error: 'args need branch and worktree' }
}

const HEAVY = [
  'Heavy jobs (any pytest run, any repin --after-tests, any full run) take a machine-wide lock first,',
  'in the same command chain as the job:',
  'L=$(git rev-parse --git-common-dir)/plumb-heavy.lock; until ( set -o noclobber; echo "land" > "$L" ) 2>/dev/null; do sleep 20; done; <the job>; rm -f "$L"',
  'When the lock stays held, run the chain in the background and wait for it to end; never remove a lock you did not create.',
  'Never run pytest with more than -n 2.',
].join('\n')
const WORKTREE = [
  'Work ONLY in the worktree ' + worktree + ' (branch ' + branch + '): begin every shell command with cd ' + worktree + ' &&',
  'and run plumb as PYTHONPATH=' + worktree + '/src {plumb} ... Never edit or merge in the main checkout.',
  'Never bypass a hook or a check: no flag that skips verification, no override, no forced push or merge.',
].join('\n')
const QUESTION = [
  'You ask the owner nothing. If something holds on a choice only the owner can make, or a link whose meaning changed,',
  'stop and return it as a question with options and what each option does.',
].join('\n')
const STATE = 'You are one step of the plumb workflow land, getting branch ' + branch + ' ready to land in main. Steps run in order; yours is named below. You never merge the branch into main: the main session does that.'

const STEP = {
  type: 'object',
  properties: {
    ok: { type: 'boolean' },
    finding: { type: 'string' },
    holds: { type: 'array', items: { type: 'string' } },
    question: {
      type: 'object',
      properties: { question: { type: 'string' }, options: { type: 'array', items: { type: 'string' } } },
      required: ['question', 'options'],
    },
  },
  required: ['ok', 'finding'],
}

const steps = [
  {
    title: 'Merge main in',
    task: [
      'Pin main first: M=$(git rev-parse main). Then run git merge main in the worktree.',
      'If it conflicts, resolve each code conflict keeping both sides intent. A conflict in a record file (under .plumb/), or one you cannot settle without the owner, is a question: say what each side wants, choose nothing.',
      'Return ok true when the merge is complete and the tree is clean; finding names the pinned M and the files the merge moved.',
    ],
  },
  {
    title: 'Full run',
    task: [
      'Run the full run under the heavy lock: {plumb} merge-check --run main',
      'Return ok true only if it passed; finding names each failing test or hold.',
    ],
  },
  {
    title: 'Repin',
    task: [
      'Pick the links the merge moved from git diff HEAD (against HEAD, never against main: main moves).',
      'Repin them under the heavy lock: {plumb} repin --after-tests',
      'Return ok true when no moved link is stale; finding names what was repinned.',
    ],
  },
  {
    title: 'Merge check',
    task: [
      'Run {plumb} merge-check and read what it says.',
      'Return ok true only if nothing holds; holds lists each hold in the owner terms (what it is and why), finding the rest.',
    ],
  },
]

const FIRST = { model: 'sonnet' }
// retry path: the step failed once, so it runs again on the stronger model, told why it failed
const RETRY = { model: 'opus' }

const run = (step, tier, earlier) => agent([
  STATE, 'Your step: ' + step.title, '', WORKTREE, '', HEAVY, '', QUESTION, '', step.task.join('\n'),
  earlier ? '\nThis step failed once already (the tree may be half done: continue from its state). Why: ' + earlier : '',
].join('\n'), { label: step.title, phase: step.title, ...tier, schema: STEP })

let holds = []
for (const step of steps) {
  phase(step.title)
  let out = await run(step, FIRST, '')
  if ((!out || !out.ok) && !(out && out.question)) {
    out = await run(step, RETRY, out ? out.finding : 'no result')
  }
  if (!out || !out.ok) {
    log(step.title + ' did not pass: stopping')
    return {
      ready: false,
      holds: out && out.holds && out.holds.length ? out.holds : [step.title + ': ' + (out ? out.finding : 'no result')],
      questions: out && out.question ? [out.question] : [],
    }
  }
  holds = out.holds || []
}
return { ready: holds.length === 0, holds, questions: [] }
