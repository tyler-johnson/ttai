<script lang="ts">
  import { connectionState } from '$lib/stores/connection';

  interface Props {
    onRetry?: () => void;
  }

  let { onRetry }: Props = $props();

  const serverUrl = 'http://localhost:8080';
</script>

<div class="space-y-4">
  <!-- Server Status -->
  <div class="flex items-center justify-between">
    <div>
      <h3 class="font-medium">MCP Server</h3>
      <p class="text-sm text-base-content/70">{serverUrl}</p>
    </div>
    <div class="flex items-center gap-2">
      {#if $connectionState === 'connecting'}
        <span class="loading loading-spinner loading-sm"></span>
        <span class="text-sm">Connecting...</span>
      {:else if $connectionState === 'connected'}
        <span class="badge badge-success gap-1">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
          </svg>
          Connected
        </span>
      {:else}
        <span class="badge badge-error gap-1">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
          Disconnected
        </span>
        {#if onRetry}
          <button class="btn btn-sm btn-outline" onclick={onRetry}>Retry</button>
        {/if}
      {/if}
    </div>
  </div>

  <div class="divider my-2"></div>

  <!-- Claude Integration -->
  <div>
    <h3 class="font-medium mb-2">Connect to Claude</h3>
    <p class="text-sm text-base-content/70 mb-3">
      Use TTAI tools directly in Claude by adding this server as a connector.
    </p>

    <div class="bg-base-200 rounded-lg p-4 space-y-3">
      <div>
        <p class="text-sm font-medium mb-1">Server URL</p>
        <code class="text-sm bg-base-300 px-2 py-1 rounded select-all">{serverUrl}/mcp</code>
      </div>

      <div class="text-sm text-base-content/70">
        <p class="mb-2">To connect:</p>
        <ol class="list-decimal list-inside space-y-1">
          <li>Open Claude Desktop or claude.ai</li>
          <li>Go to Settings → Connectors</li>
          <li>Click "Add Connector"</li>
          <li>Enter the server URL above</li>
        </ol>
      </div>
    </div>

    <div class="mt-3">
      <a
        href="https://support.anthropic.com/en/articles/11175166-how-do-i-connect-to-a-remote-mcp-server-using-claude-desktop"
        target="_blank"
        rel="noopener noreferrer"
        class="link link-primary text-sm"
      >
        Learn more about Claude connectors →
      </a>
    </div>
  </div>
</div>
