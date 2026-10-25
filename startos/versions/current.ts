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

export const v2_10_0_0 = VersionInfo.of({
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

export const v2_11_0_0 = VersionInfo.of({
  version: '2.11.0:0',
  releaseNotes: {
    en_US:
      'Updates SilverBullet to 2.11.0 with collaboration, SSO/permissions, comments, revisions, Obsidian-compatible link resolving, and a refreshed UI; the StartOS package now mounts the space at the upstream-preferred /data path while preserving the same main volume subpath.',
    es_ES:
      'Actualiza SilverBullet a 2.11.0 con colaboración, SSO/permisos, comentarios, revisiones, resolución de enlaces compatible con Obsidian y una interfaz renovada; el paquete StartOS ahora monta el espacio en la ruta /data preferida por upstream, conservando la misma subruta del volumen principal.',
    de_DE:
      'Aktualisiert SilverBullet auf 2.11.0 mit Zusammenarbeit, SSO/Berechtigungen, Kommentaren, Revisionen, Obsidian-kompatibler Linkauflösung und aktualisierter Oberfläche; das StartOS-Paket mountet den Space jetzt unter dem von Upstream bevorzugten Pfad /data und behält denselben Unterpfad des Hauptvolumes bei.',
    pl_PL:
      'Aktualizuje SilverBullet do wersji 2.11.0 z funkcjami współpracy, SSO/uprawnieniami, komentarzami, rewizjami, rozwiązywaniem linków zgodnym z Obsidianem i odświeżonym interfejsem; pakiet StartOS montuje teraz przestrzeń w preferowanej przez upstream ścieżce /data, zachowując tę samą podścieżkę głównego wolumenu.',
    fr_FR:
      'Met à jour SilverBullet vers 2.11.0 avec collaboration, SSO/autorisations, commentaires, révisions, résolution de liens compatible Obsidian et interface rafraîchie ; le package StartOS monte désormais l’espace sur le chemin /data préféré par upstream tout en conservant le même sous-chemin du volume principal.',
  },
  migrations: {
    up: async ({ effects }) => {},
    down: IMPOSSIBLE,
  },
})

export const current = VersionInfo.of({
  version: '2.12.1:1',
  releaseNotes: {
    en_US:
      'Opt-in authenticated Business Memory MCP with a separate rebuildable index. Runtime API is now always disabled. MCP mutations remain hard-disabled pending real-client safety evidence; previews are available. Preserves login and space; adds separate atomic Agent API state.',
  },
  migrations: {
    up: async () => {},
    // :0 ignores agent-api.json and the rebuildable index. No canonical data change.
    down: async () => {},
  },
})

export const v2_12_1_0 = VersionInfo.of({
  version: '2.12.1:0',
  releaseNotes: {
    en_US:
      'Updates SilverBullet to 2.12.1 with mobile and large-space performance improvements, hidden-file API protection, and proxy ETag fixes. Breaking Space Lua change: replace view.new with widget.new and pass widget to view.define. Preserves StartOS-managed credentials and notes, runs the upstream tini entrypoint as PID 1, and corrects the package repository link. Full notes: https://github.com/silverbulletmd/silverbullet/blob/2.12.1/docs/CHANGELOG.md',
    es_ES:
      'Actualiza SilverBullet a 2.12.1 con mejoras móviles y de rendimiento, protección de archivos ocultos y correcciones ETag. Cambio incompatible en Space Lua: sustituya view.new por widget.new y pase widget a view.define. Conserva credenciales y notas, ejecuta tini como PID 1 y corrige el enlace del repositorio. Notas: https://github.com/silverbulletmd/silverbullet/blob/2.12.1/docs/CHANGELOG.md',
    de_DE:
      'Aktualisiert SilverBullet auf 2.12.1 mit Verbesserungen für Mobilgeräte und große Spaces, Schutz versteckter Dateien und ETag-Korrekturen. Inkompatible Space-Lua-Änderung: view.new durch widget.new ersetzen und widget an view.define übergeben. Behält Anmeldedaten und Notizen bei, startet tini als PID 1 und korrigiert den Repository-Link. Hinweise: https://github.com/silverbulletmd/silverbullet/blob/2.12.1/docs/CHANGELOG.md',
    pl_PL:
      'Aktualizuje SilverBullet do 2.12.1 z usprawnieniami mobilnymi i wydajności, ochroną ukrytych plików i poprawkami ETag. Niezgodna zmiana Space Lua: zastąp view.new przez widget.new i przekaż widget do view.define. Zachowuje poświadczenia i notatki, uruchamia tini jako PID 1 i poprawia adres repozytorium. Uwagi: https://github.com/silverbulletmd/silverbullet/blob/2.12.1/docs/CHANGELOG.md',
    fr_FR:
      'Met à jour SilverBullet vers 2.12.1 avec des améliorations mobiles et de performances, la protection des fichiers cachés et des corrections ETag. Changement incompatible Space Lua : remplacer view.new par widget.new et passer widget à view.define. Conserve identifiants et notes, exécute tini comme PID 1 et corrige le lien du dépôt. Notes : https://github.com/silverbulletmd/silverbullet/blob/2.12.1/docs/CHANGELOG.md',
  },
  migrations: {
    up: async ({ effects }) => {},
    down: IMPOSSIBLE,
  },
})
