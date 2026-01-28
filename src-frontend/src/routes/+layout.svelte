<script lang="ts">
  import '../app.css';
  import { onMount } from 'svelte';
  import { invoke } from '@tauri-apps/api/core';
  import Navbar from '$lib/components/Navbar.svelte';
  import { connectionState } from '$lib/stores/connection';
  import { authStatus, type AuthStatusData } from '$lib/stores/auth';

  let { children } = $props();

  async function initializeConnection() {
    connectionState.set('connecting');

    try {
      // Ping to check if already connected
      await invoke<string>('mcp_ping');
      connectionState.set('connected');

      const status = await invoke<AuthStatusData>('mcp_get_auth_status');
      authStatus.set(status);
    } catch {
      // Not connected yet, wait for auto-start to complete
      // The Tauri backend auto-starts the server on launch
      try {
        // Give it a moment then try again
        await new Promise((resolve) => setTimeout(resolve, 2000));
        await invoke<string>('mcp_ping');
        connectionState.set('connected');

        const status = await invoke<AuthStatusData>('mcp_get_auth_status');
        authStatus.set(status);
      } catch (error) {
        console.error('Connection error:', error);
        connectionState.set('error');
      }
    }
  }

  onMount(() => {
    initializeConnection();
  });
</script>

<div class="min-h-screen bg-base-200 flex flex-col">
  <Navbar />
  <main class="flex-1">
    {@render children()}
  </main>
</div>
