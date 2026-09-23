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
  version: '2.11.1:0',
  releaseNotes: {
    en_US:
      'Updates SilverBullet to 2.11.1 with upstream fixes for Git/revision history, direct HTML/CSS/JavaScript opening, readable dark-mode tooltips, longer Git connection checks, Mention Inbox access from Space Lua/CLI, richer document and media viewing, and drag-and-drop uploads.',
    es_ES:
      'Actualiza SilverBullet a 2.11.1 con correcciones upstream para Git/historial de revisiones, apertura directa de HTML/CSS/JavaScript, tooltips legibles en modo oscuro, comprobaciones Git más largas, acceso a Mention Inbox desde Space Lua/CLI, vista de más documentos y medios, y cargas por arrastrar y soltar.',
    de_DE:
      'Aktualisiert SilverBullet auf 2.11.1 mit Upstream-Korrekturen für Git/Revisionsverlauf, direktes Öffnen von HTML/CSS/JavaScript, lesbare Tooltips im Dark Mode, längere Git-Verbindungsprüfungen, Mention-Inbox-Zugriff aus Space Lua/CLI, umfangreichere Dokument- und Medienanzeige sowie Drag-and-drop-Uploads.',
    pl_PL:
      'Aktualizuje SilverBullet do wersji 2.11.1 z poprawkami upstream dla Git/historii rewizji, bezpośredniego otwierania HTML/CSS/JavaScript, czytelnych podpowiedzi w trybie ciemnym, dłuższych kontroli połączenia Git, dostępu do Mention Inbox ze Space Lua/CLI, szerszego podglądu dokumentów i multimediów oraz przesyłania przez przeciąganie i upuszczanie.',
    fr_FR:
      'Met à jour SilverBullet vers 2.11.1 avec des correctifs upstream pour Git/l’historique des révisions, l’ouverture directe des fichiers HTML/CSS/JavaScript, les infobulles lisibles en mode sombre, des vérifications Git plus longues, l’accès à Mention Inbox depuis Space Lua/CLI, l’affichage enrichi de documents et médias, et les téléversements par glisser-déposer.',
  },
  migrations: {
    up: async ({ effects }) => {},
    down: IMPOSSIBLE,
  },
})
