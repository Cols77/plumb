// SR-319 EX-1..3 and SR-365 EX-2, EX-4 in the room: the player above the text, the subtitle
// track on by default, the fallback lines with the text still readable, the pending and failed lines.
import { render, screen, waitFor } from '@testing-library/svelte';
import { describe, it, expect, vi, afterEach } from 'vitest';
import Studies from '../components/Studies.svelte';

const study = (extra: object) => ({slug:'judge-cascade', title:'How the judge cascade runs', step:'plan', why:'the plan adds it', status:'opened', body:'The cascade asks the judge first.', video:'', video_reason:'', ...extra});

function room(s: any, missing: string[] = []) {
  const revoked: string[] = []; const headers: (string | null)[] = [];
  let n = 0;
  vi.stubGlobal('URL', Object.assign(URL, {createObjectURL: () => `blob:${++n}`, revokeObjectURL: (u: string) => { revoked.push(u); }}));
  vi.stubGlobal('fetch', vi.fn(async (input: string, init?: any) => {
    if (input.includes('/media/')) { headers.push(init?.headers?.Authorization ?? null); return missing.some((m) => input.endsWith(m)) ? Response.json({error:'No video'},{status:404}) : new Response('bytes'); }
    if (input.endsWith('/open')) return Response.json(s);
    return Response.json({studies:[s], understanding:{text:'',knows:[],needs:[]}});
  }));
  history.replaceState({}, '', `/?study=${s.slug}`);
  render(Studies, {capability: 'test-token'});
  return {revoked, headers};
}
afterEach(() => history.replaceState({}, '', '/'));

describe('a video study in the room', () => {
  it('SR-319 EX-1: the player shows above the text, fetched with the capability', async () => {
    const {headers} = room(study({video:'ready'}));
    const text = await screen.findByText('The cascade asks the judge first.');
    await waitFor(() => expect(document.querySelector('video')).toBeTruthy());
    const video = document.querySelector('video')!;
    expect(video).toHaveAttribute('controls');
    expect(video.compareDocumentPosition(text) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(headers).toEqual(['Bearer test-token', 'Bearer test-token']);
  });
  it('SR-365 EX-2: the subtitle track is on by default', async () => {
    room(study({video:'ready'}));
    await waitFor(() => expect(document.querySelector('track')).toBeTruthy());
    const track = document.querySelector('track')!;
    expect(track).toHaveAttribute('default'); expect(track).toHaveAttribute('kind', 'subtitles');
  });
  it('SR-319 EX-2: a missing video shows the fallback line and the text stays', async () => {
    room(study({video:'ready'}), ['video']);
    expect(await screen.findByText('The video is unavailable.')).toBeInTheDocument();
    expect(document.querySelector('video')).toBeNull();
    expect(screen.getByText('The cascade asks the judge first.')).toBeInTheDocument();
  });
  it('SR-365 EX-4: a missing track plays the video and says the subtitles are unavailable', async () => {
    room(study({video:'ready'}), ['subtitles']);
    expect(await screen.findByText('Subtitles are unavailable.')).toBeInTheDocument();
    expect(document.querySelector('video')).toBeTruthy(); expect(document.querySelector('track')).toBeNull();
  });
  it('SR-319 EX-3: a study that is not ready loads nothing; rendering and failed say so', async () => {
    const first = room(study({video:'rendering'}));
    expect(await screen.findByText('video rendering…')).toBeInTheDocument();
    expect(document.querySelector('video')).toBeNull(); expect(first.headers).toEqual([]);
  });
  it('a failed video gives the reason and keeps the text', async () => {
    room(study({video:'failed', video_reason:'beat 2 shows no cascade'}));
    expect(await screen.findByText('The video could not be shown: beat 2 shows no cascade')).toBeInTheDocument();
    expect(screen.getByText('The cascade asks the judge first.')).toBeInTheDocument();
  });
});
