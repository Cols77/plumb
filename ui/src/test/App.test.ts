import { render, screen, waitFor, fireEvent } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import App from '../App.svelte';

const offer = (id = 'offer-one', question = 'q1') => ({ offer_id: id, question, buttons: [
  {index: 7, label: 'Keep CSV', answer: 'accepted', change: null, consequence: 'Spreadsheets still work'},
  {index: 12, label: 'Ask for a change', answer: 'change', change: null},
  {index: 19, label: 'Leave open', answer: 'open', change: null},
] });
const card = (id = 'one', topic = 'Export format') => ({id, topic, kind: 'choice', issue: 'Choose a format.', evidence: 'Full source evidence', state: 'waiting', status: 'open', answers: [], questions: [{id:'q1',text:'Which format?'}], offers: [offer()], records: [], diff: null, diagram: {source:'',available:false}, content: {topic, issue:'Choose a format.',context:['First context','Second context','Uncut doubt: Yes confirms only the wording'],assumptions:['Files stay local'],wont:'Send email',options:[{text:'Keep CSV',consequence:'Spreadsheets still work',recommended:false}]} });
function server(cards: any[] = [card()], press?: (body: any) => Response | Promise<Response>) {
  const calls: any[] = [];
  vi.stubGlobal('fetch', vi.fn(async (input: string, init?: RequestInit) => {
    if (input === '/api/workspace') return Response.json({project:{name:'Test project',root:'/test',demo:true},sessions:[{id:'source-session',counts:{waiting:cards.length}}]});
    if (input.endsWith('/draw')) return Response.json({session:'source-session',cards,followups:[]});
    if (input.endsWith('/press')) { const body = JSON.parse(String(init?.body)); calls.push(body); return press ? press(body) : Response.json({line:'Owner answer saved.',followup:{id:'f1',status:'queued'}}); }
    throw Error('Unexpected route '+ input);
  }));
  return calls;
}
describe('Owner issue workflow', () => {
  it('selects issues, searches every context entry and filters state', async () => {
    server([card(), {...card('two','Saved filters'),state:'done',offers:[]}]); render(App);
    await screen.findByRole('heading',{name:'Export format'});
    const user = userEvent.setup();
    await user.click(screen.getByRole('button',{name:/Saved filters/}));
    expect(screen.getByRole('heading',{name:'Saved filters'})).toBeInTheDocument();
    await user.type(screen.getByRole('searchbox'), 'Uncut doubt');
    expect(screen.getByRole('button',{name:/Export format/})).toBeInTheDocument();
    await user.click(screen.getByRole('button',{name:/Waiting/}));
    expect(screen.queryByRole('button',{name:/Saved filters/})).not.toBeInTheDocument();
  });
  it('removes launch token and submits the actual stored button index and offer', async () => {
    const calls = server(); render(App); const user = userEvent.setup();
    await user.click(await screen.findByRole('button',{name:'Keep CSV'}));
    await screen.findByText('Owner answer saved.');
    expect(calls[0]).toMatchObject({offer:'offer-one',choice:7});
    expect(calls[0].request_id).toMatch(/^[\w-]+$/);
    expect(location.hash).toBe('');
    expect(sessionStorage.getItem('plumb.capability')).toBe('test-token');
    expect(screen.getByRole('status')).toHaveTextContent(/next prompt hook/i);
  });
  it('requires correction text and preserves draft and request identity after network failure', async () => {
    let attempt = 0;
    const calls = server(undefined, () => { if (++attempt === 1) throw Error('Offline'); return Response.json({line:'Correction saved.',followup:{status:'queued'}}); });
    render(App); const user = userEvent.setup();
    await user.click(await screen.findByRole('button',{name:'Ask for a change'}));
    expect(screen.getByRole('button',{name:'Send correction'})).toBeDisabled();
    await user.type(screen.getByRole('textbox',{name:'Your correction'}), 'Keep nested addresses');
    await user.click(screen.getByRole('button',{name:'Send correction'}));
    await screen.findByText(/Offline/);
    await user.click(screen.getByRole('button',{name:'Refresh'}));
    expect(screen.getByRole('textbox',{name:'Your correction'})).toHaveValue('Keep nested addresses');
    await user.click(screen.getByRole('button',{name:'Send correction'}));
    await screen.findByText('Correction saved.');
    expect(calls[0]).toMatchObject({choice:12,text:'Keep nested addresses'});
    expect(calls[1].request_id).toBe(calls[0].request_id);
  });
  it('reports stale refusal without implying the action succeeded', async () => {
    server(undefined, () => Response.json({error:'The displayed offer is stale. Refresh before answering.'},{status:409})); render(App);
    await fireEvent.click(await screen.findByRole('button',{name:'Keep CSV'}));
    expect(await screen.findByRole('alert')).toHaveTextContent(/stale/);
    expect(screen.queryByText('Owner answer saved.')).not.toBeInTheDocument();
    await fireEvent.click(screen.getByRole('button',{name:'Refresh issue'}));
    await waitFor(() => expect(screen.getByRole('button',{name:'Keep CSV'})).not.toBeDisabled());
  });
  it('labels multiple questions and suppresses actions for answered questions', async () => {
    const first = card(); first.questions.push({id:'q2',text:'Which destination?'}); first.offers.push(offer('offer-two','q2'));
    (first.answers as any[]).push({question:'q1',answer:'accepted'});
    const calls = server([first]); render(App);
    await screen.findByText('Which destination?');
    expect(screen.getAllByRole('button',{name:'Keep CSV'})).toHaveLength(1);
    await fireEvent.click(screen.getByRole('button',{name:'Keep CSV'}));
    await waitFor(() => expect(calls[0].offer).toBe('offer-two'));
  });
  it('keeps Ask for a change distinct from an earlier custom-text Both choice', async () => {
    const c = card(); c.offers[0].buttons.unshift({index:3,label:'Both',answer:'change',change:null});
    const calls=server([c]); render(App); const user=userEvent.setup();
    await user.click(await screen.findByRole('button',{name:'Ask for a change'}));
    await user.type(screen.getByRole('textbox',{name:'Your correction'}),'Use an alternative');
    await user.click(screen.getByRole('button',{name:'Send correction'}));
    await waitFor(() => expect(calls[0]?.choice).toBe(12));
  });
  it('suppresses duplicate clicks while a request is in flight', async () => {
    let resolve!: (response:Response) => void;
    const calls=server(undefined, () => new Promise<Response>(r => resolve=r)); render(App);
    const button=await screen.findByRole('button',{name:'Keep CSV'});
    await fireEvent.click(button); await fireEvent.click(button);
    expect(calls).toHaveLength(1); expect(button).toBeDisabled();
    resolve(Response.json({line:'Saved once.'})); await screen.findByText('Saved once.');
  });
  it('keeps questions actionable when a correction draw has no settled answer', async () => {
    server(); render(App); const user=userEvent.setup();
    await user.click(await screen.findByRole('button',{name:'Ask for a change'}));
    await user.type(screen.getByRole('textbox',{name:'Your correction'}),'Revise the proposal');
    await user.click(screen.getByRole('button',{name:'Send correction'}));
    await screen.findByText('Owner answer saved.');
    await waitFor(() => expect(screen.getByRole('button',{name:'Keep CSV'})).not.toBeDisabled());
  });
  it('cancels a correction without sending and keeps draft when reopened', async () => {
    const calls=server(); render(App); const user=userEvent.setup();
    await user.click(await screen.findByRole('button',{name:'Ask for a change'}));
    await user.type(screen.getByRole('textbox',{name:'Your correction'}),'My draft');
    await user.click(screen.getByRole('button',{name:'Cancel'})); expect(calls).toHaveLength(0);
    await user.click(screen.getByRole('button',{name:'Ask for a change'})); expect(screen.getByRole('textbox',{name:'Your correction'})).toHaveValue('My draft');
  });
  it('restores selection through URL navigation and keeps it on refresh', async () => {
    server([card(),card('two','Second issue')]); render(App);
    await screen.findByRole('heading',{name:'Export format'});
    await fireEvent.click(screen.getByRole('button',{name:/Second issue/}));
    expect(new URL(location.href).searchParams.get('card')).toBe('two');
    await fireEvent.click(screen.getByRole('button',{name:'Refresh'}));
    await waitFor(() => expect(screen.getByRole('button',{name:'Refresh'})).not.toBeDisabled());
    expect(screen.getByRole('heading',{name:'Second issue'})).toBeInTheDocument();
    history.replaceState({},'', '/?session=source-session&card=one'); window.dispatchEvent(new PopStateEvent('popstate'));
    await screen.findByRole('heading',{name:'Export format'});
  });
  it('keeps a selection made while a same-session refresh is pending', async () => {
    const cards=[card(),card('two','Second issue')]; server(cards);
    const original=fetch; let resolve!: (response:Response) => void; let hold=false;
    vi.stubGlobal('fetch',vi.fn((url:string,init?:RequestInit) => hold && url.endsWith('/draw') ? new Promise<Response>(r => resolve=r) : original(url,init)));
    render(App); await screen.findByRole('heading',{name:'Export format'});
    hold=true; await fireEvent.click(screen.getByRole('button',{name:'Refresh'}));
    await waitFor(() => expect(resolve).toBeDefined());
    await fireEvent.click(screen.getByRole('button',{name:/Second issue/}));
    resolve(Response.json({cards,followups:[]}));
    await waitFor(() => expect(screen.getByRole('button',{name:'Refresh'})).not.toBeDisabled());
    expect(screen.getByRole('heading',{name:'Second issue'})).toBeInTheDocument();
    expect(new URL(location.href).searchParams.get('card')).toBe('two');
  });
  it('uses effective drift kind and shows a recoverable empty filter result', async () => {
    const c=card(); (c.content as any).kind='drift'; c.kind='stale_link'; server([c]); render(App);
    await screen.findByRole('heading',{name:'Export format'});
    await fireEvent.change(screen.getByRole('combobox',{name:'Issue kind'}),{target:{value:'drift'}});
    expect(screen.getByRole('button',{name:/Export format/})).toBeInTheDocument();
    await fireEvent.input(screen.getByRole('searchbox'),{target:{value:'unfindable'}});
    expect(screen.getByText('No issues match these filters.')).toBeInTheDocument();
    await fireEvent.click(screen.getByRole('button',{name:'Clear filters'}));
    expect(screen.getByRole('searchbox')).toHaveValue('');
  });
  it('ignores a slow draw after the owner selects another source session', async () => {
    let resolve!: (response:Response) => void;
    vi.stubGlobal('fetch',vi.fn((url:string) => {
      if(url==='/api/workspace') return Promise.resolve(Response.json({project:{name:'Race',demo:false},sessions:[{id:'slow',counts:{waiting:3}},{id:'fast',counts:{waiting:1}}]}));
      if(url.includes('/slow/')) return new Promise<Response>(r => resolve=r);
      return Promise.resolve(Response.json({cards:[card('fast-card','Fast session')],followups:[]}));
    }));
    render(App);
    await screen.findByRole('option',{name:/slow/});
    await fireEvent.change(screen.getByRole('combobox',{name:'Source session'}),{target:{value:'fast'}});
    await screen.findByRole('heading',{name:'Fast session'});
    resolve(Response.json({cards:[card('slow-card','Stale session')],followups:[]}));
    await new Promise(r => setTimeout(r,0)); expect(screen.queryByRole('heading',{name:'Stale session'})).not.toBeInTheDocument();
  });
  it('retains settled questions, consequences and recorded answers without adding actions', async () => {
    const c:any=card(); c.offers=[]; c.state='done'; c.answers=[{question:'q1',answer:'accepted'}];
    c.questions[0].choices=[{label:'Keep CSV',answer:'accepted',consequence:'Spreadsheets still work'}];
    c.questions.push({id:'q2',text:'Keep the full address?',choices:[{label:'Full address',consequence:'Preserves international delivery'}]});
    server([c]); render(App);
    await screen.findByText('Keep the full address?');
    expect(screen.getByText('Preserves international delivery')).toBeInTheDocument();
    expect(screen.getByText('Recorded answer: accepted')).toBeInTheDocument();
    expect(screen.queryByRole('button',{name:'Keep CSV'})).not.toBeInTheDocument();
  });
  it('explains record confirmation and coverage while keeping technical JSON collapsed', async () => {
    const c:any=card(); c.records=[{id:'SR-001',title:'Export requirement',body:'Full wording',fields:{},hash:'sha256:abc',status:{confirmation:'proposed',covered:false,uncovered_examples:['EX-2'],links:[{state:'stale',link:{target:'tests/test_export.py'}}]}}];
    server([c]); render(App);
    await screen.findByText('Not yet confirmed');
    expect(screen.getByText('Examples without current coverage: EX-2')).toBeInTheDocument();
    expect(screen.getByText('stale · tests/test_export.py')).toBeInTheDocument();
    expect(screen.getByText('Technical details').closest('details')).not.toHaveAttribute('open');
  });
});
