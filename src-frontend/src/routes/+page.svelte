<script lang="ts">
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';

  onMount(() => {
    goto('/settings', { replaceState: true });
  });
</script>

<div class="flex items-center justify-center h-full p-6">
  <span class="loading loading-spinner loading-lg"></span>
</div>
