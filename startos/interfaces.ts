import { i18n } from './i18n'
import { sdk } from './sdk'
import { uiPort } from './utils'
import { agentApi } from './fileModels/agent-api.json'

export const setInterfaces = sdk.setupInterfaces(async ({ effects }) => {
  const uiMulti = sdk.MultiHost.of(effects, 'ui-multi')
  const uiMultiOrigin = await uiMulti.bindPort(uiPort, {
    protocol: 'http',
  })
  const ui = sdk.createInterface(effects, {
    name: i18n('Web UI'),
    id: 'ui',
    description: i18n('The SilverBullet web interface'),
    type: 'ui',
    masked: false,
    schemeOverride: null,
    username: null,
    path: '',
    query: {},
  })

  const uiReceipt = await uiMultiOrigin.export([ui])

  const enabled = await agentApi.enabled().const(effects)
  if (!enabled) return [uiReceipt]
  const mcpHost = sdk.MultiHost.of(effects, 'mcp-multi')
  const mcpOrigin = await mcpHost.bindPort(3001, { protocol: 'http' })
  const mcp = sdk.createInterface(effects, {
    name: 'Agent Memory MCP',
    id: 'mcp',
    description: 'Authenticated Streamable HTTP memory API',
    type: 'api',
    masked: true,
    schemeOverride: null,
    username: null,
    path: '/mcp',
    query: {},
  })
  return [uiReceipt, await mcpOrigin.export([mcp])]
})
