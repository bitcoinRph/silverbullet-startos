import { setupManifest } from '@start9labs/start-sdk'
import { long, short, alertInstall } from './i18n'

export const manifest = setupManifest({
  id: 'silverbullet',
  title: 'SilverBullet',
  license: 'MIT',
  packageRepo: 'https://github.com/bitcoinRph/silverbullet-startos',
  upstreamRepo: 'https://github.com/silverbulletmd/silverbullet',
  marketingUrl: 'https://silverbullet.md',
  donationUrl: null,
  description: { short, long },
  volumes: ['main', 'index'],
  images: {
    silverbullet: {
      source: { dockerTag: 'ghcr.io/silverbulletmd/silverbullet:2.12.1' },
      arch: ['x86_64', 'aarch64'],
    },
    'memory-mcp': {
      source: {
        dockerBuild: { dockerfile: 'Dockerfile', workdir: 'memory-mcp' },
      },
      arch: ['x86_64', 'aarch64'],
    },
  },
  alerts: {
    install: alertInstall,
    update: null,
    uninstall: null,
    restore: null,
    start: null,
    stop: null,
  },
  dependencies: {},
})
