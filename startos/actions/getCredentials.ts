import { i18n } from '../i18n'
import { sdk } from '../sdk'
import { storeJson } from '../fileModels/store.json'
import { username } from '../utils'

export const getCredentials = sdk.Action.withoutInput(
  'get-credentials',

  async ({ effects }) => ({
    name: i18n('Get Credentials'),
    description: i18n('Retrieve your SilverBullet login username and password'),
    warning: null,
    allowedStatuses: 'any',
    group: null,
    visibility: 'enabled',
  }),

  async ({ effects }) => {
    const password = await storeJson.read((s) => s.password).once()

    return {
      version: '1' as const,
      title: 'SilverBullet Credentials',
      message: 'Use these credentials to log in to SilverBullet.',
      result: {
        type: 'group',
        value: [
          {
            type: 'single',
            name: 'Username',
            description: null,
            value: username,
            masked: false,
            copyable: true,
            qr: false,
          },
          {
            type: 'single',
            name: 'Password',
            description: null,
            value: password ?? 'UNKNOWN',
            masked: true,
            copyable: true,
            qr: false,
          },
        ],
      },
    }
  },
)
