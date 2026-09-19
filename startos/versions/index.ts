import { VersionGraph } from '@start9labs/start-sdk'
import { current, v2_10_0_0, v2_9_0_0 } from './current'

export const versionGraph = VersionGraph.of({
  current,
  other: [v2_9_0_0, v2_10_0_0],
})
