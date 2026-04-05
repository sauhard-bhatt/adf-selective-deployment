# Azure Data Factory (ADF) CI/CD — Selective Deployment (Pipelines/Datasets)

This repository stores **Azure Data Factory assets as code** and provides a **GitHub Actions CI/CD pipeline** to:

1. **Validate ADF changes on PRs** using Microsoft’s ADF Utilities.
2. **Build and deploy a selective subset of ADF assets** (driven by a manifest) to **DEV**.

The key idea: **deploy only specific pipelines (and their dependencies)** instead of deploying the entire factory. The workflow exports an ARM template from a staged subset, then produces a **safe template** by stripping infra-owned resources before deploying.

---

## What this repo contains

ADF assets are stored at the repo root using ADF’s standard JSON folder layout:

```text
.
├─ pipeline/                 # pipeline JSONs
├─ dataset/                  # dataset JSONs
├─ linkedService/            # linked service JSONs
├─ trigger/                  # triggers (optional for selective deploy)
├─ factory/                  # factory-level artifacts (may exist)
├─ deploy/
│  └─ manifests/
│     └─ release.json        # selective deploy manifest
├─ scripts/
│  ├─ select_adf_subset.py   # stages subset into build/adf_subset/
│  └─ strip_arm_resources.py # strips infra-owned resources from ARM template
├─ publish_config.json
├─ arm-template-parameters-definition.json
├─ package.json              # root uses @microsoft/azure-data-factory-utilities
└─ package-lock.json
```

---

## Workflows

### 1) PR validation — `adf-validate-develop-pr.yml`

**Trigger:** Pull requests targeting branch `selective_deployment`.

**Purpose:** Validate that the ADF JSON in the PR is valid in the context of the target factory.

**Main steps:**
- Checkout
- Setup Node.js 20
- `npm install`
- Azure login using **OIDC** (`azure/login@v2`)
- Validate with ADF Utilities:

```bash
FACTORY_ID="/subscriptions/${AZURE_SUBSCRIPTION_ID}/resourceGroups/${AZURE_RESOURCE_GROUP}/providers/Microsoft.DataFactory/factories/${DEV_FACTORY_NAME}"
npm run build validate "$GITHUB_WORKSPACE" "$FACTORY_ID"
```

> This is a CI guardrail: PRs fail early if assets are invalid/misaligned.

---

### 2) Release build + selective deploy to DEV — `adf-release-build-selective-deploy.yml`

**Triggers:**
- Push to `selective_deployment`
- Manual run (`workflow_dispatch`) with optional `manifest` input  
  Default: `deploy/manifests/release.json`

This workflow has two jobs:

#### Job A: `adf-build` (staging + export + sanitize + artifacts)

1. Checkout (full history)
2. Azure login using OIDC
3. Setup Node.js 20
4. Install build dependencies inside `build/` (`npm install` in `build`)
5. **Stage selective subset**
   - `python3 scripts/select_adf_subset.py <manifest>`
   - Produces:
     - `build/adf_subset/` (staged tree)
     - `build/adf_subset_report.json` (dependency report)
6. **Export ARM templates from staged subset** via ADF Utilities:
   - `npm --prefix build run build -- export "adf_subset" "$FACTORY_ID" "ArmTemplate"`
   - Produces:
     - `build/ArmTemplate/ARMTemplateForFactory.json`
     - `build/ArmTemplate/ARMTemplateParametersForFactory.json`
7. **Strip infra-owned resources** to produce a safe template:
   - `build/ArmTemplate/ARMTemplateForFactory.safe.json`
8. Upload artifacts:
   - ARM templates (`adf-arm`)
   - metadata (`adf-release-meta`)
   - subset report (`adf-subset-report`)

#### Job B: `deploy_dev` (deploy safe template)

1. Download ARM artifact
2. Azure login using OIDC
3. Ensure `az` Data Factory extension is installed
4. Validate JSON files exist/parse
5. Deploy via `azure/arm-deploy@v2` (Incremental) to DEV RG/factory:
   - Template: `ARMTemplateForFactory.safe.json`
   - Parameters: `ARMTemplateParametersForFactory.json` + `factoryName=<DEV_FACTORY_NAME>`

---

## Selective deployment manifest

The manifest controls which pipelines to deploy and which optional categories may be included.

`deploy/manifests/release.json` (current example):

```json
{
  "pipelines": [
    "pl_ingest_population_selective1",
    "pl_ingest_population_selective",
    "pl_get_meta_temporary_copy1",
    "pl_get_meta_temporary_copy2"
  ],
  "includeTriggers": false,
  "includeIntegrationRuntimes": false,
  "includeAllGlobalParameters": true,

  "includeLinkedServices": true,
  "validateLinkedServicesExist": true,

  "includeManagedVirtualNetwork": false,
  "includeManagedPrivateEndpoints": false
}
```

### Notes on manifest behavior (based on the script)
- `pipelines` is required (script exits if empty).
- `includeTriggers` controls staging triggers (and the script tries to include only triggers that reference included pipelines).
- `includeIntegrationRuntimes` controls whether to stage:
  - all IRs (when true), OR
  - only referenced IRs (when false, but references exist)
- `includeAllGlobalParameters` copies `globalParameters/*.json` into the subset stage.
- `includeCredentials` is supported by the script (not present in your example manifest).
- `includeLinkedServices` / `validateLinkedServicesExist` exist in the manifest, but the script primarily stages linked services **based on discovered references** and warns if missing (strict enforcement can be added if desired).
- `includeManagedPrivateEndpoints` exists in the manifest, but the current script does not explicitly stage private endpoints (it only stages `managedVirtualNetwork` when enabled).

