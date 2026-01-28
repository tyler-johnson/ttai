import { writable, derived } from 'svelte/store';

export type ConnectionState = 'connecting' | 'connected' | 'error';

export const connectionState = writable<ConnectionState>('connecting');

export const isConnected = derived(
  connectionState,
  ($state) => $state === 'connected'
);
