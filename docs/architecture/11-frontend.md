# Frontend Architecture

## Overview

The TTAI desktop application has a minimal frontend focused on a single purpose: **Settings**. The UI provides configuration and credential management, while trading analysis happens via MCP tools in external clients like Claude Desktop.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         TTAI Frontend Architecture                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Desktop App UI                           Trading Analysis                   │
│  ┌────────────────────────────────┐      ┌────────────────────────────────┐ │
│  │         Settings Page          │      │      Claude Desktop            │ │
│  │  ┌──────────────────────────┐  │      │      (or other MCP client)     │ │
│  │  │  TastyTrade Credentials  │  │      │                                │ │
│  │  │  API Configuration       │  │      │  - Get quotes                  │ │
│  │  │  Notification Prefs      │  │      │  - Analyze charts              │ │
│  │  │  Connection Testing      │  │      │  - Run strategies              │ │
│  │  └──────────────────────────┘  │      │  - View positions              │ │
│  └────────────────────────────────┘      └────────────────────────────────┘ │
│              │                                         │                     │
│              │ Tauri IPC                               │ HTTP/SSE            │
│              └─────────────────────┬───────────────────┘                     │
│                                    │                                         │
│                                    ▼                                         │
│                    ┌──────────────────────────────┐                          │
│                    │      Python MCP Server       │                          │
│                    │   (Tools, Resources, etc.)   │                          │
│                    └──────────────────────────────┘                          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Design Principles

1. **Minimal UI**: The app is a Settings interface, not a trading dashboard
2. **Configuration Focus**: Manage credentials, preferences, and test connections
3. **Analysis via MCP**: Trading analysis happens through MCP tools in Claude Desktop or other clients
4. **Modern CSS**: Tailwind CSS v4 with CSS-based configuration (no JS config file)
5. **Component Library**: DaisyUI for pre-built, accessible components

## Technology Stack

| Technology | Version | Purpose |
|------------|---------|---------|
| Svelte | 5.x | UI framework |
| SvelteKit | 2.x | Routing and SSR (static adapter) |
| Tailwind CSS | 4.x | Utility-first CSS with CSS-based config |
| DaisyUI | 5.x | Component library built on Tailwind |
| TypeScript | 5.x | Type safety |
| Vite | 6.x | Build tooling |

## Project Structure

```
src/
├── app.html                      # HTML template
├── app.css                       # Tailwind directives + DaisyUI
├── lib/
│   ├── components/               # Shared UI components
│   │   └── settings/             # Settings-specific components
│   │       ├── CredentialsForm.svelte
│   │       ├── ConnectionStatus.svelte
│   │       └── PreferencesForm.svelte
│   ├── stores/                   # Svelte stores
│   │   ├── config.ts             # Configuration state
│   │   └── connection.ts         # Connection status state
│   └── api.ts                    # MCP client wrapper
└── routes/
    ├── +layout.svelte            # App layout with DaisyUI theme
    ├── +page.svelte              # Redirects to /settings
    └── settings/
        └── +page.svelte          # Settings page
```

## Tailwind CSS Configuration

TTAI uses Tailwind CSS v4 with CSS-based configuration. Instead of a JavaScript config file, themes and customizations are defined directly in CSS using `@theme` directives.

### CSS Setup

```css
/* src/app.css */
@import "tailwindcss";
@plugin "daisyui";

@theme {
  /* Brand colors */
  --color-primary: #570df8;
  --color-secondary: #f000b8;
  --color-accent: #37cdbe;
  --color-neutral: #3d4451;
  --color-base-100: #ffffff;

  /* Extend with custom values as needed */
  --font-family-display: "Inter", sans-serif;
}
```

### Why CSS-Based Config?

- **No build-time JS**: Configuration is pure CSS, loaded at runtime
- **CSS Variables**: Easy to override and inspect in browser devtools
- **Standard CSS**: Works with any tooling that understands CSS
- **Simpler setup**: No `tailwind.config.js` file to maintain

## DaisyUI Integration

DaisyUI provides pre-built components that work with Tailwind's utility classes.

### Theme Setup

```svelte
<!-- src/routes/+layout.svelte -->
<script>
  import '../app.css';
</script>

<div data-theme="light" class="min-h-screen bg-base-100">
  <slot />
</div>
```

### Using Components

DaisyUI components are applied via CSS classes:

```svelte
<!-- Example: Settings form with DaisyUI components -->
<div class="card bg-base-200 shadow-xl">
  <div class="card-body">
    <h2 class="card-title">TastyTrade Credentials</h2>

    <div class="form-control">
      <label class="label">
        <span class="label-text">Username</span>
      </label>
      <input
        type="text"
        bind:value={username}
        class="input input-bordered"
        placeholder="Enter username"
      />
    </div>

    <div class="form-control">
      <label class="label">
        <span class="label-text">Password</span>
      </label>
      <input
        type="password"
        bind:value={password}
        class="input input-bordered"
        placeholder="Enter password"
      />
    </div>

    <div class="card-actions justify-end mt-4">
      <button class="btn btn-primary" on:click={saveCredentials}>
        Save
      </button>
      <button class="btn btn-ghost" on:click={testConnection}>
        Test Connection
      </button>
    </div>
  </div>
</div>
```

