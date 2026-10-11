// plumb's mod (SP7 5; SR-085, SR-086, SR-087): the band, the card panel with its buttons, the
// /plumb answers drawn in the transcript and the session background. Slice 7 builds it; until
// then this module registers nothing, so Claude Code loads the plugin and the command hooks in
// hooks.json do all the work (the fallback of SP7 5.8: no mod.json is written, and the hooks
// print and inject everything as before).
import type { Register } from 'claude-code'

export const register: Register = () => {}
