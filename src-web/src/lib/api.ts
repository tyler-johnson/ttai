// API client for TTAI backend

export interface ServerInfo {
	version: string;
	http_url: string;
	https_url?: string;
	ssl_enabled: boolean;
}

export interface Settings {
	launch_at_startup: boolean;
	open_settings_on_launch: boolean;
}

export interface TastyTradeStatus {
	authenticated: boolean;
	error?: string;
}

export async function getServerInfo(): Promise<ServerInfo> {
	const response = await fetch('/api/server-info');
	if (!response.ok) throw new Error('Failed to load server info');
	return response.json();
}

export async function getSettings(): Promise<Settings> {
	const response = await fetch('/api/settings');
	if (!response.ok) throw new Error('Failed to load settings');
	return response.json();
}

export async function updateSettings(updates: Partial<Settings>): Promise<Settings> {
	const response = await fetch('/api/settings', {
		method: 'PATCH',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(updates)
	});
	if (!response.ok) throw new Error('Failed to save settings');
	return response.json();
}

export async function getTastyTradeStatus(): Promise<TastyTradeStatus> {
	const response = await fetch('/api/tastytrade');
	if (!response.ok) throw new Error('Failed to load TastyTrade status');
	return response.json();
}

export async function loginTastyTrade(
	clientSecret: string,
	refreshToken: string
): Promise<TastyTradeStatus> {
	const response = await fetch('/api/tastytrade', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({
			client_secret: clientSecret,
			refresh_token: refreshToken
		})
	});
	return response.json();
}

export async function logoutTastyTrade(): Promise<TastyTradeStatus> {
	const response = await fetch('/api/tastytrade', { method: 'DELETE' });
	if (!response.ok) throw new Error('Failed to logout');
	return response.json();
}

export async function copyToClipboard(text: string): Promise<void> {
	await navigator.clipboard.writeText(text);
}
