import { sdk } from '../sdk'
import { getCredentials } from './getCredentials'
import {
  enableAgentApi,
  disableAgentApi,
  getMcpCredentials,
  rotateMcpTokens,
  rotateInternalToken,
  rebuildMemoryIndex,
} from './agentApi'

export const actions = sdk.Actions.of()
  .addAction(getCredentials)
  .addAction(enableAgentApi)
  .addAction(disableAgentApi)
  .addAction(getMcpCredentials)
  .addAction(rotateMcpTokens)
  .addAction(rotateInternalToken)
  .addAction(rebuildMemoryIndex)
