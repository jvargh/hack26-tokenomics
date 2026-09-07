param environmentName string
param location string
param resourceToken string
param tokenosImageName string
param foundryBaseUrl string = ''
param foundryEfficientDeployment string = ''
param foundryAdvancedDeployment string = ''

var containerAppName = environmentName
var containerAppsEnvironmentName = 'azcae${resourceToken}'
var containerRegistryName = 'azacr${resourceToken}'
var identityName = 'azid${resourceToken}'
var logAnalyticsName = 'azlog${resourceToken}'
var applicationInsightsName = 'azai${resourceToken}'
var acrPullRoleDefinitionId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '7f951dda-4ed3-4680-a7ca-43fe172d538d'
)

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2025-02-01' = {
  name: logAnalyticsName
  location: location
  tags: {
    'azd-env-name': environmentName
  }
  properties: {
    retentionInDays: 30
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
  }
}

resource applicationInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: applicationInsightsName
  location: location
  kind: 'web'
  tags: {
    'azd-env-name': environmentName
  }
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
  }
}

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2025-04-01' = {
  name: containerRegistryName
  location: location
  tags: {
    'azd-env-name': environmentName
  }
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
    anonymousPullEnabled: false
    publicNetworkAccess: 'Enabled'
  }
}

resource userIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: identityName
  location: location
  tags: {
    'azd-env-name': environmentName
  }
}

resource acrPullRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(containerRegistry.id, userIdentity.id, acrPullRoleDefinitionId)
  scope: containerRegistry
  properties: {
    principalId: userIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: acrPullRoleDefinitionId
  }
}

resource containerAppsEnvironment 'Microsoft.App/managedEnvironments@2025-01-01' = {
  name: containerAppsEnvironmentName
  location: location
  tags: {
    'azd-env-name': environmentName
  }
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

var publicOrigin = 'https://${containerAppName}.${containerAppsEnvironment.properties.defaultDomain}'

resource containerApp 'Microsoft.App/containerApps@2025-01-01' = {
  name: containerAppName
  location: location
  tags: {
    'azd-env-name': environmentName
    'azd-service-name': 'tokenos'
  }
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${userIdentity.id}': {}
    }
  }
  properties: {
    environmentId: containerAppsEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
        corsPolicy: {
          allowedOrigins: [
            publicOrigin
          ]
          allowedMethods: [
            'GET'
            'POST'
            'DELETE'
            'OPTIONS'
          ]
          allowedHeaders: [
            '*'
          ]
          allowCredentials: false
        }
      }
      registries: [
        {
          server: containerRegistry.properties.loginServer
          identity: userIdentity.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'tokenos'
          image: !empty(tokenosImageName)
            ? tokenosImageName
            : 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
          env: [
            {
              name: 'TOKENOS_MODEL_MODE'
              value: !empty(foundryBaseUrl) ? 'foundry' : 'local'
            }
            {
              name: 'TOKENOS_FOUNDRY_BASE_URL'
              value: foundryBaseUrl
            }
            {
              name: 'TOKENOS_FOUNDRY_EFFICIENT_DEPLOYMENT'
              value: foundryEfficientDeployment
            }
            {
              name: 'TOKENOS_FOUNDRY_ADVANCED_DEPLOYMENT'
              value: foundryAdvancedDeployment
            }
            {
              name: 'TOKENOS_FOUNDRY_AUTH_MODE'
              value: 'entra'
            }
            {
              name: 'AZURE_CLIENT_ID'
              value: userIdentity.properties.clientId
            }
            {
              name: 'TOKENOS_STORAGE_ROOT'
              value: '/tmp/tokenos/runtime'
            }
            {
              name: 'TOKENOS_WEB_DIST_ROOT'
              value: '/app/services/tokenos-api/static'
            }
            {
              name: 'TOKENOS_CORS_ORIGINS'
              value: publicOrigin
            }
            {
              name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
              value: applicationInsights.properties.ConnectionString
            }
          ]
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          probes: [
            {
              type: 'Startup'
              httpGet: {
                path: '/health'
                port: 8000
                scheme: 'HTTP'
              }
              initialDelaySeconds: 0
              periodSeconds: 5
              failureThreshold: 12
              timeoutSeconds: 3
            }
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 8000
                scheme: 'HTTP'
              }
              initialDelaySeconds: 10
              periodSeconds: 30
              failureThreshold: 3
              timeoutSeconds: 3
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/health'
                port: 8000
                scheme: 'HTTP'
              }
              initialDelaySeconds: 5
              periodSeconds: 10
              failureThreshold: 3
              timeoutSeconds: 3
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 3
        rules: [
          {
            name: 'http-scaling'
            http: {
              metadata: {
                concurrentRequests: '50'
              }
            }
          }
        ]
      }
    }
  }
  dependsOn: [
    acrPullRoleAssignment
  ]
}

output registryEndpoint string = containerRegistry.properties.loginServer
output containerAppName string = containerApp.name
output containerAppUri string = publicOrigin
output identityPrincipalId string = userIdentity.properties.principalId
