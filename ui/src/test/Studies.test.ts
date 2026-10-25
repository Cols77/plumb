// SR-319 EX-1..3, SR-365 EX-2, EX-4 and SR-370 in the room: each clip plays at its place in the
// body, the subtitle track on by default, the fallback lines at the clip's place with the rest
// still readable, the pending and failed lines.
import { render, screen, waitFor } from '@testing-library/svelte';
import { describe, it, expect, vi, afterEach } from 'vitest';
import Studies from '../components/Studies.svelte';

const BODY = 'The cascade asks the judge first.\n\n```video\ncascade\n```\n\nThen it builds.\n';
const clip = (state: string, reason = '') => ({clips: {cascade: {state, reason, revisions: 0}}});
const study = (extra: object) => ({slug:'judge-cascade', title:'How the judge cascade runs', step:'plan', why:'the plan adds it', status:'opened', body:BODY, clips:{}, ...extra});

function room(s: any, missing: string[] = []) {
  const revoked: string[] = []; const headers: (string | null)[] = []; const urls: string[] = [];
  let n = 0;
  vi.stubGlobal('URL', Object.assign(URL, {createObjectURL: () => `blob:${++n}`, revokeObjectURL: (u: string) => { revoked.push(u); }}));
  vi.stubGlobal('fetch', vi.fn(async (input: string, init?: any) => {
    if (input.includes('/media/')) { urls.push(input); headers.push(init?.headers?.Authorization ?? null); return missing.some((m) => input.endsWith(m)) ? Response.json({error:'No video'},{status:404}) : new Response('bytes'); }
    if (input.endsWith('/open')) return Response.json(s);
    return Response.json({studies:[s], understanding:{text:'',knows:[],needs:[]}});
  }));
  history.replaceState({}, '', `/?study=${s.slug}`);
  render(Studies, {capability: 'test-token'});
  return {revoked, headers, urls};
}
afterEach(() => history.replaceState({}, '', '/'));

describe('a study mixing text and clips in the room', () => {
  it('SR-319 EX-1, SR-370 EX-1: the clip plays between its paragraphs, fetched with the capability', async () => {
    const {headers, urls} = room(study(clip('ready')));
    const before = await screen.findByText('The cascade asks the judge first.');
    await waitFor(() => expect(document.querySelector('video')).toBeTruthy());
    const video = document.querySelector('video')!; const after = screen.getByText('Then it builds.');
    expect(video).toHaveAttribute('controls');
    expect(before.compareDocumentPosition(video) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(video.compareDocumentPosition(after) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(headers).toEqual(['Bearer test-token', 'Bearer test-token']);
    expect(urls.every((u) => u.includes('/media/cascade/'))).toBe(true);
    expect(document.querySelector('code.language-video')).toBeNull();
  });
  it('SR-365 EX-2: the subtitle track is on by default', async () => {
    room(study(clip('ready')));
    await waitFor(() => expect(document.querySelector('track')).toBeTruthy());
    const track = document.querySelector('track')!;
    expect(track).toHaveAttribute('default'); expect(track).toHaveAttribute('kind', 'subtitles');
  });
  it('SR-319 EX-2: a missing clip shows the fallback line at its place and the text stays', async () => {
    room(study(clip('ready')), ['video']);
    expect(await screen.findByText('The video is unavailable.')).toBeInTheDocument();
    expect(document.querySelector('video')).toBeNull();
    expect(screen.getByText('Then it builds.')).toBeInTheDocument();
  });
  it('SR-365 EX-4: a missing track plays the clip and says the subtitles are unavailable', async () => {
    room(study(clip('ready')), ['subtitles']);
    expect(await screen.findByText('Subtitles are unavailable.')).toBeInTheDocument();
    expect(document.querySelector('video')).toBeTruthy(); expect(document.querySelector('track')).toBeNull();
  });
  it('SR-370 EX-4: a rendering clip loads nothing and says so at its place', async () => {
    const first = room(study(clip('rendering')));
    expect(await screen.findByText('video rendering…')).toBeInTheDocument();
    expect(document.querySelector('video')).toBeNull(); expect(first.headers).toEqual([]);
  });
  it('SR-370 EX-5: a failed clip gives the reason and keeps the rest', async () => {
    room(study(clip('failed', 'beat 2 shows no cascade')));
    expect(await screen.findByText('The video could not be shown: beat 2 shows no cascade')).toBeInTheDocument();
    expect(screen.getByText('The cascade asks the judge first.')).toBeInTheDocument();
  });
});
