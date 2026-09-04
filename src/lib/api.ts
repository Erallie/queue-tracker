import { env } from '$env/dynamic/public';
import { demoAccount, demoCatalog, demoGroups, demoSettings } from './demo';
import type { Account, Catalog, QueueState, Settings, SongGroup } from './types';

const api = (env.PUBLIC_QUEUE_API_URL || '').replace(/\/$/, '');

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  if (!api) throw new Error('demo');
  const response = await fetch(api + path, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
  return body as T;
}

export async function getCatalog(): Promise<Catalog> {
  try { return await request<Catalog>('/api/catalog'); } catch { return demoCatalog; }
}

export async function getAccount(): Promise<Account> {
  try { return await request<Account>('/api/me'); } catch { return demoAccount; }
}

export async function getQueue(): Promise<QueueState> {
  if (!api) return { queue: [], connected: false };
  return request<QueueState>('/api/queue');
}

export function watchQueue(update: (state: QueueState) => void): () => void {
  if (!api || typeof EventSource === 'undefined') return () => {};
  const events = new EventSource(`${api}/api/queue/events`);
  events.addEventListener('queue', (event) => {
    try { update(JSON.parse((event as MessageEvent).data) as QueueState); } catch { /* A reconnect delivers another snapshot. */ }
  });
  return () => events.close();
}

export async function getAdmin(): Promise<{ settings: Settings; groups: SongGroup[]; catalog: Catalog }> {
  if (!api) return { settings: demoSettings, groups: demoGroups, catalog: demoCatalog };
  return request('/api/admin');
}

export function authUrl(provider: string, mode = 'login'): string {
  const returnTo = `${location.origin}${location.pathname.replace(/\/[^/]*$/, '')}/account`;
  return `${api}/auth/${provider}?mode=${mode}&return_to=${encodeURIComponent(returnTo)}`;
}

export async function requestSong(songId: string): Promise<{ queued: boolean; message: string }> {
  return request(`/api/songs/${encodeURIComponent(songId)}/request`, { method: 'POST' });
}

export async function logout(): Promise<void> { await request('/api/logout', { method: 'POST' }); }
export async function unlink(provider: string): Promise<{ account_deleted: boolean }> { return request(`/api/identities/${provider}`, { method: 'DELETE' }); }
export async function saveSettings(settings: Settings): Promise<void> { await request('/api/admin/settings', { method: 'PUT', body: JSON.stringify(settings) }); }
export async function saveGroups(groups: SongGroup[]): Promise<void> { await request('/api/admin/groups', { method: 'PUT', body: JSON.stringify({ groups }) }); }
export async function saveTags(tags: Catalog['tags']): Promise<void> { await request('/api/admin/tags', { method: 'PUT', body: JSON.stringify({ tags }) }); }
export async function saveSongTags(songId: string, tags: string[]): Promise<void> { await request(`/api/admin/songs/${songId}/tags`, { method: 'PUT', body: JSON.stringify({ tags }) }); }
export async function adjustPlay(songId: string, delta: number): Promise<void> { await request(`/api/admin/songs/${songId}/plays`, { method: 'POST', body: JSON.stringify({ delta }) }); }
export async function removeNewTag(songId: string): Promise<void> { await request(`/api/admin/songs/${songId}/new`, { method: 'DELETE' }); }
