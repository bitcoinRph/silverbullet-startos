import { IMPOSSIBLE, VersionInfo } from '@start9labs/start-sdk'

export const current = VersionInfo.of({
  version: '2.9.0:0',
  releaseNotes: {
    en_US: 'Initial StartOS release of SilverBullet 2.9.0.',
    es_ES: 'Versión inicial de SilverBullet 2.9.0 para StartOS.',
    de_DE: 'Erste StartOS-Veröffentlichung von SilverBullet 2.9.0.',
    pl_PL: 'Pierwsze wydanie SilverBullet 2.9.0 dla StartOS.',
    fr_FR: 'Première version StartOS de SilverBullet 2.9.0.',
  },
  migrations: {
    up: async ({ effects }) => {},
    down: IMPOSSIBLE,
  },
})
