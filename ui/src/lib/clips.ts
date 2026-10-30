// A study's ```video blocks as players at their place in the body (SR-319, SR-370). A ready clip
// is fetched with the capability into object URLs (a <video> cannot send the header); any other
// state leaves a line at its place, and the rest of the study stays readable.
import type { Clip } from './types';

type Fetch = (clip: string, kind: 'video' | 'subtitles') => Promise<string>;

/** Turn each ```video block under `root` into its clip's place, then fill each place. */
export async function placeClips(root: HTMLElement, clips: Record<string, Clip>, fetchUrl: Fetch, gone: () => boolean): Promise<void> {
  for (const code of Array.from(root.querySelectorAll<HTMLElement>('pre > code.language-video'))) {
    const box = document.createElement('div');
    box.className = 'study-clip'; box.dataset.clip = (code.textContent ?? '').trim();
    code.parentElement!.replaceWith(box);
  }
  for (const box of Array.from(root.querySelectorAll<HTMLElement>('.study-clip'))) {
    const name = box.dataset.clip ?? ''; const held = clips[name];
    const parts: HTMLElement[] = [];
    const line = (text: string) => { const p = document.createElement('p'); p.className = 'muted'; p.setAttribute('role', 'status'); p.textContent = text; parts.push(p); };
    if (held?.state === 'failed') line(`The video could not be shown: ${held.reason}`);
    else if (held?.state !== 'ready') line('video rendering…');
    else {
      const wait = document.createElement('p'); wait.className = 'muted'; wait.setAttribute('role', 'status'); wait.textContent = 'loading video…';
      box.replaceChildren(wait);
      const [video, track] = await Promise.allSettled([fetchUrl(name, 'video'), fetchUrl(name, 'subtitles')]);
      if (video.status !== 'fulfilled') line('The video is unavailable.');
      else {
        const player = document.createElement('video');
        player.className = 'study-video'; player.controls = true; player.src = video.value;
        if (track.status === 'fulfilled') {
          const t = document.createElement('track');
          t.kind = 'subtitles'; t.srclang = 'en'; t.label = 'Explanations'; t.src = track.value; t.default = true;
          player.append(t);
        }
        parts.push(player);
        if (track.status !== 'fulfilled') line('Subtitles are unavailable.');
      }
    }
    if (gone()) return;
    box.replaceChildren(...parts);
  }
}
