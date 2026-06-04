// Constants and helpers shared across the package codebase.

// Port SilverBullet's web server listens on inside the container (SB_PORT).
export const uiPort = 3000

// Login username paired with the generated password (passed via SB_USER).
export const username = 'admin'

// Where the SilverBullet "space" (your Markdown files) lives in the container.
// The main volume is mounted here via a dedicated subpath so package state
// (store.json) stays out of the user's space folder.
export const spaceDir = '/space'
