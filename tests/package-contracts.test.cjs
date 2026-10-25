const assert = require('node:assert/strict')
const { test } = require('node:test')
const { readFileSync, existsSync } = require('node:fs')
const read = p => readFileSync(p, 'utf8')
test('memory image is scoped non-root hash-locked and excludes repository dependencies', () => {
  const docker = read('memory-mcp/Dockerfile')
  assert.match(docker, /USER 10001:10001/)
  assert.match(docker, /--require-hashes/)
  assert.match(docker, /COPY src/)
  assert.ok(!docker.includes('COPY . '))
  const health = read('memory-mcp/src/silverbullet_memory/health.py')
  assert.match(health, /status_code == 200/)
  assert.match(health, /\[['"]ready['"]\]/)
})
test('manifest Dockerfile ingredient resolves from the repository root', () => {
  const file = read('startos/manifest/index.ts').match(/dockerfile: '([^']+)'/)[1]
  assert.ok(existsSync(file), `missing Dockerfile ingredient: ${file}`)
  assert.equal(file, 'memory-mcp/Dockerfile')
})
test('PR builds exact head and release excludes integration-only changes', () => {
  assert.ok(read('.github/workflows/pr-build.yml').includes('ref: ${{ github.event.pull_request.head.sha }}'))
  assert.match(read('.github/workflows/release.yml'), /integrations\/\*\*/)
})
test('one independently versioned skill forbids acting on retrieved instructions', () => {
  const skill = read('integrations/hermes/skills/silverbullet-memory/SKILL.md')
  for (const tool of ['memory_status','memory_search','memory_get','memory_backlinks','memory_create','memory_replace_text']) assert.ok(skill.includes(tool))
  assert.match(skill, /untrusted/i)
  assert.match(skill, /approval/i)
})
