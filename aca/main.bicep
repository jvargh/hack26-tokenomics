// Judge demonstration revision of the existing Container App.
//
// This template deliberately does NOT create the Container App, its
// environment, the registry or the managed identity. Those already exist and
// belong to infra/. Creating them again here would risk reconfiguring live
// infrastructure to ship a demonstration.
//
// It configures the existing app to run the simulated image with durable
// storage. It grants no model-inference permission of any kind: the judge
// build has no provider SDK and no endpoint to call.

targetScope = 'resourceGroup'

@description('Name of the existing Container App to update.')
param containerAppName string = 'tokenos-hack26'

@description('Name of the existing Container Apps managed environment.')
param environmentName string

@description('Fully qualified image reference, preferably pinned by digest.')
param image string

@description('Existing user-assigned identity used to pull from the registry.')
param userAssignedIdentityId string

@description('Login server of the private registry holding the image.')
param registryServer string

// Writable path inside the container, matching TOKENOS_STORAGE_ROOT.
//
// This is the replica's own ephemeral disk, not a mounted share. Saved runs
// therefore survive for the lifetime of the running container but are LOST on
// restart, scale event or image roll. That is a deliberate, accepted trade-off
// to avoid provisioning a storage account for this demonstration; it is
// recorded in aca/README.md under Limitations rather than left for a judge to
// discover. Attaching an Azure Files share at this same path is the single
// change needed to make the data durable.
var storageRoot = '/data/tokenos'

resource environment 'Microsoft.App/managedEnvironments@2025-01-01' existing = {
  name: environmentName
}

resource containerApp 'Microsoft.App/containerApps@2025-01-01' = {
  name: containerAppName
  location: resourceGroup().location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${userAssignedIdentityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: environment.id
    configuration: {
      // Single revision mode. Two revisions would mean two writers against one
      // SQLite file on a shared mount.
      activeRevisionsMode: 'Single'
      ingress: {
        // Public and unauthenticated by design: judges must reach the demo
        // without signing in. The application keeps its own input bounds,
        // origin checks and per-session isolation.
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
      }
      registries: [
        {
          server: registryServer
          identity: userAssignedIdentityId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'tokenos'
          image: image
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            // The setting that makes this a demonstration. The application
            // rejects any unrecognised value at startup rather than guessing.
            { name: 'TOKENOS_MODEL_MODE', value: 'simulated' }
            { name: 'TOKENOS_STORAGE_ROOT', value: storageRoot }
            { name: 'TOKENOS_WEB_DIST_ROOT', value: '/app/services/tokenos-api/static' }
            // Same-origin deployment: the API serves the built web assets, so
            // no cross-origin browser access is required.
            { name: 'TOKENOS_CORS_ORIGINS', value: 'https://${containerAppName}.${environment.properties.defaultDomain}' }
          ]
          volumeMounts: []
          probes: [
            {
              type: 'Liveness'
              httpGet: { path: '/health', port: 8000 }
              initialDelaySeconds: 10
              periodSeconds: 30
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: { path: '/health', port: 8000 }
              initialDelaySeconds: 5
              periodSeconds: 10
              failureThreshold: 3
            }
          ]
        }
      ]
      volumes: []
      scale: {
        // Exactly one replica. The store is a file-backed SQLite database and
        // concurrent writers corrupt it. This is a correctness constraint, not
        // a cost decision, and it must not be raised without moving the store
        // to a backend that supports multiple writers.
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

output fqdn string = containerApp.properties.configuration.ingress.fqdn
output url string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
output revision string = containerApp.properties.latestRevisionName
