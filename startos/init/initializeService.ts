import { utils } from '@start9labs/start-sdk'
import { i18n } from '../i18n'
import { sdk } from '../sdk'
import { storeJson } from '../fileModels/store.json'
import { getCredentials } from '../actions/getCredentials'

export const initializeService = sdk.setupOnInit(async (effects, kind) => {
  // Generate a login password once, on a fresh install.
  if (kind === 'install') {
    const password = utils.getDefaultString({
      charset: 'a-z,A-Z,0-9',
      len: 22,
    })
    await storeJson.write(effects, { password })
  }

  // On install and restore, prompt the user to retrieve their credentials.
  if (kind !== null) {
    await sdk.action.createOwnTask(effects, getCredentials, 'critical', {
      reason: i18n('Retrieve your SilverBullet login credentials'),
    })
  }
})