### Available Themes

DaisyUI includes multiple themes. Switch themes by changing the `data-theme` attribute:

```svelte
<script>
  let theme = 'light';

  function toggleTheme() {
    theme = theme === 'light' ? 'dark' : 'light';
  }
</script>

<div data-theme={theme}>
  <button class="btn" on:click={toggleTheme}>
    Toggle Theme
  </button>
</div>
```

## Settings Page Structure

The Settings page is the primary (and only) view in the desktop app.

### Layout

```svelte
<!-- src/routes/settings/+page.svelte -->
<script lang="ts">
  import CredentialsForm from '$lib/components/settings/CredentialsForm.svelte';
  import ConnectionStatus from '$lib/components/settings/ConnectionStatus.svelte';
  import PreferencesForm from '$lib/components/settings/PreferencesForm.svelte';
</script>

<div class="container mx-auto p-6 max-w-2xl">
  <h1 class="text-2xl font-bold mb-6">Settings</h1>

  <div class="space-y-6">
    <!-- Connection Status -->
    <ConnectionStatus />

    <!-- TastyTrade Credentials -->
    <CredentialsForm />

    <!-- Preferences -->
    <PreferencesForm />
  </div>
</div>
```

### Root Redirect

The root page redirects to Settings:

```svelte
<!-- src/routes/+page.svelte -->
<script lang="ts">
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';

  onMount(() => {
    goto('/settings');
  });
</script>

<div class="flex items-center justify-center min-h-screen">
  <span class="loading loading-spinner loading-lg"></span>
</div>
```

## Component Organization

### Settings Components

Components specific to the Settings page:

```
src/lib/components/settings/
├── CredentialsForm.svelte    # TastyTrade login credentials
├── ConnectionStatus.svelte   # Server connection indicator
├── PreferencesForm.svelte    # User preferences (notifications, etc.)
└── ApiKeyInput.svelte        # Secure API key entry
```

### Shared Components

Reusable UI components (if needed):

```
src/lib/components/
├── Alert.svelte              # Status messages
├── LoadingSpinner.svelte     # Loading indicator
└── Modal.svelte              # Dialog component
```

## State Management

### Svelte Stores

Configuration state is managed with Svelte stores:

```typescript
// src/lib/stores/config.ts
import { writable } from 'svelte/store';

interface Config {
  tastytrade: {
    username: string;
    hasCredentials: boolean;
  };
  notifications: {
    enabled: boolean;
    sound: boolean;
  };
}

export const config = writable<Config>({
  tastytrade: {
    username: '',
    hasCredentials: false,
  },
  notifications: {
    enabled: true,
    sound: true,
  },
});

// Load config from MCP server on startup
export async function loadConfig() {
  const result = await mcpClient.getConfig();
  config.set(result);
}
```

### Connection Status

Track MCP server connection state:

```typescript
// src/lib/stores/connection.ts
import { writable } from 'svelte/store';

export type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'error';

export const connectionState = writable<ConnectionState>('disconnected');
export const connectionError = writable<string | null>(null);
```

## Frontend-to-MCP Communication

The Settings UI communicates with the Python MCP server via Tauri IPC. See [Integration Patterns](./09-integration-patterns.md) for the full implementation.

### API Wrapper

```typescript
// src/lib/api.ts
import { invoke } from '@tauri-apps/api/core';

export async function getConfig(): Promise<Config> {
  return invoke('mcp_call_tool', {
    name: 'get_config',
    arguments: {},
  });
}

export async function updateConfig(config: Partial<Config>): Promise<void> {
  return invoke('mcp_call_tool', {
    name: 'update_config',
    arguments: { config },
  });
}

export async function testConnection(): Promise<{ success: boolean; message: string }> {
  return invoke('mcp_call_tool', {
    name: 'test_connection',
    arguments: {},
  });
}

export async function setCredentials(username: string, password: string): Promise<void> {
  return invoke('mcp_call_tool', {
    name: 'set_credentials',
    arguments: { username, password },
  });
}
```

## Vite Configuration

```typescript
// vite.config.ts
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [sveltekit()],

  // Tauri expects a fixed port
  server: {
    port: 5173,
    strictPort: true,
  },

  // Optimize for Tauri
  build: {
    target: 'esnext',
  },
});
```

## SvelteKit Configuration

```javascript
// svelte.config.js
import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
  preprocess: vitePreprocess(),

  kit: {
    // Static adapter for Tauri
    adapter: adapter({
      pages: 'build',
      assets: 'build',
      fallback: 'index.html',
    }),
  },
};

export default config;
```

## Development Workflow

### Running the Frontend

```bash
# Frontend only (no Tauri)
pnpm dev

# Full desktop app with hot reload
pnpm tauri dev
```

### Building

```bash
# Build frontend for production
pnpm build

# Build full desktop app
pnpm tauri build
```

See [Local Development](./10-local-development.md) for the complete development setup guide.

## Cross-References

- [Build and Distribution](./08-build-distribution.md) - Project structure and build process
- [Integration Patterns](./09-integration-patterns.md) - Tauri IPC and MCP communication
- [Local Development](./10-local-development.md) - Development setup and workflow
