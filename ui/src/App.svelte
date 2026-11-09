<script lang="ts">
  // The study room (SR-380): the studies and the understanding page. No card is drawn or
  // pressed here; the questions are put to the owner in the session.
  import { onMount } from 'svelte';
  import { api, takeCapability } from './lib/api';
  import type { Workspace } from './lib/types';
  import Studies from './components/Studies.svelte';

  const capability = takeCapability();
  let workspace = $state<Workspace>();
  onMount(() => { void api<Workspace>('/api/workspace', capability).then(next => { workspace = next; }).catch(() => {}); });
</script>

<header class="workspace-header">
  <div class="brand"><span class="iaso-mark" aria-hidden="true">◈</span><strong>iaso</strong><span class="brand-divider">/</span><span class="project-name" title={workspace?.project.root}>{workspace?.project.name ?? 'Study room'}</span></div>
</header>
<main id="study-room" tabindex="-1"><Studies {capability}/></main>
