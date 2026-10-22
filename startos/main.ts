import { i18n } from './i18n'
import { sdk } from './sdk'
import { spaceDir, uiPort, username } from './utils'
import { storeJson } from './fileModels/store.json'
import { getCredentials } from './actions/getCredentials'

export const main = sdk.setupMain(async ({ effects }) => {
  console.info(i18n('Starting SilverBullet'))

  // Never launch without auth, including after a damaged/incomplete restore.
  let password: string | null | undefined
  try {
    password = await storeJson.read((s) => s.password).const(effects)
    // Upstream AuthConfig::try_parse splits SB_USER at the FIRST colon:
    // colons are valid in passwords, but not in the username. NUL cannot be
    // represented in an exec environment. Reject blank credentials, not spaces
    // within an otherwise valid password, and never normalize stored secrets.
    if (
      typeof username !== 'string' ||
      !username.trim() ||
      username.includes(':') ||
      username.includes('\0') ||
      typeof password !== 'string' ||
      !password.trim() ||
      password.includes('\0')
    ) {
      throw new Error('Invalid credentials')
    }
  } catch {
    // Do not expose JSON/parser errors (which may contain credential bytes),
    // and do not generate a replacement password over restored user data.
    await sdk.action.createOwnTask(effects, getCredentials, 'critical', {
      reason:
        'SilverBullet authentication unavailable. Restore a known-good backup including store.json, then start the service and retrieve your credentials. Existing notes and credentials have not been changed.',
    })
    throw new Error(
      'SilverBullet authentication unavailable; restore a known-good credential backup before starting.',
    )
  }

  const appSub = await sdk.SubContainer.of(
    effects,
    { imageId: 'silverbullet' },
    sdk.Mounts.of().mountVolume({
      volumeId: 'main',
      subpath: 'space',
      mountpoint: spaceDir,
      readonly: false,
    }),
    'silverbullet-sub',
  )

  return sdk.Daemons.of(effects).addDaemon('primary', {
    subcontainer: appSub,
    exec: {
      // The upstream image's entrypoint launches the server; configure it via SB_* env.
      command: sdk.useEntrypoint(),
      // The upstream entrypoint uses tini, which must run as PID 1.
      runAsInit: true,
      env: {
        SB_HOSTNAME: '0.0.0.0',
        SB_PORT: String(uiPort),
        SB_FOLDER: spaceDir,
        SB_USER: `${username}:${password}`,
      },
    },
    ready: {
      display: i18n('Web Interface'),
      fn: () =>
        sdk.healthCheck.checkPortListening(effects, uiPort, {
          successMessage: i18n('The web interface is ready'),
          errorMessage: i18n('The web interface is not ready'),
        }),
    },
    requires: [],
  })
})
