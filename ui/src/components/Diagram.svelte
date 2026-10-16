<script lang="ts">
  import { api } from '../lib/api';
  import { prepareDiagram } from '../lib/diagram';
  let { session, card, capability, source, available, problem = '' }: { session: string; card: string; capability: string; source: string; available: boolean; problem?: string } = $props();
  let url = $state(''); let description = $state(''); let error = $state(''); let loading = $state(false);
  let zoom = $state(1); let svg = $state(''); let showSource = $state(false); let retry = $state(0);
  $effect(() => {
    const currentSession = session, currentCard = card; const canLoad = available; const existingProblem = problem; void retry; void source;
    let live = true; let ownedUrl = '';
    url = ''; error = ''; svg = ''; description = ''; loading = false; zoom = 1; showSource = false;
    if (!canLoad) { error = existingProblem || 'Diagram source is unavailable.'; return; }
    loading = true;
    api<{text: string | null; error?: string}>(`/api/sessions/${encodeURIComponent(currentSession)}/diagram?card=${encodeURIComponent(currentCard)}`, capability)
      .then(result => {
        if (!live) return;
        if (!result.text) throw Error(result.error || 'Diagram source is unavailable.');
        const prepared = prepareDiagram(result.text);
        ownedUrl = URL.createObjectURL(new Blob([prepared.svg], {type:'image/svg+xml'}));
        url = ownedUrl; svg = prepared.svg; description = prepared.description;
      }).catch(cause => { if (live) error = cause.message; }).finally(() => { if (live) loading = false; });
    return () => { live = false; if (ownedUrl) URL.revokeObjectURL(ownedUrl); };
  });
</script>
<section class="diagram" aria-label="Issue diagram">
  <div class="diagram-head"><span class="eyebrow">The decision, illustrated</span><span class="source-name" title={source}>{source}</span></div>
  {#if loading}<p class="diagram-fallback" role="status">Loading diagram…</p>
  {:else if error}<div class="diagram-fallback"><p>{error}</p>{#if available}<button onclick={() => retry++}>Retry diagram</button>{/if}</div>
  {:else if url}
    <div class="diagram-viewport"><img src={url} alt={description} style:width={`${zoom * 100}%`} /></div>
    <div class="diagram-tools" aria-label="Diagram controls">
      <button aria-label="Zoom out" title="Zoom out" disabled={zoom <= 0.5} onclick={() => zoom = Math.max(0.5, zoom - 0.25)}>−</button>
      <output aria-label="Diagram zoom">{Math.round(zoom * 100)}%</output>
      <button aria-label="Zoom in" title="Zoom in" disabled={zoom >= 3} onclick={() => zoom = Math.min(3, zoom + 0.25)}>+</button>
      <button onclick={() => zoom = 1}>Fit</button>
      <a class="button" href={url} download="plumb-diagram.svg">Download SVG</a>
      <button aria-expanded={showSource} onclick={() => showSource = !showSource}>{showSource ? 'Hide source' : 'Show source'}</button>
    </div>
    <p class="diagram-description">{description}</p>
    {#if showSource}<pre class="source-code" aria-label="Sanitized SVG source">{svg}</pre>{/if}
  {/if}
</section>
