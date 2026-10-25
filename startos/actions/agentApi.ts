import { sdk } from '../sdk'
import { agentApi, newToken } from '../fileModels/agent-api.json'
import * as fs from 'node:fs/promises'

const metadata = (name: string, warning: string | null = null) => ({
  name,
  description: name,
  warning,
  allowedStatuses: 'any' as const,
  group: null,
  visibility: 'enabled' as const,
})
const endpointSpec = sdk.InputSpec.of({
  hosts: sdk.Value.text({
    name: 'Allowed Host headers',
    description:
      'Comma-separated exact host:port values observed through your private StartOS interface. No wildcards.',
    required: true,
    default: 'localhost:3001',
  }),
  origins: sdk.Value.text({
    name: 'Allowed browser origins',
    description:
      'Comma-separated exact http(s) origins. Use an empty string to reject all browser Origin headers.',
    required: false,
    default: '',
  }),
})
export const enableAgentApi = sdk.Action.withInput(
  'enable-agent-api',
  metadata(
    'Enable Agent Memory API',
    'Enables a private API, an internal full-space bearer credential, and restarts this package. MCP mutations remain disabled in this release.',
  ),
  endpointSpec,
  async () => ({}),
  async ({ effects, input }) => {
    const hosts = input.hosts.split(',').map((s) => s.trim())
    const origins = (input.origins || '')
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
    if (
      !hosts.length ||
      hosts.length > 16 ||
      origins.length > 16 ||
      hosts.some((h) => !/^[a-zA-Z0-9.-]+(?::[0-9]{1,5})?$/.test(h))
    )
      throw new Error(
        'Supply exact host headers without wildcards, schemes or paths.',
      )
    for (const origin of origins) {
      const u = new URL(origin)
      if (
        !['http:', 'https:'].includes(u.protocol) ||
        u.origin !== origin ||
        u.username ||
        u.password
      )
        throw new Error('Supply exact http(s) origins only.')
    }
    await agentApi.update((s) => ({
      ...s,
      enabled: true,
      allowedHosts: hosts,
      allowedOrigins: origins,
    }))
    await sdk.restart(effects)
  },
)
export const disableAgentApi = sdk.Action.withoutInput(
  'disable-agent-api',
  metadata(
    'Disable Agent Memory API',
    'Restarts this package and removes the MCP interface and all bearer authentication.',
  ),
  async ({ effects }) => {
    await agentApi.update((s) => ({ ...s, enabled: false }))
    await sdk.restart(effects)
  },
)
export const getMcpCredentials = sdk.Action.withoutInput(
  'get-mcp-credentials',
  metadata('Get MCP Credentials'),
  async ({ effects }) => {
    const state = await agentApi.read()
    const iface = await sdk.serviceInterface.getOwn(effects, 'mcp').once()
    const urls = iface?.addressInfo?.nonLocal.format() ?? []
    return {
      version: '1' as const,
      title: 'Agent Memory API',
      message:
        'Use the masked MCP interface URL from the StartOS Interfaces tab, path /mcp. Send tokens only in Authorization headers. Read/write token currently permits previews only; mutations are disabled.',
      result: {
        type: 'group' as const,
        value: [
          ...urls.map((url) => ({
            type: 'single' as const,
            name: 'MCP URL',
            description: null,
            value: url,
            masked: false,
            copyable: true,
            qr: false,
          })),
          {
            type: 'single' as const,
            name: 'Read token',
            description: null,
            value: state.mcpReadToken,
            masked: true,
            copyable: true,
            qr: false,
          },
          {
            type: 'single' as const,
            name: 'Read/write token',
            description: null,
            value: state.mcpWriteToken,
            masked: true,
            copyable: true,
            qr: false,
          },
        ],
      },
    }
  },
)
export const rotateMcpTokens = sdk.Action.withoutInput(
  'rotate-mcp-tokens',
  metadata(
    'Rotate MCP Tokens',
    'Revokes existing MCP clients and restarts this package. Login and internal token are unchanged.',
  ),
  async ({ effects }) => {
    await agentApi.update((s) => ({
      ...s,
      mcpReadToken: newToken(),
      mcpWriteToken: newToken(),
      rotatedAt: new Date().toISOString(),
    }))
    await sdk.restart(effects)
  },
)
export const rotateInternalToken = sdk.Action.withoutInput(
  'rotate-internal-token',
  metadata(
    'Rotate Internal API Token',
    'Restarts this package; MCP tokens and login are unchanged.',
  ),
  async ({ effects }) => {
    await agentApi.update((s) => ({
      ...s,
      silverbulletApiToken: newToken(),
      rotatedAt: new Date().toISOString(),
    }))
    await sdk.restart(effects)
  },
)
export const rebuildMemoryIndex = sdk.Action.withoutInput(
  'rebuild-memory-index',
  metadata(
    'Rebuild Memory Index',
    'Requests a derived index rebuild. Notes and credentials are unchanged.',
  ),
  async () => {
    // Publish atomically so the poller can rename/claim a complete request.
    // Never delete the database while the daemon has it open.
    const marker = sdk.volumes.index.subpath('rebuild-request')
    const temporary = `${marker}.${newToken()}.tmp`
    try {
      const file = await fs.open(temporary, 'wx', 0o644)
      try {
        await file.writeFile(new Date().toISOString())
        await file.sync()
      } finally {
        await file.close()
      }
      await fs.rename(temporary, marker)
      const directory = await fs.open(sdk.volumes.index.subpath(''), 'r')
      try {
        await directory.sync()
      } finally {
        await directory.close()
      }
    } finally {
      await fs.rm(temporary, { force: true })
    }
  },
)
