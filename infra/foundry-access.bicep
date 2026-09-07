// Grants the Container App's managed identity access to a pre-existing Azure
// OpenAI / Microsoft Foundry account that lives in a different resource group
// than the app itself. Deployed as a module scoped to that resource group.
param foundryAccountName string
param principalId string

// "Cognitive Services OpenAI User" - lets the identity call chat completions
// against Azure OpenAI deployments using Entra ID auth (no API key).
var cognitiveServicesOpenAIUserRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
)

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: foundryAccountName
}

resource foundryRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundryAccount.id, principalId, cognitiveServicesOpenAIUserRoleId)
  scope: foundryAccount
  properties: {
    principalId: principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: cognitiveServicesOpenAIUserRoleId
  }
}
