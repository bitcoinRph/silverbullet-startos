const assert = require('node:assert/strict')
const { test, after } = require('node:test')
const fs = require('node:fs/promises')
const path = require('node:path')
const os = require('node:os')
const ts = require('typescript')
require.extensions['.ts'] = (module, filename) => module._compile(ts.transpileModule(require('node:fs').readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, filename)
let root
const { sdk } = require('../startos/sdk.ts')
const { storeJson } = require('../startos/fileModels/store.json.ts')
const { main } = require('../startos/main.ts')
let daemons = [], tasks = [], mounts = []
sdk.SubContainer.of = async (...args) => { mounts.push(args[2].build()); return { execFail: async () => ({ stdout: '', stderr: '' }) } }
sdk.Daemons.of = () => ({ addDaemon(id, definition) { daemons.push({ id, ...definition }); return this } })
sdk.action.createOwnTask = async (...args) => { tasks.push(args) }
sdk.serviceInterface.getOwn = (effects, id) => ({ once: async () => { assert.equal(id, 'mcp'); return { addressInfo: { nonLocal: { format: () => ['https://memory.example.test/mcp'] } } } } })
const effects = { isInContext: true, clearBindings: async () => {}, clearServiceInterfaces: async () => {} }
async function fixture() {
  root ??= await fs.mkdtemp(path.join(os.tmpdir(), 'silverbullet-memory-test-'))
  storeJson.path = path.join(root, 'store.json')
  sdk.volumes.index.subpath = p => path.join(root, p)
  await fs.writeFile(storeJson.path, '{ "password": "synthetic-original" }\n')
  daemons = []; tasks = []; mounts = []
  return require('../startos/fileModels/agent-api.json.ts')
}
after(async () => { if (root) await fs.rm(root, { recursive: true, force: true }) })
test('generate-if-missing across update restore rebuild preserves password and tokens', async () => {
  const { agentApi } = await fixture()
  const { initializeService } = require('../startos/init/initializeService.ts')
  const before = await fs.readFile(storeJson.path)
  await initializeService.init(effects, 'update')
  const first = await agentApi.read()
  assert.equal(first.enabled, false)
  for (const k of ['silverbulletApiToken', 'mcpReadToken', 'mcpWriteToken']) assert.ok(first[k].length >= 32)
  assert.equal(new Set([first.silverbulletApiToken, first.mcpReadToken, first.mcpWriteToken]).size, 3)
  for (const kind of ['restore', null, 'update']) await initializeService.init(effects, kind)
  assert.deepEqual(await agentApi.read(), first)
  assert.deepEqual(await fs.readFile(storeJson.path), before)
  assert.equal((await fs.stat(agentApi.path)).mode & 0o777, 0o600)
})
test('disabled API omits bearer daemon and interface; runtime disabled unconditionally', async () => {
  const { agentApi } = await fixture()
  await agentApi.ensure()
  await agentApi.update(s => ({ ...s, enabled: false }))
  await main({ effects })
  assert.equal(daemons.length, 1)
  assert.equal(daemons[0].exec.env.SB_RUNTIME_API, '0')
  assert.equal(daemons[0].exec.env.SB_AUTH_TOKEN, undefined)
})
test('enabled API uses separate credentials, index-only mount, dependency and non-root', async () => {
  const { agentApi } = await fixture()
  await agentApi.ensure()
  await agentApi.update(s => ({ ...s, enabled: true }))
  await main({ effects })
  assert.equal(daemons.length, 2)
  const state = await agentApi.read()
  assert.equal(daemons[0].exec.env.SB_AUTH_TOKEN, state.silverbulletApiToken)
  assert.equal(daemons[0].exec.env.SB_RUNTIME_API, '0')
  assert.deepEqual(daemons[1].requires, ['primary'])
  assert.equal(daemons[1].exec.user, '10001:10001')
  assert.equal(mounts[1][0].options.volumeId, 'index')
  assert.equal(mounts[1].length, 1)
})
test('missing or corrupt API state never blocks SilverBullet, creates safe recovery task', async () => {
  const { agentApi } = await fixture()
  for (const raw of [undefined, '{"silverbulletApiToken":"do-not-leak"', '{}']) {
    await fs.rm(agentApi.path, { force: true })
    if (raw) await fs.writeFile(agentApi.path, raw)
    daemons = []; tasks = []
    await main({ effects })
    assert.equal(daemons.length, 1)
    assert.equal(daemons[0].exec.env.SB_AUTH_TOKEN, undefined)
    assert.equal(tasks.length, 1)
    assert.equal(tasks[0][2], 'critical')
    assert.ok(!JSON.stringify(tasks).includes('do-not-leak'))
  }
})
test('failed atomic write leaves existing state intact and removes temporary file', async () => {
  const { agentApi } = await fixture()
  await fs.rm(agentApi.path, { force: true })
  await agentApi.ensure()
  const before = await fs.readFile(agentApi.path)
  const originalRename = fs.rename
  fs.rename = async () => { throw new Error('synthetic I/O failure') }
  try { await assert.rejects(agentApi.update(s => ({ ...s, enabled: true }))) }
  finally { fs.rename = originalRename }
  assert.deepEqual(await fs.readFile(agentApi.path), before)
  assert.deepEqual((await fs.readdir(root)).sort(), ['agent-api.json', 'store.json'])
})
test('wrapper :2 downgrade through :1 to :0 is a no-op with credential files byte-preserved', async () => {
  const { agentApi } = await fixture()
  const versions = require('../startos/versions/current.ts')
  assert.equal(versions.current.options.version, '2.12.1:2')
  assert.equal(versions.v2_12_1_1.options.version, '2.12.1:1')
  assert.equal(versions.v2_12_1_0.options.version, '2.12.1:0')
  const before = await fs.readFile(storeJson.path)
  const apiBefore = await fs.readFile(agentApi.path)
  assert.equal(typeof versions.current.options.migrations.down, 'function')
  await versions.current.options.migrations.down({ effects })
  const { versionGraph } = require('../startos/versions/index.ts')
  const { ExtendedVersion } = require('@start9labs/start-sdk')
  const migrated = []
  await versionGraph.migrate({
    effects: { setDataVersion: async value => { migrated.push(value.version); return null } },
    from: ExtendedVersion.parse('2.12.1:2'), to: ExtendedVersion.parse('2.12.1:0'),
  })
  assert.equal(migrated.at(-1), '2.12.1:0')
  assert.deepEqual(await fs.readFile(storeJson.path), before)
  assert.deepEqual(await fs.readFile(agentApi.path), apiBefore)
})
test('actions enable disable rotate and rebuild preserve store and mask only external credentials', async () => {
  const { agentApi } = await fixture()
  const { actions } = require('../startos/actions/index.ts')
  await fs.rm(agentApi.path, { force: true })
  await agentApi.ensure()
  const before = await fs.readFile(storeJson.path)
  const original = await agentApi.read()
  let restarts = 0
  sdk.restart = async () => { restarts++; return null }
  const run = async (id, input = {}) => {
    const action = actions.get(id)
    await action.getInput({ effects, prefill: null })
    return action.run({ effects, input })
  }
  await run('enable-agent-api', { hosts: 'memory.example:443', origins: 'https://memory.example' })
  assert.equal((await agentApi.read()).enabled, true)
  const result = await run('get-mcp-credentials')
  const values = result.result.value
  assert.equal(values.find(v => v.name === 'MCP URL').value, 'https://memory.example.test/mcp')
  assert.equal(values.filter(v => v.masked).length, 2)
  assert.ok(!JSON.stringify(result).includes(original.silverbulletApiToken))
  await run('rotate-mcp-tokens')
  const rotated = await agentApi.read()
  assert.equal(rotated.silverbulletApiToken, original.silverbulletApiToken)
  assert.notEqual(rotated.mcpReadToken, original.mcpReadToken)
  assert.notEqual(rotated.mcpWriteToken, original.mcpWriteToken)
  await run('rotate-internal-token')
  assert.notEqual((await agentApi.read()).silverbulletApiToken, original.silverbulletApiToken)
  await run('disable-agent-api')
  assert.equal((await agentApi.read()).enabled, false)
  await run('rebuild-memory-index')
  assert.ok(restarts >= 4)
  assert.deepEqual(await fs.readFile(storeJson.path), before)
})
test('interface export is conditional and uses a masked API path', async () => {
  const { agentApi } = await fixture()
  await agentApi.ensure()
  const interfaces = []
  sdk.MultiHost.of = () => ({ bindPort: async () => ({ export: async v => v }) })
  sdk.createInterface = (_effects, definition) => { interfaces.push(definition); return definition }
  const { setInterfaces } = require('../startos/interfaces.ts')
  await agentApi.update(s => ({ ...s, enabled: false }))
  await setInterfaces(effects)
  assert.deepEqual(interfaces.map(i => i.id), ['ui'])
  interfaces.length = 0
  await agentApi.update(s => ({ ...s, enabled: true }))
  await setInterfaces(effects)
  assert.deepEqual(interfaces.map(i => i.id), ['ui', 'mcp'])
  assert.equal(interfaces[1].masked, true)
  assert.equal(interfaces[1].type, 'api')
  assert.equal(interfaces[1].path, '/mcp')
})

test('rebuild action publishes a complete marker atomically without truncating an in-flight request', async () => {
  await fixture()
  const { actions } = require('../startos/actions/index.ts')
  const marker = path.join(root, 'rebuild-request')
  await fs.writeFile(marker, 'existing request')
  const originalRename = fs.rename
  let published = false
  fs.rename = async (source, target) => {
    assert.equal(target, marker)
    assert.notEqual(source, marker)
    assert.equal(await fs.readFile(marker, 'utf8'), 'existing request')
    assert.ok((await fs.readFile(source, 'utf8')).length > 0)
    published = true
    return originalRename(source, target)
  }
  try {
    const action = actions.get('rebuild-memory-index')
    await action.getInput({ effects, prefill: null })
    await action.run({ effects, input: {} })
    assert.ok(published, 'request must be published by atomic rename')
    assert.notEqual(await fs.readFile(marker, 'utf8'), 'existing request')
    assert.ok(!(await fs.readdir(root)).some(name => name.endsWith('.tmp')))
  } finally {
    fs.rename = originalRename
  }
})
