import { i18n } from './i18n'
import { sdk } from './sdk'
import { spaceDir, uiPort, username } from './utils'
import { storeJson } from './fileModels/store.json'

export const main = sdk.setupMain(async ({ effects }) => {
  console.info(i18n('Starting SilverBullet'))

  // Read the generated login password so we can enable SilverBullet's auth.
  const password = await storeJson.read((s) => s.password).const(effects)

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
      env: {
        SB_HOSTNAME: '0.0.0.0',
        SB_PORT: String(uiPort),
        SB_FOLDER: spaceDir,
        ...(password ? { SB_USER: `${username}:${password}` } : {}),
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
