// Runs a shipped workflow script with scripted agents (SR-385's tests):
//   node run_workflow.mjs <script.js> '{"args": {...}, "answers": {"<label>": [result, ...]}}'
// An agent's nth call under a label gets that label's nth answer (the last one repeats).
import { readFileSync } from 'node:fs'

const [file, json] = process.argv.slice(2)
const { args, answers } = JSON.parse(json)
const calls = []
const agent = async (prompt, opts = {}) => {
  calls.push({ label: opts.label, model: opts.model, phase: opts.phase })
  const list = answers[opts.label] || [null]
  const n = calls.filter((c) => c.label === opts.label).length
  return list[Math.min(n, list.length) - 1]
}
const pipeline = (items, ...stages) => Promise.all(items.map(async (item, i) => {
  let out = item
  try { for (const stage of stages) out = await stage(out, item, i) } catch { return null }
  return out
}))
const parallel = (thunks) => Promise.all(thunks.map((t) => t().catch(() => null)))
const body = readFileSync(file, 'utf8').replace('export const meta', 'const meta')
const AsyncFunction = Object.getPrototypeOf(async () => {}).constructor
const run = new AsyncFunction('args', 'agent', 'pipeline', 'parallel', 'phase', 'log', body)
const result = await run(args, agent, pipeline, parallel, () => {}, () => {})
console.log(JSON.stringify({ result, calls }))
