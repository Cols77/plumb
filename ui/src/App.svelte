<script lang="ts">
  import { onMount, tick } from 'svelte';
  import { api, ApiError, takeCapability } from './lib/api';
  import type { Button, Card, Draw, Followup, Offer, PressResult, Session, Workspace } from './lib/types';
  import Splitter from './components/Splitter.svelte';
  import Diagram from './components/Diagram.svelte';
  import Evidence from './components/Evidence.svelte';
  import Studies from './components/Studies.svelte';

  const capability = takeCapability();
  let workspace = $state<Workspace>(); let session = $state(''); let cards = $state<Card[]>([]); let followups = $state<Followup[]>([]);
  let selected = $state(''); let query = $state(''); let stateFilter = $state('all'); let kindFilter = $state('all');
  let connection = $state('Connecting'); let loadError = $state(''); let loading = $state(false); let busy = $state(false);
  let feedback = $state<Record<string, {error?: string; result?: PressResult}>>({});
  let drafts = $state<Record<string, string>>({}); let composers = $state<Record<string, number | undefined>>({});
  let refused = $state<Record<string, boolean>>({}); let section = $state<'issues' | 'studies'>('issues');
  const pending = new Map<string, string>();
  let generation = 0; let alive = true;
  let viewport = $state(window.innerWidth); let drawer = $state(false); let drawerButton = $state<HTMLButtonElement>(); let inbox = $state<HTMLElement>(); let help: HTMLDialogElement;
  const readWidth = (key: string, fallback: number, min: number, max: number) => { try { const value = Number(localStorage.getItem(key)); return value ? Math.max(min, Math.min(max, value)) : fallback; } catch { return fallback; } };
  let leftWidth = $state(readWidth('plumb.inbox-width',260,220,380)); let rightWidth = $state(readWidth('plumb.evidence-width',320,260,460));
  function saveWidth(key: string, value: number) { try { localStorage.setItem(key,String(value)); } catch { /* Resizing still works. */ } }
  const kindOf = (card: Card) => card.content?.kind ?? card.kind;
  const titleOf = (card: Card) => card.content?.topic || card.topic || 'Untitled issue';
  const human = (value: string) => value.replaceAll('_', ' ');
  const states = ['all','waiting','processing','blocked','done','left_open'];
  const total = (item: Session) => Object.values(item.counts).reduce((sum,n) => sum+n,0);
  const sessions = $derived([...(workspace?.sessions ?? [])].sort((a,b) => (b.counts.waiting || 0)-(a.counts.waiting || 0) || total(b)-total(a) || a.id.localeCompare(b.id)));
  const kinds = $derived([...new Set(cards.map(kindOf))].sort());
  const visible = $derived(cards.filter(card => (stateFilter === 'all' || card.state === stateFilter) && (kindFilter === 'all' || kindOf(card) === kindFilter) &&
    [card.topic, card.issue, card.evidence, card.content?.topic, card.content?.issue, ...(card.content?.context ?? [])].join(' ').toLowerCase().includes(query.trim().toLowerCase())));
  const active = $derived(cards.find(card => card.id === selected));
  const activeKey = $derived(`${session}:${selected}`);
  const message = $derived(feedback[activeKey]);
  const isNarrow = $derived(viewport < 760);
  function locationSelection() { const url = new URL(location.href); return {session:url.searchParams.get('session') ?? '',card:url.searchParams.get('card') ?? ''}; }
  function setUrl(push: boolean) {
    const url = new URL(location.href); url.hash = '';
    if (session) url.searchParams.set('session',session); else url.searchParams.delete('session');
    if (selected) url.searchParams.set('card',selected); else url.searchParams.delete('card');
    if (url.href !== location.href) history[push ? 'pushState' : 'replaceState']({},'',url);
  }
  function closeDrawer() { drawer = false; if (isNarrow) void tick().then(() => drawerButton?.focus()); }
  async function openDrawer() { drawer = true; await tick(); inbox?.querySelector<HTMLInputElement>('input')?.focus(); }
  function chooseCard(id: string) { selected = id; setUrl(true); if (drawer) closeDrawer(); }
  async function draw(id: string, desired?: string) {
    const request = ++generation; loading = true;
    try {
      const data = await api<Draw>(`/api/sessions/${encodeURIComponent(id)}/draw`, capability, {});
      if (!alive || request !== generation || id !== session) return;
      cards = data.cards; followups = data.followups;
      const keep = desired ?? selected;
      selected = cards.some(card => card.id === keep) ? keep : (cards.find(card => card.state === 'waiting') ?? cards[0])?.id ?? '';
      connection = 'Connected'; loadError = ''; setUrl(false);
    } catch (cause) {
      if (request !== generation || !alive) return;
      connection = 'Disconnected'; loadError = cause instanceof Error ? cause.message : 'Unable to load this session.';
    } finally { if (request === generation && alive) loading = false; }
  }
  async function chooseSession(id: string, desired = '', push = true) {
    session = id; selected = desired; cards = []; followups = []; stateFilter = 'all'; kindFilter = 'all'; query = ''; loadError = '';
    setUrl(push); if (id) await draw(id,desired);
  }
  async function refresh(initial = false, reviewed = true) {
    if (loading || busy) return;
    loading = true; const request = ++generation;
    try {
      const next = await api<Workspace>('/api/workspace', capability);
      if (!alive || request !== generation) return;
      workspace = next;
      const requested = initial ? locationSelection() : {session,card:selected};
      const preferred = next.sessions.find(item => item.id === requested.session) ?? [...next.sessions].sort((a,b) => (b.counts.waiting || 0)-(a.counts.waiting || 0) || total(b)-total(a))[0];
      if (!preferred) { session=''; selected=''; cards=[]; followups=[]; loading=false; connection='Connected'; loadError=''; setUrl(false); return; }
      session = preferred.id;
      await draw(session,initial ? requested.card : undefined);
      if (reviewed && !loadError) refused = {};
    } catch (cause) { if (alive && request === generation) { loadError = cause instanceof Error ? cause.message : 'Unable to reach the local server.'; connection='Disconnected'; loading=false; } }
  }
  const draftKey = (offer: Offer) => `${session}:${selected}:${offer.question}`;
  const answered = (card: Card, offer: Offer) => card.answers.some(answer => answer.question === offer.question && answer.answer !== 'open');
  async function compose(offer: Offer, button: Button) { const key = draftKey(offer); composers[key]=button.index; await tick(); document.getElementById(`correction-${offer.offer_id}`)?.focus(); }
  async function press(offer: Offer, button: Button, correction?: string) {
    if (busy || refused[offer.offer_id] || !active || answered(active,offer)) return;
    if (button.answer === 'change' && button.change == null && correction === undefined) { await compose(offer,button); return; }
    if (correction !== undefined && !correction.trim()) return;
    const sourceSession = session, cardId = selected, key = activeKey, ownerDraft = draftKey(offer);
    const body = {offer:offer.offer_id, choice:button.index, ...(correction !== undefined ? {text:correction.trim()} : {})};
    const fingerprint = JSON.stringify([sourceSession,body]);
    const requestId = pending.get(fingerprint) ?? crypto.randomUUID(); pending.set(fingerprint,requestId);
    busy = true; feedback[key] = {};
    try {
      const result = await api<PressResult>(`/api/sessions/${encodeURIComponent(sourceSession)}/press`,capability,{...body,request_id:requestId});
      feedback[key] = {result}; pending.delete(fingerprint);
      if (correction !== undefined) { drafts[ownerDraft]=''; composers[ownerDraft]=undefined; }
      if (sourceSession === session) await draw(sourceSession);
    } catch (cause) {
      const stale = cause instanceof ApiError && cause.status === 409;
      if (stale) refused[offer.offer_id] = true;
      feedback[key] = {error: (cause instanceof Error ? cause.message : 'Unable to save your answer.') + (stale ? ' Refresh to review the latest issue.' : ' Your text is kept; retry the same action to check its receipt.')};
      if (!(cause instanceof ApiError)) connection = 'Disconnected';
    } finally { busy = false; }
  }
  async function popstate() { const target=locationSelection(); if (target.session !== session) await chooseSession(target.session,target.card,false); else selected=target.card; }
  function keyboard(event: KeyboardEvent) {
    if (!drawer || !isNarrow) return;
    if (event.key === 'Escape') { event.preventDefault(); closeDrawer(); }
    if (event.key === 'Tab') {
      const controls = Array.from(inbox?.querySelectorAll<HTMLElement>('button:not(:disabled),input,select,[tabindex="0"]') ?? []);
      const first = controls[0], last = controls.at(-1);
      if (event.shiftKey && document.activeElement === first) {event.preventDefault(); last?.focus();}
      else if (!event.shiftKey && document.activeElement === last) {event.preventDefault(); first?.focus();}
    }
  }
  onMount(() => {
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => { if (!document.hidden && !busy && !loading) await refresh(false,false); if (alive) timer=setTimeout(poll,15000); };
    void refresh(true).then(() => { if (alive) timer=setTimeout(poll,15000); });
    return () => { alive=false; generation++; clearTimeout(timer); };
  });
