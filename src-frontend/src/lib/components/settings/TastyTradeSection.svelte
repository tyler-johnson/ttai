<script lang="ts">
  import { invoke } from '@tauri-apps/api/core';
  import { open } from '@tauri-apps/plugin-shell';
  import { authStatus, isLoggingIn, loginError } from '$lib/stores/auth';
  import type { LoginResult, AuthStatusData, LogoutResult } from '$lib/mcp/types';

  let clientSecret = $state('');
  let refreshToken = $state('');
  let rememberMe = $state(true);
  let isLoggingOut = $state(false);

  function openApiAccess(event: Event) {
    event.preventDefault();
    open('https://my.tastytrade.com/app.html#/manage/api-access');
  }

  async function handleSubmit(event: Event) {
    event.preventDefault();

    if (!clientSecret || !refreshToken) {
      loginError.set('Please enter client secret and refresh token');
      return;
    }

    isLoggingIn.set(true);
    loginError.set(null);

    try {
      const result = await invoke<LoginResult>('mcp_login', {
        clientSecret,
        refreshToken,
        rememberMe
      });

      if (result.success) {
        // Refresh auth status
        const status = await invoke<AuthStatusData>('mcp_get_auth_status');
        authStatus.set(status);
        clientSecret = '';
        refreshToken = '';
      } else {
        loginError.set(result.error || result.message || 'Login failed');
      }
    } catch (error) {
      loginError.set(String(error));
    } finally {
      isLoggingIn.set(false);
    }
  }

  async function handleLogout(clearCredentials: boolean = false) {
    isLoggingOut = true;

    try {
      await invoke<LogoutResult>('mcp_logout', {
        clearCredentials
      });
      // Refresh auth status
      const status = await invoke<AuthStatusData>('mcp_get_auth_status');
      authStatus.set(status);
    } catch (error) {
      console.error('Logout error:', error);
    } finally {
      isLoggingOut = false;
    }
  }
</script>

<div class="space-y-4">
  <!-- Status Header -->
  <div class="flex items-center justify-between">
    <div>
      <h3 class="font-medium">TastyTrade Account</h3>
      <p class="text-sm text-base-content/70">
        {#if $authStatus?.authenticated}
          Connected via OAuth
        {:else if $authStatus?.has_stored_credentials}
          Credentials stored, not connected
        {:else}
          Not configured
        {/if}
      </p>
    </div>
    <div>
      {#if $authStatus?.authenticated}
        <span class="badge badge-success gap-1">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
          </svg>
          Connected
        </span>
      {:else}
        <span class="badge badge-neutral">Not Connected</span>
      {/if}
    </div>
  </div>

  <div class="divider my-2"></div>

  {#if $authStatus?.authenticated}
    <!-- Authenticated State -->
    <div class="space-y-3">
      <p class="text-sm text-base-content/70">
        Your TastyTrade account is connected and ready for use with MCP tools.
      </p>
      <div class="flex gap-2">
        <button
          class="btn btn-outline btn-sm"
          onclick={() => handleLogout(false)}
          disabled={isLoggingOut}
        >
          {#if isLoggingOut}
            <span class="loading loading-spinner loading-xs"></span>
          {/if}
          Disconnect
        </button>
        <button
          class="btn btn-outline btn-error btn-sm"
          onclick={() => handleLogout(true)}
          disabled={isLoggingOut}
        >
          Remove Credentials
        </button>
      </div>
    </div>
  {:else}
    <!-- Login Form -->
    <div>
      <p class="text-sm text-base-content/70 mb-3">
        Get your credentials from
        <button type="button" onclick={openApiAccess} class="link link-primary">
          TastyTrade API Access
        </button>
      </p>

      <form onsubmit={handleSubmit} class="space-y-3">
        <div class="form-control">
          <label class="label py-1" for="clientSecret">
            <span class="label-text">Client Secret</span>
          </label>
          <input
            type="password"
            id="clientSecret"
            bind:value={clientSecret}
            class="input input-bordered input-sm"
            placeholder="Enter your client secret"
            disabled={$isLoggingIn}
          />
        </div>

        <div class="form-control">
          <label class="label py-1" for="refreshToken">
            <span class="label-text">Refresh Token</span>
          </label>
          <input
            type="password"
            id="refreshToken"
            bind:value={refreshToken}
            class="input input-bordered input-sm"
            placeholder="Enter your refresh token"
            disabled={$isLoggingIn}
          />
        </div>

        <div class="form-control">
          <label class="label cursor-pointer justify-start gap-3 py-1">
            <input
              type="checkbox"
              bind:checked={rememberMe}
              class="checkbox checkbox-primary checkbox-sm"
              disabled={$isLoggingIn}
            />
            <span class="label-text">Remember credentials</span>
          </label>
        </div>

        {#if $loginError}
          <div class="alert alert-error py-2">
            <span class="text-sm">{$loginError}</span>
          </div>
        {/if}

        <div class="flex justify-end">
          <button
            type="submit"
            class="btn btn-primary btn-sm"
            disabled={$isLoggingIn}
          >
            {#if $isLoggingIn}
              <span class="loading loading-spinner loading-xs"></span>
              Connecting...
            {:else}
              Connect
            {/if}
          </button>
        </div>
      </form>
    </div>
  {/if}
</div>
