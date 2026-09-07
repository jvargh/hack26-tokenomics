targetScope = 'subscription'

@minLength(1)
@maxLength(32)
param environmentName string

param location string

param tokenosImageName string = ''

@description('Pre-existing Azure OpenAI / Microsoft Foundry account to grant the app access to. Empty disables Foundry wiring and the app runs in local mode.')
param foundryAccountName string = ''

@description('Resource group containing foundryAccountName. Ignored when foundryAccountName is empty.')
param foundryResourceGroupName string = ''

param foundryBaseUrl string = ''
param foundryEfficientDeployment string = ''
param foundryAdvancedDeployment string = ''

var resourceToken = uniqueString(subscription().id, location, environmentName)
var resourceGroupName = 'azrg${resourceToken}'

resource resourceGroup 'Microsoft.Resources/resourceGroups@2025-04-01' = {
  name: resourceGroupName
  location: location
  tags: {
    'azd-env-name': environmentName
  }
}

module tokenosResources './resources.bicep' = {
  name: 'tokenos-resources'
  scope: resourceGroup
  params: {
    environmentName: environmentName
    location: location
    resourceToken: resourceToken
    tokenosImageName: tokenosImageName
    foundryBaseUrl: foundryBaseUrl
    foundryEfficientDeployment: foundryEfficientDeployment
    foundryAdvancedDeployment: foundryAdvancedDeployment
  }
}

module foundryAccess './foundry-access.bicep' = if (!empty(foundryAccountName)) {
  name: 'foundry-access'
  scope: az.resourceGroup(foundryResourceGroupName)
  params: {
    foundryAccountName: foundryAccountName
    principalId: tokenosResources.outputs.identityPrincipalId
  }
}

output AZURE_LOCATION string = location
output AZURE_RESOURCE_GROUP_NAME string = resourceGroup.name
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = tokenosResources.outputs.registryEndpoint
output SERVICE_TOKENOS_NAME string = tokenosResources.outputs.containerAppName
output SERVICE_TOKENOS_URI string = tokenosResources.outputs.containerAppUri
