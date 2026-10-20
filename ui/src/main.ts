import { mount } from 'svelte';
import App from './App.svelte';
import './app.css';
import { reloadOnStaleBuild } from './lib/stale';
reloadOnStaleBuild(window, import.meta.url);
mount(App, {target: document.getElementById('app')!});
