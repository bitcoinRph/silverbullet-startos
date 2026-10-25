import * as fs from 'node:fs/promises'
import * as path from 'node:path'
import { utils, z } from '@start9labs/start-sdk'
import { storeJson } from './store.json'

const token = z.string().regex(/^[A-Za-z0-9]{48}$/)
const shape = z
  .object({
    schemaVersion: z.literal(1),
    enabled: z.boolean(),
    silverbulletApiToken: token,
    mcpReadToken: token,
    mcpWriteToken: token,
    createdAt: z.string(),
    rotatedAt: z.string(),
    allowedHosts: z.array(z.string()).max(16),
    allowedOrigins: z.array(z.string()).max(16),
  })
  .strict()
  .refine(
    (s) =>
      new Set([s.silverbulletApiToken, s.mcpReadToken, s.mcpWriteToken])
        .size === 3,
  )
export type AgentApiState = z.infer<typeof shape>
export const newToken = () =>
  utils.getDefaultString({ charset: 'a-z,A-Z,0-9', len: 48 })
let pending: Promise<unknown> = Promise.resolve()
function serialized<T>(fn: () => Promise<T>): Promise<T> {
  const next = pending.then(fn, fn)
  pending = next.catch(() => {})
  return next
}
async function atomicWrite(state: AgentApiState) {
  const value = shape.parse(state)
  const dir = path.dirname(agentApi.path)
  const temporary = path.join(dir, `.agent-api-${newToken()}.tmp`)
  try {
    const file = await fs.open(temporary, 'wx', 0o600)
    try {
      await file.writeFile(JSON.stringify(value) + '\n')
      await file.sync()
    } finally {
      await file.close()
    }
    await fs.rename(temporary, agentApi.path)
    const directory = await fs.open(dir, 'r')
    try {
      await directory.sync()
    } finally {
      await directory.close()
    }
  } finally {
    await fs.rm(temporary, { force: true })
  }
}
export const agentApi = {
  // Same main-volume root as store.json, never within the served space.
  get path() {
    return path.join(path.dirname(storeJson.path), 'agent-api.json')
  },
  async read(): Promise<AgentApiState> {
    try {
      return shape.parse(JSON.parse(await fs.readFile(this.path, 'utf8')))
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') throw error
      throw new Error(
        'Agent API state unavailable; restore its known-good backup.',
      )
    }
  },
  ensure() {
    return serialized(async () => {
      try {
        return await this.read()
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error
      }
      const now = new Date().toISOString()
      const state: AgentApiState = {
        schemaVersion: 1,
        enabled: false,
        silverbulletApiToken: newToken(),
        mcpReadToken: newToken(),
        mcpWriteToken: newToken(),
        createdAt: now,
        rotatedAt: now,
        allowedHosts: ['127.0.0.1:3001', 'localhost:3001'],
        allowedOrigins: [],
      }
      await atomicWrite(state)
      return state
    })
  },
  update(fn: (state: AgentApiState) => AgentApiState) {
    return serialized(async () => {
      const next = fn(await this.read())
      await atomicWrite(next)
      return next
    })
  },
}
