<script lang="ts">
	import { onMount } from 'svelte';
	import {
		getServerInfo,
		getSettings,
		updateSettings,
		getTastyTradeStatus,
		loginTastyTrade,
		logoutTastyTrade,
		copyToClipboard,
		getUpdateStatus,
		checkForUpdates,
		downloadUpdate,
		applyUpdate,
		type ServerInfo,
		type Settings,
		type UpdateStatus
	} from '$lib/api';

	// State
	let activeTab = $state<'connection' | 'settings' | 'about'>('connection');
	let serverInfo = $state<ServerInfo | null>(null);
	let settings = $state<Settings | null>(null);
	let isAuthenticated = $state(false);
	let showLoginModal = $state(false);
	let loginError = $state('');
	let clientSecret = $state('');
	let refreshToken = $state('');
	let copiedUrl = $state<string | null>(null);
	let updateStatus = $state<UpdateStatus | null>(null);
	let isUpdating = $state(false);

	onMount(async () => {
		try {
			const [info, prefs, status, update] = await Promise.all([
				getServerInfo(),
				getSettings(),
				getTastyTradeStatus(),
				getUpdateStatus()
			]);
			serverInfo = info;
			settings = prefs;
			isAuthenticated = status.authenticated;
			updateStatus = update;
		} catch (error) {
			console.error('Failed to load initial data:', error);
		}

		// Poll update status every 5 seconds when checking/downloading
		const pollInterval = setInterval(async () => {
			if (updateStatus?.status === 'checking' || updateStatus?.status === 'downloading') {
				try {
					updateStatus = await getUpdateStatus();
				} catch (error) {
					console.error('Failed to poll update status:', error);
				}
			}
		}, 5000);

		return () => clearInterval(pollInterval);
	});

	async function handleCopy(url: string) {
		try {
			await copyToClipboard(url);
			copiedUrl = url;
			setTimeout(() => (copiedUrl = null), 1500);
		} catch (error) {
			console.error('Failed to copy:', error);
		}
	}

	async function handleSettingChange(key: keyof Settings, value: boolean) {
		try {
			settings = await updateSettings({ [key]: value });
		} catch (error) {
			console.error('Failed to save settings:', error);
		}
	}

	function openLoginModal() {
		clientSecret = '';
		refreshToken = '';
		loginError = '';
		showLoginModal = true;
	}

	function closeLoginModal() {
		showLoginModal = false;
	}

	async function handleLogin() {
		if (!clientSecret.trim() || !refreshToken.trim()) {
			loginError = 'Please enter both client secret and refresh token';
			return;
		}

		try {
			const result = await loginTastyTrade(clientSecret.trim(), refreshToken.trim());
			if (result.authenticated) {
				isAuthenticated = true;
				closeLoginModal();
			} else {
				loginError = result.error || 'Login failed';
			}
		} catch (error) {
			loginError = 'Connection error';
		}
	}

	async function handleLogout() {
		try {
			await logoutTastyTrade();
			isAuthenticated = false;
		} catch (error) {
			console.error('Failed to disconnect:', error);
		}
	}

	async function handleCheckForUpdates() {
		try {
			await checkForUpdates();
			updateStatus = await getUpdateStatus();
		} catch (error) {
			console.error('Failed to check for updates:', error);
		}
	}

	async function handleDownloadUpdate() {
		try {
			isUpdating = true;
			await downloadUpdate();
			// Poll until download completes
			const poll = async () => {
				updateStatus = await getUpdateStatus();
				if (updateStatus?.status === 'downloading') {
					setTimeout(poll, 1000);
				} else {
					isUpdating = false;
				}
			};
			poll();
		} catch (error) {
			console.error('Failed to download update:', error);
			isUpdating = false;
		}
	}

	async function handleApplyUpdate() {
		try {
			isUpdating = true;
			await applyUpdate();
			// App will restart, so we won't get here normally
		} catch (error) {
			console.error('Failed to apply update:', error);
			isUpdating = false;
		}
	}

	function handleKeydown(event: KeyboardEvent) {
		if (event.key === 'Escape' && showLoginModal) {
			closeLoginModal();
		}
		if (event.key === 'Enter' && showLoginModal) {
			handleLogin();
		}
	}
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="container mx-auto max-w-xl p-5">
	<!-- Update Banner -->
	{#if updateStatus?.status === 'available' || updateStatus?.status === 'ready'}
		<div class="alert alert-info mb-4">
			<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" class="stroke-current shrink-0 w-6 h-6">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
			</svg>
			<div class="flex-1">
				<h3 class="font-bold">Update Available</h3>
				<p class="text-sm">Version {updateStatus.update_info?.version} is ready to install</p>
			</div>
			{#if updateStatus.status === 'available'}
				<button
					class="btn btn-sm btn-primary"
					onclick={handleDownloadUpdate}
					disabled={isUpdating}
				>
					{isUpdating ? 'Downloading...' : 'Download'}
				</button>
			{:else if updateStatus.status === 'ready'}
				<button
					class="btn btn-sm btn-primary"
					onclick={handleApplyUpdate}
					disabled={isUpdating}
				>
					{isUpdating ? 'Installing...' : 'Install & Restart'}
				</button>
			{/if}
		</div>
	{/if}

	<!-- Tabs -->
	<div role="tablist" class="tabs tabs-bordered mb-6">
		<button
			role="tab"
			class="tab"
			class:tab-active={activeTab === 'connection'}
			onclick={() => (activeTab = 'connection')}
		>
			Connection
		</button>
		<button
			role="tab"
			class="tab"
			class:tab-active={activeTab === 'settings'}
			onclick={() => (activeTab = 'settings')}
		>
			Settings
		</button>
		<button
			role="tab"
			class="tab"
			class:tab-active={activeTab === 'about'}
			onclick={() => (activeTab = 'about')}
		>
			About
		</button>
	</div>

	<!-- Connection Tab -->
	{#if activeTab === 'connection'}
		<div class="card bg-base-200 mb-4">
			<div class="card-body">
				<h2 class="card-title text-sm font-semibold text-neutral-content uppercase tracking-wide">
					MCP Server
				</h2>
				{#if serverInfo}
					<div class="space-y-3">
						{#if serverInfo.https_url}
							<div class="flex items-center gap-3">
								<code class="flex-1 bg-base-300 px-3 py-2 rounded text-sm font-mono truncate">
									{serverInfo.https_url}
								</code>
								<button
									class="btn btn-sm"
									class:btn-success={copiedUrl === serverInfo.https_url}
									onclick={() => handleCopy(serverInfo!.https_url!)}
								>
									{copiedUrl === serverInfo.https_url ? 'Copied!' : 'Copy'}
								</button>
							</div>
						{/if}
						<div class="flex items-center gap-3">
							<code class="flex-1 bg-base-300 px-3 py-2 rounded text-sm font-mono truncate">
								{serverInfo.http_url}
							</code>
							<button
								class="btn btn-sm"
								class:btn-success={copiedUrl === serverInfo.http_url}
								onclick={() => handleCopy(serverInfo!.http_url)}
							>
								{copiedUrl === serverInfo.http_url ? 'Copied!' : 'Copy'}
							</button>
						</div>
					</div>
					<p class="text-sm text-neutral-content mt-2">
						Add this URL to your MCP client configuration
					</p>
				{/if}
			</div>
		</div>

		<div class="card bg-base-200">
			<div class="card-body">
				<h2 class="card-title text-sm font-semibold text-neutral-content uppercase tracking-wide">
					TastyTrade
				</h2>
				<div class="flex items-center gap-3">
					<div class="w-3 h-3 rounded-full" class:bg-success={isAuthenticated} class:bg-error={!isAuthenticated}></div>
					<span class="flex-1">{isAuthenticated ? 'Connected' : 'Not Connected'}</span>
					{#if isAuthenticated}
						<button class="btn btn-secondary btn-sm" onclick={handleLogout}>Disconnect</button>
					{:else}
						<button class="btn btn-primary btn-sm" onclick={openLoginModal}>Connect...</button>
					{/if}
				</div>
			</div>
		</div>
	{/if}

	<!-- Settings Tab -->
	{#if activeTab === 'settings'}
		<div class="card bg-base-200 mb-4">
			<div class="card-body">
				<h2 class="card-title text-sm font-semibold text-neutral-content uppercase tracking-wide">
					Startup
				</h2>
				{#if settings}
					<div class="form-control">
						<label class="label cursor-pointer justify-start gap-3">
							<input
								type="checkbox"
								class="checkbox checkbox-primary"
								checked={settings.launch_at_startup}
								onchange={(e) => handleSettingChange('launch_at_startup', e.currentTarget.checked)}
							/>
							<span class="label-text">Launch TTAI when you log in</span>
						</label>
					</div>
					<div class="divider my-2"></div>
					<div class="form-control">
						<label class="label cursor-pointer justify-start gap-3">
							<input
								type="checkbox"
								class="checkbox checkbox-primary"
								checked={settings.open_settings_on_launch}
								onchange={(e) => handleSettingChange('open_settings_on_launch', e.currentTarget.checked)}
							/>
							<span class="label-text">Open settings in browser on launch</span>
						</label>
					</div>
				{/if}
			</div>
		</div>

		<div class="card bg-base-200">
			<div class="card-body">
				<h2 class="card-title text-sm font-semibold text-neutral-content uppercase tracking-wide">
					Updates
				</h2>
				{#if settings}
					<div class="form-control">
						<label class="label cursor-pointer justify-start gap-3">
							<input
								type="checkbox"
								class="checkbox checkbox-primary"
								checked={settings.auto_update_enabled}
								onchange={(e) => handleSettingChange('auto_update_enabled', e.currentTarget.checked)}
							/>
							<span class="label-text">Check for updates automatically</span>
						</label>
					</div>
					<div class="divider my-2"></div>
					<div class="flex items-center justify-between">
						<span class="text-sm text-neutral-content">Current version: {updateStatus?.current_version ?? serverInfo?.version ?? '1.0.0'}</span>
						<button
							class="btn btn-sm btn-ghost"
							onclick={handleCheckForUpdates}
							disabled={updateStatus?.status === 'checking'}
						>
							{updateStatus?.status === 'checking' ? 'Checking...' : 'Check Now'}
						</button>
					</div>
				{/if}
			</div>
		</div>
	{/if}

	<!-- About Tab -->
	{#if activeTab === 'about'}
		<div class="card bg-base-200">
			<div class="card-body text-center">
				<img src="/favicon.png" alt="TTAI Logo" class="mx-auto w-24 h-24 rounded-2xl mb-4" />
				<h1 class="text-3xl font-bold">TTAI</h1>
				<p class="text-neutral-content">TastyTrade AI Assistant</p>
				<p class="text-sm text-neutral-content mb-4">
					Version {serverInfo?.version ?? '1.0.0'}
				</p>
				<div class="divider my-2"></div>
				<p class="text-sm text-neutral-content leading-relaxed">
					AI-powered trading analysis using the TastyTrade API.<br />
					Connect via MCP for intelligent insights.
				</p>
			</div>
		</div>
	{/if}
</div>

<!-- Login Modal -->
{#if showLoginModal}
	<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
	<div
		class="modal modal-open"
		onclick={(e) => e.target === e.currentTarget && closeLoginModal()}
	>
		<div class="modal-box bg-base-200">
			<h3 class="text-lg font-semibold mb-1">Connect to TastyTrade</h3>
			<p class="text-sm text-neutral-content mb-5">Enter your TastyTrade API credentials</p>

			<div class="form-control mb-4">
				<label class="label" for="client-secret">
					<span class="label-text text-neutral-content text-sm">Client Secret</span>
				</label>
				<input
					id="client-secret"
					type="password"
					class="input input-bordered w-full"
					placeholder="Enter client secret"
					bind:value={clientSecret}
				/>
			</div>

			<div class="form-control mb-4">
				<label class="label" for="refresh-token">
					<span class="label-text text-neutral-content text-sm">Refresh Token</span>
				</label>
				<input
					id="refresh-token"
					type="password"
					class="input input-bordered w-full"
					placeholder="Enter refresh token"
					bind:value={refreshToken}
				/>
			</div>

			{#if loginError}
				<p class="text-error text-sm mb-4">{loginError}</p>
			{/if}

			<a
				href="https://my.tastytrade.com/app.html#/manage/api-access"
				target="_blank"
				class="link link-primary text-sm"
			>
				Get Credentials...
			</a>

			<div class="modal-action">
				<button class="btn btn-secondary" onclick={closeLoginModal}>Cancel</button>
				<button class="btn btn-primary" onclick={handleLogin}>Connect</button>
			</div>
		</div>
	</div>
{/if}
