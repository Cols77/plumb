<script lang="ts">
  import DiffView from './DiffView.svelte';
  import type { DiffLine } from '../lib/diff';
  import type { Card, Followup, LinkTarget } from '../lib/types';
  let { card, followups, session }: {card: Card | undefined; followups: Followup[]; session: string} = $props();
  let tab = $state('evidence'); let split = $state(true); let onlySelected = $state(false);
  const activity = $derived(onlySelected ? followups.filter(item => item.card === card?.id) : followups);
  const text = (value: unknown) => typeof value === 'string' ? value : JSON.stringify(value, null, 2) ?? '(not stored)';
  const linkTarget = (target: LinkTarget | undefined) => typeof target === 'string' ? target : target?.record || target?.path || target?.test || target?.symbol || 'Related artifact';
  const confirmation = (state: string | undefined) => ({proposed:'Not yet confirmed',confirmed:'Confirmed wording','unconfirmed-edit':'Changed since confirmation'}[state ?? ''] ?? 'Confirmation unavailable');
  function fieldLines(ours: unknown, theirs: unknown): DiffLine[] {
    if (text(ours) === text(theirs)) return text(ours).split('\n').map((line, i) => ({kind:'ctx',text:line,oldNo:i+1,newNo:i+1}));
    return [...text(ours).split('\n').map((line, i): DiffLine => ({kind:'del',text:line,oldNo:i+1,newNo:null})), ...text(theirs).split('\n').map((line, i): DiffLine => ({kind:'add',text:line,oldNo:null,newNo:i+1}))];
  }
</script>
<aside class="evidence-pane" aria-label="Evidence and activity">
  <div class="pane-tabs" role="tablist" aria-label="Issue supporting details">
    <button role="tab" aria-selected={tab === 'evidence'} id="evidence-tab" aria-controls="evidence-panel" onclick={() => tab = 'evidence'}>Evidence</button>
    <button role="tab" aria-selected={tab === 'activity'} id="activity-tab" aria-controls="activity-panel" onclick={() => tab = 'activity'}>Activity <span class="count">{followups.length}</span></button>
  </div>
  {#if tab === 'evidence'}
    <div id="evidence-panel" role="tabpanel" aria-labelledby="evidence-tab" class="pane-content">
      <p class="eyebrow">Grounded in the records</p>
      <p class="muted">An answer records your intent. Repair and verification need their own evidence.</p>
      {#if card?.evidence}<details open><summary>Source evidence</summary><div class="prose">{card.evidence}</div></details>{/if}
      {#each card?.records ?? [] as record (record.id)}
        <article class="record"><span class="eyebrow mono">{record.id}</span><h3>{record.title}</h3>
          <div class="record-status" aria-label="Confirmation and link status"><p class:confirmed={record.status?.confirmation === 'confirmed'}>{confirmation(record.status?.confirmation)}</p>
            {#if record.id.startsWith('SR-') && record.status}<p class="muted">{record.status.covered ? 'Examples have current linked coverage.' : 'Coverage is incomplete or unavailable.'}</p>{/if}
            {#if record.status?.uncovered_examples?.length}<p class="muted">Examples without current coverage: {record.status.uncovered_examples.join(', ')}</p>{/if}
            {#if record.status?.changed_tests?.length}<p class="muted">Acceptance tests changed: {record.status.changed_tests.join(', ')}</p>{/if}
            {#if record.status?.superseded_by}<p class="muted">Replaced by {record.status.superseded_by}</p>{/if}
            {#if record.status?.carried_from}<p class="muted">Confirmation carried by renumber from {record.status.carried_from}.</p>{/if}
            {#if record.status?.self_recorded}<p class="muted">Approval relies on a message recorded by the agent.</p>{/if}
            {#if record.status?.links?.length}<ul class="record-links">{#each record.status.links as link}<li>{link.state} · {linkTarget(link.link?.target)}</li>{/each}</ul>{/if}
          </div>
          <details><summary>Technical details</summary><pre>{text(record.status)}</pre></details>
          <details><summary>Full record body</summary><div class="prose">{record.body || 'No body text stored.'}</div></details>
          <details><summary>Stored fields and hash</summary><pre>{text(record.fields)}</pre><code>{record.hash}</code></details>
        </article>
      {:else}<p class="empty-note">No related record evidence is available for this issue.</p>{/each}
      {#if card?.diff}
        <section class="conflict"><h3>Stored conflict · {card.diff.record}</h3>
          <div class="segmented" aria-label="Diff display"><button aria-pressed={!split} onclick={() => split = false}>Unified</button><button aria-pressed={split} onclick={() => split = true}>Split</button></div>
          <p class="diff-labels"><span>− {card.diff.labels.ours}</span><span>+ {card.diff.labels.theirs}</span></p>
          {#each Object.entries(card.diff.fields) as [field, values]}
            <h4>{field}</h4><details><summary>Base value</summary><pre>{text(values.base)}</pre></details>
            <div class="diff-scroll"><DiffView lines={fieldLines(values.ours, values.theirs)} {split}/></div>
          {/each}
          {#if card.diff.proposed != null}<details><summary>Stored proposed version</summary><pre>{text(card.diff.proposed)}</pre></details>{/if}
        </section>
      {/if}
    </div>
  {:else}
    <div id="activity-panel" role="tabpanel" aria-labelledby="activity-tab" class="pane-content">
      <p class="eyebrow">Source session</p><p class="mono wrap">{session}</p>
      <p class="muted">Queued context waits for this session's next prompt hook. Delivered means retained in that hook's output; it does not mean the agent acted.</p>
      <label class="check-label"><input type="checkbox" bind:checked={onlySelected}/> Only this issue</label>
      <ol class="activity-list">{#each activity as item (item.id)}<li><span class="status-badge">{item.status.replaceAll('_',' ')}</span><p class="wrap">{item.card}</p><time datetime={item.created}>{item.created}</time>{#if item.delivered}<p>Delivered <time datetime={item.delivered}>{item.delivered}</time></p>{/if}</li>{:else}<li class="empty-note">No follow-up activity recorded.</li>{/each}</ol>
    </div>
  {/if}
</aside>
