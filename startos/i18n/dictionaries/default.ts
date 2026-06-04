export const DEFAULT_LANG = 'en_US'

const dict = {
  // main.ts
  'Starting SilverBullet': 0,
  'Web Interface': 1,
  'The web interface is ready': 2,
  'The web interface is not ready': 3,

  // interfaces.ts
  'Web UI': 4,
  'The SilverBullet web interface': 5,

  // actions/getCredentials.ts
  'Get Credentials': 6,
  'Retrieve your SilverBullet login username and password': 7,

  // init/initializeService.ts
  'Retrieve your SilverBullet login credentials': 8,
} as const

/**
 * Plumbing. DO NOT EDIT.
 */
export type I18nKey = keyof typeof dict
export type LangDict = Record<(typeof dict)[I18nKey], string>
export default dict