</script>

<svelte:window bind:innerWidth={viewport} onpopstate={popstate} onkeydown={keyboard}/>
<a class="skip-link" href="#issue-detail">Skip to selected issue</a>
<header class="workspace-header">
  <div class="brand"><span class="plumb-mark" aria-hidden="true">◈</span><strong>plumb</strong><span class="brand-divider">/</span><span class="project-name" title={workspace?.project.root}>{workspace?.project.name ?? 'Issue workspace'}</span>{#if workspace?.project.demo}<span class="demo-label">Isolated demo</span>{/if}</div>
  <div class="header-tools"><div class="section-tabs" aria-label="Section"><button aria-pressed={section === 'issues'} onclick={() => section='issues'}>Questions</button><button aria-pressed={section === 'studies'} onclick={() => section='studies'}>Studies</button></div><label class="session-control"><span>Session</span><select aria-label="Source session" value={session} onchange={event => void chooseSession(event.currentTarget.value)} disabled={!sessions.length || busy}>{#each sessions as item}<option value={item.id}>{item.id} · {item.counts.waiting || 0} waiting · {total(item)} total</option>{/each}</select></label>
    <span class:offline={connection === 'Disconnected'} class="connection"><span class="connection-dot"></span>{connection}</span>
    <button title="Refresh issues and evidence" onclick={() => void refresh()} disabled={loading || busy}>Refresh</button><button onclick={() => help.showModal()}>Help</button>
  </div>
</header>
{#if section === 'studies'}<Studies {capability}/>{:else}
<div class="mobile-bar"><button bind:this={drawerButton} aria-expanded={drawer} aria-controls="issue-inbox" onclick={openDrawer}>Issues <span class="count">{cards.length}</span></button><span>{active ? human(active.state) : 'Issue workspace'}</span></div>
{#if loadError}<div class="connection-error" role="alert"><strong>Connection needs attention.</strong> {loadError} <button onclick={() => void refresh()} disabled={loading || busy}>Retry connection</button></div>{/if}
<div class="workspace" style:--inbox-width={`${leftWidth}px`} style:--evidence-width={`${rightWidth}px`}>
  {#if drawer && isNarrow}<button class="drawer-shade" aria-label="Close issues drawer" onclick={closeDrawer}></button>{/if}
  <aside id="issue-inbox" class="inbox" class:drawer-open={drawer} bind:this={inbox} inert={isNarrow && !drawer} aria-label="Issue inbox">
    <div class="inbox-heading"><div><span class="eyebrow">Owner workspace</span><h2>Issues <span class="count">{cards.length}</span></h2></div><button class="drawer-close" onclick={closeDrawer} aria-label="Close issues">×</button></div>
    <div class="inbox-controls"><input type="search" aria-label="Search issues" placeholder="Search issues and context…" bind:value={query}/>
      <div class="state-filters" aria-label="Filter issue state">{#each states as state}<button aria-pressed={stateFilter === state} onclick={() => stateFilter=state}>{state === 'all' ? 'All' : human(state).replace(/^./, c => c.toUpperCase())}<span class="count">{state === 'all' ? cards.length : cards.filter(card => card.state === state).length}</span></button>{/each}</div>
      <label class="kind-control"><span>Kind</span><select aria-label="Issue kind" bind:value={kindFilter}><option value="all">All kinds</option>{#each kinds as kind}<option value={kind}>{human(kind)}</option>{/each}</select></label>
    </div>
    <nav class="issue-list" aria-label="Issues">{#each visible as card (card.id)}<button class="issue-row" class:selected={card.id === selected} aria-current={card.id === selected ? 'true' : undefined} onclick={() => chooseCard(card.id)}><span class="issue-meta"><span>{human(kindOf(card))}</span><span class="state-dot" class:waiting={card.state === 'waiting'} title={human(card.state)}></span></span><strong>{titleOf(card)}</strong><span class="issue-preview">{card.content?.issue || card.issue}</span><span class="issue-state">{human(card.state)}</span></button>{:else}<div class="inbox-empty">{loading ? 'Loading issues…' : cards.length ? 'No issues match these filters.' : sessions.length ? 'No issues in this session.' : 'No source sessions yet.'}{#if cards.length}<button onclick={() => {query=''; stateFilter='all'; kindFilter='all';}}>Clear filters</button>{/if}</div>{/each}</nav>
    <div class="inbox-foot">Your decisions stay with their source session.</div>
  </aside>
  <div class="left-divider"><Splitter value={leftWidth} min={220} max={380} reset={260} label="Resize issue inbox" title="Drag or use arrow keys. Double-click to reset." onresize={value => leftWidth=value} oncommit={value => saveWidth('plumb.inbox-width',value)}/></div>
  <main id="issue-detail" class="issue-detail" tabindex="-1" aria-busy={loading}>
    {#if active}
      <div class="issue-topline"><span class="eyebrow">{human(kindOf(active))}{#if active.kind === 'clarify' || active.kind === 'trial'} · Read-back{/if}</span><span class="status-badge" class:waiting={active.state === 'waiting'}>{human(active.state)}</span></div>
      <h1>{titleOf(active)}</h1>
      {#if (active.content?.issue || active.issue) !== titleOf(active)}<p class="issue-lead">{active.content?.issue || active.issue}</p>{/if}
      {#if active.reason}<p class="reason">{active.reason}</p>{/if}
      {#if active.content?.context?.length}<section class="context" aria-label="Issue context">{#each active.content.context as line}<p class="prose">{line}</p>{/each}</section>{/if}
      {#if active.content?.assumptions?.length}<section class="assumptions"><h2>Assumptions you can change</h2><ul>{#each active.content.assumptions as assumption}<li>{assumption}</li>{/each}</ul></section>{/if}
      {#if active.content?.wont}<p class="wont"><strong>Outside this proposal</strong><br/>{active.content.wont}</p>{/if}
      {#if active.diagram?.source}<Diagram {session} card={active.id} {capability} source={active.diagram.source} available={active.diagram.available} problem={active.diagram.error}/>{/if}
      {#if message?.error}<div class="action-error" role="alert">{message.error}<button disabled={loading || busy} onclick={() => void refresh()}>Refresh issue</button></div>{/if}
      {#if message?.result}<div class="receipt" role="status"><strong>{message.result.line || 'Answer recorded.'}</strong>{#if message.result.duplicate}<p>This action was already recorded; its existing receipt was returned.</p>{/if}{#if message.result.followup}<p>Follow-up {human(message.result.followup.status)}. Context is retained for the source session's next prompt hook; this does not mean the agent ran or verified a repair.</p>{/if}</div>{/if}
      <section class="decision" aria-label="Owner decisions"><div class="decision-heading"><span class="eyebrow">Your decision</span><span class="muted">Choose what should happen next</span></div>
      {#each active.offers ?? [] as offer, questionIndex (offer.offer_id)}
        {@const question = active.questions.find(item => item.id === offer.question)}
        {@const key = draftKey(offer)}
        <fieldset class="question"><legend>{question?.text || (active.offers.length > 1 ? `Question ${questionIndex + 1}` : 'How would you like to proceed?')}</legend>
          {#if answered(active,offer)}<p class="answered">Answer recorded for this question.</p>
          {:else}
            {#if questionIndex === 0 && active.content?.options?.length}<ol class="option-explanations">{#each active.content.options as option}<li><strong>{option.text}</strong>{#if option.recommended}<span class="recommended">Recommended</span>{/if}{#if option.consequence}<p>{option.consequence}</p>{/if}</li>{/each}</ol>
            {:else if question?.choices?.length}<ol class="option-explanations">{#each question.choices as choice}<li><strong>{choice.label}</strong>{#if choice.consequence}<p>{choice.consequence}</p>{/if}</li>{/each}</ol>{/if}
            <div class="answer-buttons">{#each offer.buttons as button (button.index)}<button class:primary={button.answer === 'accepted'} class:quiet={button.answer === 'open'} disabled={busy || loading || refused[offer.offer_id]} onclick={() => void press(offer,button)}>{button.label}</button>{/each}</div>
            {#if composers[key] !== undefined}{@const changeButton = offer.buttons.find(button => button.index === composers[key] && button.answer === 'change' && button.change == null)}<div class="composer"><label for={`correction-${offer.offer_id}`}>Your correction</label><textarea id={`correction-${offer.offer_id}`} value={drafts[key] ?? ''} oninput={event => drafts[key]=event.currentTarget.value} rows="4" placeholder="What should change, and why?" disabled={busy}></textarea><p class="muted">This text accompanies your answer in the source session's next turn.</p><div class="answer-buttons"><button onclick={() => composers[key]=undefined} disabled={busy}>Cancel</button><button class="primary" disabled={busy || loading || !drafts[key]?.trim() || refused[offer.offer_id] || !changeButton} onclick={() => changeButton && void press(offer,changeButton,drafts[key])}>Send correction</button></div></div>{/if}
          {/if}
        </fieldset>
      {:else}
        {#each active.questions as question}
          <section class="question"><h2>{question.text}</h2>
            <ol class="option-explanations">{#each question.choices ?? [] as choice}<li><strong>{choice.label}</strong>{#if choice.consequence}<p>{choice.consequence}</p>{/if}</li>{/each}</ol>
            {#each active.answers.filter(answer => answer.question === question.id) as answer}<p class="recorded-answer">Recorded answer: {human(answer.answer)}</p>{/each}
          </section>
        {:else}
          <ol class="option-explanations">{#each active.content?.options ?? [] as option}<li><strong>{option.text}</strong>{#if option.recommended}<span class="recommended">Recommended</span>{/if}{#if option.consequence}<p>{option.consequence}</p>{/if}</li>{/each}</ol>
          {#each active.answers as answer}<p class="recorded-answer">Recorded answer: {human(answer.answer)}</p>{/each}
        {/each}
        <p class="settled-note">No answer is currently requested. {active.state === 'done' ? 'This issue is settled; review the evidence for implementation and verification status.' : 'Review the issue state and evidence, or refresh for updated offers.'}</p>
      {/each}
      </section>
      <footer class="issue-footer"><span class="mono">{active.id}</span>{#if active.turn}<span>Turn {active.turn}</span>{/if}{#if active.branch}<span>{active.branch}</span>{/if}</footer>
    {:else}<div class="main-empty"><span class="plumb-mark" aria-hidden="true">◈</span><h1>{loading ? 'Opening your workspace…' : !sessions.length ? 'No source sessions yet' : !cards.length ? 'Nothing waiting here' : 'Select an issue'}</h1><p>{!sessions.length ? 'Plumb issues will appear here when a source session records them.' : 'Use the issue inbox to inspect context, evidence and decisions.'}</p></div>{/if}
  </main>
  <div class="right-divider"><Splitter value={rightWidth} min={260} max={460} reset={320} reverse label="Resize evidence pane" title="Drag or use arrow keys. Double-click to reset." onresize={value => rightWidth=value} oncommit={value => saveWidth('plumb.evidence-width',value)}/></div>
  <Evidence card={active} {followups} {session}/>
</div>
{/if}
<dialog bind:this={help} class="help-dialog" aria-labelledby="help-title"><h2 id="help-title">Decide with the evidence in view</h2><p>Select a source session, inspect an issue and its diagram, then answer an offered question or ask for a change. Leave open keeps the issue available.</p><p>Answers refer to the exact content you saw. If it changes, refresh and review before answering again.</p><p>Queued follow-ups are delivered at the source session's next prompt hook. Plumb does not wake an agent, and an accepted answer is not a verified repair.</p><p>Resize panes with the pointer or arrow keys; Home and End set their limits. Double-click a divider to reset it.</p><p class="muted">This workspace runs on your local loopback server. Fonts and application assets are bundled locally.</p><a href="/assets/THIRD_PARTY_NOTICES.txt" target="_blank" rel="noreferrer">Third-party notices</a><form method="dialog"><button class="primary">Close help</button></form></dialog>
