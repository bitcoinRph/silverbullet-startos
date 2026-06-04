import { FileHelper, z } from '@start9labs/start-sdk'
import { sdk } from '../sdk'

const shape = z.object({
  password: z.string().optional().catch(undefined),
})

// Persisted at the root of the main volume (NOT inside the 'space' subpath that
// SilverBullet serves), so the generated password never appears as a note.
export const storeJson = FileHelper.json(
  { base: sdk.volumes.main, subpath: 'store.json' },
  shape,
)
