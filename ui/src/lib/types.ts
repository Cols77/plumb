export type Workspace = { project: {name: string; root: string} };
export type Study = { slug: string; title: string; topic: string; step: string; loop: string; why: string; status: 'new' | 'opened' | 'known' | 'deeper'; body?: string; changed?: string; clips?: Record<string, Clip> };
export type Clip = { state: '' | 'rendering' | 'checking' | 'ready' | 'failed'; reason: string; revisions: number };
export type Understanding = { text: string; knows: string[]; needs: string[] };
export type StudyList = { studies: Study[]; understanding: Understanding };
