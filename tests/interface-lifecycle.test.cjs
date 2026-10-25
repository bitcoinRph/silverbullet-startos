const assert = require('node:assert/strict')
const { test } = require('node:test')
const fs = require('node:fs/promises')
const path = require('node:path')
const os = require('node:os')
const ts = require('typescript')
require.extensions['.ts'] = (module, filename) => module._compile(ts.transpileModule(require('node:fs').readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, filename)
const { sdk } = require('../startos/sdk.ts')
const { storeJson } = require('../startos/fileModels/store.json.ts')
const { agentApi } = require('../startos/fileModels/agent-api.json.ts')
const { actions } = require('../startos/actions/index.ts')
const { setInterfaces } = require('../startos/interfaces.ts')

test('real actions reactively export and revoke MCP; rotation preserves interface and returns fresh credentials', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'silverbullet-interface-'))
  const interfaces = new Map()
  const bindings = new Map()
  let runs = 0, restarts = 0, pending = Promise.resolve()
  let retryError
  const effects = {
    isInContext: true,
    onLeaveContext: () => {},
    bind: async value => { bindings.set(value.id, value); return null },
    exportServiceInterface: async value => { interfaces.set(value.id, value); return null },
    clearBindings: async ({ except }) => { for (const id of bindings.keys()) if (!except.some(v => v.id === id)) bindings.delete(id) },
    clearServiceInterfaces: async ({ except }) => { for (const id of interfaces.keys()) if (!except.includes(id)) interfaces.delete(id) },
    // Model only the OS context retry. File watching, const dependency and exports are the pinned SDK.
    constRetry: () => { pending = pending.then(() => { runs++; return setInterfaces(effects) }).catch(error => { retryError = error }) },
  }
  const originalRestart = sdk.restart
  const originalGetOwn = sdk.serviceInterface.getOwn
  sdk.restart = async () => { restarts++; return null } // restarting main must NOT rerun interfaces
  sdk.serviceInterface.getOwn = (_effects, id) => ({ once: async () => interfaces.has(id) ? { addressInfo: { nonLocal: { format: () => ['https://memory.example.test/mcp'] } } } : null })
  const run = async (id, input = {}) => {
    const action = actions.get(id)
    await action.getInput({ effects, prefill: null })
    return action.run({ effects, input })
  }
  const waitFor = async predicate => {
    for (let n = 0; n < 100; n++) {
      await new Promise(resolve => setTimeout(resolve, 10))
      await pending
      if (retryError) throw retryError
      if (predicate()) return
    }
    assert.ok(predicate(), 'interface did not react to the action state change')
  }
  try {
    storeJson.path = path.join(root, 'store.json')
    await fs.writeFile(storeJson.path, '{"password":"synthetic"}\n')
    await agentApi.ensure()
    await setInterfaces(effects) // lifecycle setup ONCE, never manually after an action
    assert.deepEqual([...interfaces.keys()], ['ui'])
    await run('enable-agent-api', { hosts: 'memory.example.test:443', origins: '' })
    assert.equal(restarts, 1)
    await waitFor(() => interfaces.has('mcp'))
    assert.equal(interfaces.get('mcp').type, 'api')
    assert.equal(interfaces.get('mcp').masked, true)
    assert.equal(interfaces.get('mcp').addressInfo.suffix, '/mcp')
    const credentials = await run('get-mcp-credentials')
    assert.ok(credentials.result.value.some(v => v.name === 'MCP URL'))
    const oldRead = credentials.result.value.find(v => v.name === 'Read token').value
    const before = await agentApi.read()
    const enabledRuns = runs
    await run('rotate-mcp-tokens')
    await new Promise(resolve => setTimeout(resolve, 50))
    await pending
    assert.ok(interfaces.has('mcp'))
    assert.equal(runs, enabledRuns, 'token-only rotation must not recreate interfaces')
    const rotated = await run('get-mcp-credentials')
    const freshRead = rotated.result.value.find(v => v.name === 'Read token')
    assert.notEqual(freshRead.value, oldRead)
    assert.equal(freshRead.masked, true)
    assert.equal((await agentApi.read()).silverbulletApiToken, before.silverbulletApiToken)
    await run('disable-agent-api')
    await waitFor(() => !interfaces.has('mcp'))
    assert.deepEqual([...interfaces.keys()], ['ui'])
    assert.deepEqual([...bindings.keys()], ['ui-multi'])
  } finally {
    effects.isInContext = false
    sdk.restart = originalRestart
    sdk.serviceInterface.getOwn = originalGetOwn
    await fs.rm(root, { recursive: true, force: true })
    await pending
  }
})
