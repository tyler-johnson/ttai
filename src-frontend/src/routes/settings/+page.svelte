<script lang="ts">
  import ConnectionSection from '$lib/components/settings/ConnectionSection.svelte';
  import TastyTradeSection from '$lib/components/settings/TastyTradeSection.svelte';
  import { connectionState } from '$lib/stores/connection';
  import { invoke } from '@tauri-apps/api/core';
  import { authStatus, type AuthStatusData } from '$lib/stores/auth';

  async function handleRetry() {
    connectionState.set('connecting');

    try {
      await invoke('reconnect_server');
      connectionState.set('connected');

      const status = await invoke<AuthStatusData>('mcp_get_auth_status');
      authStatus.set(status);
    } catch (error) {
      console.error('Connection error:', error);
      connectionState.set('error');
    }
  }
</script>

<div class="container mx-auto max-w-2xl p-6">
  <h1 class="text-2xl font-bold mb-6">Settings</h1>

  <div class="space-y-4">
    <!-- Connection Section -->
    <div class="collapse collapse-arrow bg-base-100 border border-base-300">
      <input type="radio" name="settings-accordion" checked />
      <div class="collapse-title font-medium">
        <div class="flex items-center gap-2">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h.01M12 12h.01M19 12h.01M6 12a1 1 0 11-2 0 1 1 0 012 0zm7 0a1 1 0 11-2 0 1 1 0 012 0zm7 0a1 1 0 11-2 0 1 1 0 012 0z" />
          </svg>
          Connection
        </div>
      </div>
      <div class="collapse-content">
        <ConnectionSection onRetry={handleRetry} />
      </div>
    </div>

    <!-- TastyTrade Section -->
    <div class="collapse collapse-arrow bg-base-100 border border-base-300">
      <input type="radio" name="settings-accordion" />
      <div class="collapse-title font-medium">
        <div class="flex items-center gap-2">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
          </svg>
          TastyTrade Account
        </div>
      </div>
      <div class="collapse-content">
        {#if $connectionState === 'connected'}
          <TastyTradeSection />
        {:else}
          <p class="text-sm text-base-content/70">
            Connect to the MCP server first to configure TastyTrade credentials.
          </p>
        {/if}
      </div>
    </div>
  </div>
</div>
