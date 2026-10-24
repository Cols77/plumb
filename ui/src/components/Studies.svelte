<script lang="ts">
  // Studies and the Understanding page (SR-292..294; DEC-151): beside the questions, never an
  // answer to a session (DEC-152). A study about a conflict lays out both sides; no choice here.
  import { onMount, tick } from 'svelte';
  import { api } from '../lib/api';
  import { drawDiagrams, studyHtml } from '../lib/markdown';
  import type { Study, StudyList, Understanding } from '../lib/types';
  let { capability }: { capability: string } = $props();
  let studies = $state<Study[]>([]); let understanding = $state<Understanding>({text:'',knows:[],needs:[]});
  let selected = $state(''); let open = $state<Study>(); let draft = $state(''); let error = $state(''); let saved = $state(''); let busy = $state(false);
  const UNDERSTANDING = '#understanding';
  let bodyEl = $state<HTMLElement>();
  const html = $derived(studyHtml(open?.body ?? ''));
  // SR-293: the diagrams are drawn once the study's HTML is in place
  $effect(() => { void html; const el = bodyEl; if (el) void tick().then(() => drawDiagrams(el)); });
  async function load() {
    try { const data = await api<StudyList>('/api/studies', capability); studies = data.studies; understanding = data.understanding; if (selected === UNDERSTANDING && !busy) draft = understanding.text; error = ''; }
    catch (cause) { error = cause instanceof Error ? cause.message : 'Unable to load the studies.'; }
  }
  async function choose(slug: string) {
    selected = slug; saved = ''; open = undefined;
    // the URL names the open study, so a reload onto a newer build (SR-342) comes back to it
    const url = new URL(location.href); url.searchParams.set('study', slug); history.replaceState(history.state, '', url);
    if (slug === UNDERSTANDING) { draft = understanding.text; return; }
    try { open = await api<Study>(`/api/studies/${encodeURIComponent(slug)}/open`, capability, {}); await load(); }
    catch (cause) { error = cause instanceof Error ? cause.message : 'Unable to open the study.'; }
  }
  async function mark(how: 'known' | 'deeper') {
    if (!open || busy) return; busy = true;
    try { const data = await api<{study: Study; understanding: Understanding}>(`/api/studies/${encodeURIComponent(open.slug)}/mark`, capability, {mark: how}); open = data.study; understanding = data.understanding; saved = how === 'known' ? 'Noted: you know this. No more studies on it at this depth.' : 'Noted: a deeper study on this can come next.'; await load(); }
    catch (cause) { error = cause instanceof Error ? cause.message : 'Unable to save.'; } finally { busy = false; }
  }
  async function save() {
    busy = true;
    try { understanding = await api<Understanding>('/api/understanding', capability, {text: draft}); draft = understanding.text; saved = 'Your understanding is saved.'; error = ''; }
    catch (cause) { error = cause instanceof Error ? cause.message : 'Unable to save.'; } finally { busy = false; }
  }
  onMount(() => { const asked = new URLSearchParams(location.search).get('study'); void (asked ? choose(asked) : load()); const timer = setInterval(() => { if (!document.hidden) void load(); }, 15000); return () => clearInterval(timer); });
</script>
<div class="studies">
  <nav class="study-list" aria-label="Studies">
    <div class="inbox-heading"><div><span class="eyebrow">Learn the system</span><h2>Studies <span class="count">{studies.length}</span></h2></div></div>
    <button class="issue-row" class:selected={selected === UNDERSTANDING} aria-current={selected === UNDERSTANDING ? 'true' : undefined} onclick={() => void choose(UNDERSTANDING)}><span class="issue-meta"><span>your picture</span></span><strong>Understanding</strong><span class="issue-preview">{understanding.knows.length} known · {understanding.needs.length} to learn</span></button>
    {#each studies as item (item.slug)}<button class="issue-row" class:selected={item.slug === selected} aria-current={item.slug === selected ? 'true' : undefined} onclick={() => void choose(item.slug)}><span class="issue-meta"><span>{item.step}</span>{#if item.status === 'new'}<span class="study-new">new</span>{/if}{#if item.changed}<span class="study-new">out of date</span>{/if}</span><strong>{item.title}</strong><span class="issue-preview">{item.why}</span></button>
    {:else}<div class="inbox-empty">No study yet. During an intent loop the agent may write one per step.</div>{/each}
  </nav>
  <main class="issue-detail" aria-live="polite">
    {#if error}<div class="action-error" role="alert">{error}</div>{/if}
    {#if selected === UNDERSTANDING}
      <span class="eyebrow">Your understanding</span><h1>What you know of the system</h1>
      <p class="muted">One line each: <span class="mono">- knows: …</span> or <span class="mono">- needs: …</span>. Studies follow it: none on what you know, deeper ones on what you need.</p>
      <label class="sr-only" for="understanding-text">Your understanding</label>
      <textarea id="understanding-text" rows="14" bind:value={draft} disabled={busy}></textarea>
      <div class="answer-buttons"><button class="primary" disabled={busy || draft === understanding.text} onclick={() => void save()}>Save</button></div>
    {:else if open}
      <span class="eyebrow">Study · {open.step} step</span><h1>{open.title}</h1>
      <p class="issue-lead">{open.why}</p>
      <!-- SR-360 EX-2: a record it was written from changed; the band offers the rewrite -->
      {#if open.changed}<p class="receipt" role="status">out of date: {open.changed} changed</p>{/if}
      <div class="study-body" bind:this={bodyEl}>{@html html}</div>
      <div class="answer-buttons"><button class="primary" disabled={busy} onclick={() => void mark('known')}>I know this</button><button disabled={busy} onclick={() => void mark('deeper')}>Go deeper</button></div>
      <p class="muted">These correct your understanding only; they answer nothing in a session.</p>
    {:else}<div class="main-empty"><span class="plumb-mark" aria-hidden="true">◈</span><h1>Studies</h1><p>Open a study, or your understanding.</p></div>{/if}
    {#if saved}<div class="receipt" role="status"><strong>{saved}</strong></div>{/if}
  </main>
</div>
