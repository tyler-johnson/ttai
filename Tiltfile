# TTAI Local Development
# Run with: tilt up

# Combined workers - MCP server is primary, Python worker accessible via service binding
# Using multiple -c flags runs workers together so service bindings work natively
local_resource(
    'workers',
    serve_cmd='npx wrangler dev -c workers/mcp-server/wrangler.toml -c workers/python-worker/wrangler.toml --port 8787',
    deps=[
        '.dev.vars',
        'workers/mcp-server/src',
        'workers/mcp-server/wrangler.toml',
        'workers/python-worker/src',
        'workers/python-worker/wrangler.toml',
        'workers/python-worker/cf-requirements.txt',
    ],
    labels=['workers'],
    readiness_probe=probe(
        http_get=http_get_action(port=8787, path='/health'),
        initial_delay_secs=5,
        period_secs=30,
    ),
    links=[
        link('http://localhost:8787/health', 'Health'),
        link('http://localhost:8787/', 'MCP Endpoint'),
    ],
)

# MCP Inspector - web UI for testing MCP tools
local_resource(
    'mcp-inspector',
    serve_cmd='MCP_AUTO_OPEN_ENABLED=false DANGEROUSLY_OMIT_AUTH=true npx @modelcontextprotocol/inspector --transport http --server-url http://localhost:8787/',
    resource_deps=['workers'],
    labels=['tools'],
    readiness_probe=probe(
        http_get=http_get_action(port=6274, path='/'),
        initial_delay_secs=3,
        period_secs=30,
    ),
    links=[
        link('http://localhost:6274', 'MCP Inspector'),
    ],
)