---

## What exactly gets copied into `build/adf_subset/`

`build/adf_subset/` is a staged mini-repo that ADF Utilities can run against.

### Always copied (when present)
From `scripts/select_adf_subset.py`, the script copies these root files into the staged subset:

- `publish_config.json`
- `arm-template-parameters-definition.json`
- `package.json`
- `package-lock.json`

### Copied based on dependency discovery
The script then stages resources recursively by parsing JSON references:

1. **Pipelines**
   - Copies each pipeline from `manifest.pipelines`
   - Recursively discovers child pipelines via `PipelineReference` (for example ExecutePipeline)
2. **Datasets**
   - Copies all datasets referenced by pipelines/activities
3. **Linked Services**
   - Copies linked services referenced by pipelines/datasets
   - Performs transitive closure for linked services:
     - Key Vault store LS via `AzureKeyVaultSecret.store.referenceName`
     - Credential references (`CredentialReference`)
     - Integration runtime references (for example via `connectVia.referenceName`)

### Optional copies (controlled by manifest flags)
- `globalParameters/` (when `includeAllGlobalParameters: true`)
- `trigger/` (when `includeTriggers: true`)
- `integrationRuntime/` (when `includeIntegrationRuntimes: true` OR when referenced IRs are discovered and folder exists)
- `credential/` (when `includeCredentials: true` and folder exists)
- `managedVirtualNetwork/` (when `includeManagedVirtualNetwork: true` and folder exists)

### Workflow log output will contains 
- Root control files:
  - `publish_config.json`
  - `arm-template-parameters-definition.json`
  - `package.json`
  - `package-lock.json`
- `pipeline/`:
  - `pl_get_meta_temporary_copy1.json`
  - `pl_get_meta_temporary_copy2.json`
  - `pl_ingest_population_selective.json`
  - `pl_ingest_population_selective1.json`
- `dataset/`:
  - `ds_population_raw_gz.json`
  - `ds_population_raw_gz_selective1.json`
  - `ds_population_raw_tsv.json`
  - `ds_population_raw_tsv_selective1.json`
- `linkedService/`:
  - `ls_ablob_covidreportingsidsa.json`
  - `ls_adls_covidreportingsidsa.json`

And it produced:
- `build/adf_subset_report.json` showing counts (4 pipelines, 4 datasets, 2 linked services, no IRs/creds/dataflows) and no dynamic refs.

---

## Safe ARM template stripping (why and how)

After export, the workflow generates a safe deployable template by stripping infra-owned resources:

- `Microsoft.DataFactory/factories/linkedServices`
- `Microsoft.DataFactory/factories/managedVirtualNetworks`
- `Microsoft.DataFactory/factories/managedVirtualNetworks/managedPrivateEndpoints`
- `Microsoft.DataFactory/factories/globalparameters`
- `Microsoft.DataFactory/factories/credentials`
- `Microsoft.DataFactory/factories/integrationRuntimes`

`scripts/strip_arm_resources.py` also removes any `dependsOn` edges pointing to stripped resources to avoid deployment failures.

Finally, the workflow verifies that the safe template contains only expected ADF resource types (intended: pipelines/datasets).

---

## Prerequisites (to use this repo)

### Azure prerequisites
- An Azure subscription and a resource group 
- An Azure Data Factory instance 
- Azure AD application configured for GitHub Actions OIDC (federated credentials)

### GitHub secrets required
- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`

### GitHub environment (deployment gating)
- An environment named `dev` (the deploy job targets `environment: dev`)

### Tooling used by workflows
On GitHub-hosted Ubuntu runners:
- Node.js 20 (installed by workflow)
- Python 3 (used by staging/stripping scripts)
- `jq` (used to inspect ARM JSON)
- Azure CLI + `datafactory` extension

---

## Architecture (workflow-driven)

<img width="377" height="437" alt="image" src="https://github.com/user-attachments/assets/1966adf4-53d0-464d-8526-928c5fdc2fdf" />


---

## How to run locally (optional)

### Validate locally
```bash
npm install
FACTORY_ID="/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.DataFactory/factories/<factory>"
npm run build validate . "$FACTORY_ID"
```

### Stage subset + export ARM locally
```bash
python3 scripts/select_adf_subset.py deploy/manifests/release.json

FACTORY_ID="/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.DataFactory/factories/<factory>"
npm --prefix build run build -- export "adf_subset" "$FACTORY_ID" "ArmTemplate"
```

### Produce safe template locally
```bash
python3 scripts/strip_arm_resources.py \
  --in build/ArmTemplate/ARMTemplateForFactory.json \
  --out build/ArmTemplate/ARMTemplateForFactory.safe.json \
  --strip-type Microsoft.DataFactory/factories/linkedServices \
  --strip-type Microsoft.DataFactory/factories/managedVirtualNetworks \
  --strip-type Microsoft.DataFactory/factories/managedVirtualNetworks/managedPrivateEndpoints \
  --strip-type Microsoft.DataFactory/factories/globalparameters \
  --strip-type Microsoft.DataFactory/factories/credentials \
  --strip-type Microsoft.DataFactory/factories/integrationRuntimes
```

---

## Troubleshooting / gotchas

- **Dynamic references** (values starting with `@`) can’t be statically resolved; check `build/adf_subset_report.json` and include missing deps manually if needed.
- If export fails due to missing credentials/IRs, consider enabling `includeCredentials` / `includeIntegrationRuntimes` and ensuring those folders exist in the repo.
- The “safe template” stripping is intentionally strict to avoid overwriting infra-managed resources in DEV.
