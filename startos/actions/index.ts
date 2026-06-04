import { sdk } from '../sdk'
import { getCredentials } from './getCredentials'

export const actions = sdk.Actions.of().addAction(getCredentials)
