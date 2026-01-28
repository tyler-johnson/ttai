<script lang="ts">
  import { connectionState } from '$lib/stores/connection';
  import { authStatus } from '$lib/stores/auth';
</script>

<div class="navbar bg-base-100 border-b border-base-300 px-4">
  <div class="flex-1">
    <a href="/" class="text-xl font-bold">TTAI</a>
  </div>

  <div class="flex-none flex items-center gap-3">
    <!-- Status Indicators -->
    <div class="flex items-center gap-2 text-sm">
      <!-- Server Status -->
      {#if $connectionState === 'connected'}
        <div class="tooltip tooltip-bottom" data-tip="MCP Server Connected">
          <span class="badge badge-success badge-sm gap-1">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-2.5 w-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h.01M12 12h.01M19 12h.01M6 12a1 1 0 11-2 0 1 1 0 012 0zm7 0a1 1 0 11-2 0 1 1 0 012 0zm7 0a1 1 0 11-2 0 1 1 0 012 0z" />
            </svg>
            Server
          </span>
        </div>
      {:else if $connectionState === 'connecting'}
        <div class="tooltip tooltip-bottom" data-tip="Connecting to server...">
          <span class="badge badge-warning badge-sm gap-1">
            <span class="loading loading-spinner loading-xs"></span>
            Server
          </span>
        </div>
      {:else}
        <div class="tooltip tooltip-bottom" data-tip="Server Disconnected">
          <span class="badge badge-error badge-sm gap-1">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-2.5 w-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
            Server
          </span>
        </div>
      {/if}

      <!-- TastyTrade Auth Status -->
      {#if $authStatus?.authenticated}
        <div class="tooltip tooltip-bottom" data-tip="TastyTrade Connected">
          <span class="badge badge-success badge-sm gap-1">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-2.5 w-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
            </svg>
            TastyTrade
          </span>
        </div>
      {:else}
        <div class="tooltip tooltip-bottom" data-tip="TastyTrade Not Connected">
          <span class="badge badge-neutral badge-sm">TastyTrade</span>
        </div>
      {/if}
    </div>

    <!-- Settings Link -->
    <a href="/settings" class="btn btn-ghost btn-sm btn-square" aria-label="Settings">
      <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    </a>
  </div>
</div>
