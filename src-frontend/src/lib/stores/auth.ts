import { writable, derived } from 'svelte/store';
import type { AuthStatusData } from '$lib/mcp/types';

export type { AuthStatusData };

export const authStatus = writable<AuthStatusData | null>(null);
export const isLoggingIn = writable(false);
export const loginError = writable<string | null>(null);

export const isAuthenticated = derived(
  authStatus,
  ($status) => $status?.authenticated ?? false
);
