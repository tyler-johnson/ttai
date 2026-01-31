# TTAI Web UI

SvelteKit-based web interface for the TTAI application. This UI is embedded into the Go binary and served by the MCP server.

## Tech Stack

- **SvelteKit 2** - Application framework
- **Svelte 5** - UI components with runes
- **Tailwind CSS 4** - Styling
- **DaisyUI 5** - Component library
- **TypeScript** - Type safety

## Development

```bash
# Install dependencies
npm install

# Start dev server (hot reload)
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

The dev server runs at `http://localhost:5173` by default.

## Building for Go

The Go build process automatically builds and embeds the web UI:

```bash
cd ../src-go
make build  # Builds web UI first, then embeds it
```

The built files are copied to `src-go/internal/webui/dist/` and embedded using Go's `embed` package.

## Project Structure

```
src-web/
├── src/
│   ├── app.css          # Global styles (Tailwind imports)
│   ├── app.html         # HTML template
│   ├── lib/             # Shared components and utilities
│   └── routes/
│       ├── +layout.svelte   # Root layout
│       └── +page.svelte     # Main page
├── static/              # Static assets (favicon, etc.)
├── svelte.config.js     # SvelteKit config (static adapter)
├── vite.config.ts       # Vite config
└── package.json
```

## Static Adapter

The app uses `@sveltejs/adapter-static` to generate a fully static site that can be embedded in the Go binary. No server-side rendering is used.
