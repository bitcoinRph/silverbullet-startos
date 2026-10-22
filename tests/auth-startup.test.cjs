const assert = require('node:assert/strict')
const { test, after } = require('node:test')
const fs = require('node:fs/promises')
const path = require('node:path')
const os = require('node:os')
const ts = require('typescript')

// Execute the real package TypeScript and SDK FileHelper without building or
// replacing its parser/read/const implementation. Stub only StartOS RPC edges.
require.extensions['.ts'] = (module, filename) => {
  const source = require('node:fs').readFileSync(filename, 'utf8')
  module._compile(
    ts.transpileModule(source, {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        target: ts.ScriptTarget.ES2022,
      },
    }).outputText,
    filename,
  )
}
const { sdk } = require('../startos/sdk.ts')
const { storeJson } = require('../startos/fileModels/store.json.ts')
const utils = require('../startos/utils.ts')
const { main } = require('../startos/main.ts')
const { initializeService } = require('../startos/init/initializeService.ts')
const originalPath = storeJson.path
const originals = [
  sdk.SubContainer.of,
  sdk.Daemons.of,
  sdk.action.createOwnTask,
]
let subcontainers = [],
  daemons = [],
  tasks = []
sdk.SubContainer.of = async (...args) => {
  subcontainers.push(args)
  return {}
}
sdk.Daemons.of = () => ({
  addDaemon(id, definition) {
    daemons.push({ id, ...definition })
    return this
  },
})
sdk.action.createOwnTask = async (...args) => {
  tasks.push(args)
  return null
}
const effects = { isInContext: true }
let root
async function fixture(raw) {
  root ??= await fs.mkdtemp(path.join(os.tmpdir(), 'silverbullet-auth-test-'))
  storeJson.path = path.join(root, 'store.json')
  await fs.rm(storeJson.path, { force: true })
  if (raw !== undefined) await fs.writeFile(storeJson.path, raw)
  utils.username = 'admin'
  subcontainers = []
  daemons = []
  tasks = []
}
after(async () => {
  storeJson.path = originalPath
  utils.username = 'admin'
  ;[sdk.SubContainer.of, sdk.Daemons.of, sdk.action.createOwnTask] = originals
  if (root) await fs.rm(root, { recursive: true, force: true })
})
const invalid = [
  ['missing store', undefined],
  ['empty file', ''],
  ['malformed JSON', '{"password":"secret-marker"'],
  ['null store', 'null'],
  ['array store', '[]'],
  ['missing password', '{}'],
  ['null password', '{"password":null}'],
  ['numeric password', '{"password":123}'],
  ['object password', '{"password":{}}'],
  ['empty password', '{"password":""}'],
  ['blank password', '{"password":" \\t\\n"}'],
  ['NUL password', '{"password":"secret-marker\\u0000"}'],
]
for (const [label, raw] of invalid)
  test(`blocks ${label} before container creation`, async () => {
    await fixture(raw)
    const before = raw
    await assert.rejects(main({ effects }), (error) => {
      assert.match(error.message, /SilverBullet authentication unavailable/)
      assert.ok(!error.message.includes('secret-marker'))
      return true
    })
    assert.equal(subcontainers.length, 0)
    assert.equal(daemons.length, 0)
    assert.equal(tasks.length, 1)
    assert.equal(tasks[0][2], 'critical')
    assert.match(tasks[0][3].reason, /restore.*backup/i)
    assert.equal(
      await fs.readFile(storeJson.path, 'utf8').catch(() => undefined),
      before,
    )
  })
for (const username of [
  undefined,
  null,
  42,
  '',
  '   ',
  'bad:name',
  'bad\0name',
])
  test(`blocks invalid username ${JSON.stringify(username)}`, async () => {
    await fixture('{"password":"valid-test-secret"}')
    utils.username = username
    await assert.rejects(
      main({ effects }),
      /SilverBullet authentication unavailable/,
    )
    assert.equal(subcontainers.length, 0)
    assert.equal(daemons.length, 0)
  })
for (const password of [
  'alphaNumeric123',
  'a:b:c',
  '  meaningful whitespace  ',
  'unicode-\u00e9-\ud83d\udd12',
])
  test('preserves valid credentials byte-for-byte', async () => {
    const raw = JSON.stringify({ password })
    await fixture(raw)
    await main({ effects })
    assert.equal(daemons.length, 1)
    assert.equal(daemons[0].exec.env.SB_USER, `admin:${password}`)
    assert.equal(daemons[0].exec.runAsInit, true)
    assert.equal(daemons[0].exec.env.SB_FOLDER, '/data')
    assert.equal(subcontainers[0][2].build()[0].options.subpath, 'space')
    assert.equal(tasks.length, 0)
    assert.equal(await fs.readFile(storeJson.path, 'utf8'), raw)
  })
test('restore and rebuild never replace a valid store; changed password reaches next launch', async () => {
  await fixture('{"password":"original-test-secret"}')
  const before = await fs.readFile(storeJson.path, 'utf8')
  await initializeService.init(effects, 'restore')
  await initializeService.init(effects, null)
  assert.equal(await fs.readFile(storeJson.path, 'utf8'), before)
  await main({ effects })
  await storeJson.write(effects, { password: 'changed:test-secret' })
  await main({ effects })
  assert.equal(daemons[0].exec.env.SB_USER, 'admin:original-test-secret')
  assert.equal(daemons[1].exec.env.SB_USER, 'admin:changed:test-secret')
})
test('fresh install still generates credentials accepted by startup', async () => {
  await fixture()
  await initializeService.init(effects, 'install')
  const password = await storeJson.read((s) => s.password).once()
  assert.match(password, /^[A-Za-z0-9]{22}$/)
  await main({ effects })
  assert.equal(daemons[0].exec.env.SB_USER, `admin:${password}`)
})
