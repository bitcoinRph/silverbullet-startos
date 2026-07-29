import { IMPOSSIBLE, VersionInfo } from '@start9labs/start-sdk'

export const v2_9_0_0 = VersionInfo.of({
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

export const current = VersionInfo.of({
  version: '2.10.0:0',
  releaseNotes: {
    en_US:
      'Updates SilverBullet to 2.10.0, including upstream multi-space and multi-account support while preserving StartOS-managed single-space credentials.',
    es_ES:
      'Actualiza SilverBullet a 2.10.0, incluida la compatibilidad upstream con múltiples espacios y cuentas, conservando las credenciales de espacio único gestionadas por StartOS.',
    de_DE:
      'Aktualisiert SilverBullet auf 2.10.0 mit Upstream-Unterstützung für mehrere Spaces und Konten, während die von StartOS verwalteten Single-Space-Anmeldedaten erhalten bleiben.',
    pl_PL:
      'Aktualizuje SilverBullet do wersji 2.10.0, w tym upstreamową obsługę wielu przestrzeni i kont, zachowując poświadczenia pojedynczej przestrzeni zarządzane przez StartOS.',
    fr_FR:
      'Met à jour SilverBullet vers 2.10.0, avec la prise en charge upstream de plusieurs espaces et comptes tout en conservant les identifiants mono-espace gérés par StartOS.',
  },
  migrations: {
    up: async ({ effects }) => {},
    down: IMPOSSIBLE,
  },
})
