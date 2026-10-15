import { render, screen, fireEvent } from '@testing-library/svelte';
import { expect, it, vi } from 'vitest';
import Splitter from '../components/Splitter.svelte';
it('grows a right pane when its left divider moves left', async () => {
  const resize=vi.fn();
  render(Splitter,{value:320,min:260,max:460,reset:320,label:'Right pane',reverse:true,onresize:resize,oncommit:vi.fn()} as any);
  await fireEvent.keyDown(screen.getByRole('separator'),{key:'ArrowLeft'});
  expect(resize).toHaveBeenLastCalledWith(336);
});
it('uses limits and double-click reset', async () => {
  const resize=vi.fn(); render(Splitter,{value:300,min:220,max:380,reset:260,label:'Left pane',onresize:resize,oncommit:vi.fn()});
  const grip=screen.getByRole('separator');
  await fireEvent.keyDown(grip,{key:'Home'}); expect(resize).toHaveBeenLastCalledWith(220);
  await fireEvent.keyDown(grip,{key:'End'}); expect(resize).toHaveBeenLastCalledWith(380);
  await fireEvent.dblClick(grip); expect(resize).toHaveBeenLastCalledWith(260);
});
