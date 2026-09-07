<#
Pushes terraform-generated OIDC client secrets (Keycloak assigns these
itself -- they are NOT random values seed.py can generate, per
identity/credentials-inventory.yaml's `seed: false` entries) into Vault.
Called from wait-and-apply.ps1 right after `terraform apply`.

Two groups, both `seed: false`, both need this same treatment:
- the 2 human-SSO *web* client secrets (ops-dashboard-web, qms-web)
- the 11 machine-identity *svc* client secrets (keycloak-machine-identities.tf's
  `machine_identity_client_secrets` output), one per workload that does its
  own token-introspection self-check on boot

Found live: without the web-secret half, ops-dashboard's OIDC callback 500s
(CredentialUnavailableError) even after a fully successful terraform apply.
Found live a second time: without the svc-secret half, EVERY showcase
service hangs identically at startup (run_startup_self_check() blocks on a
missing Vault secret) -- containers show "Up" but never bind their port,
with no log output and no crash, because nothing had ever pushed these.

vault_path is NOT a fixed `rfq/{client_id}-client-secret` pattern -- found
live, 4 of the 11 (the agent workloads) use `rfq/agents/{client_id}`
instead, and hardcoding the flat pattern here silently pushed their real
secret to a path nothing reads, while seed.py kept clobbering the path the
agents actually read with a random value Keycloak then rejected (290+-restart
crash loop, zero log output pointing at why). credentials-inventory.yaml is
the single source of truth for vault_path per client_id; this script reads
it rather than re-deriving a naming convention.
#>

$ErrorActionPreference = "Stop"

$opsSecret = terraform output -raw ops_dashboard_web_client_secret
$qmsSecret = terraform output -raw qms_web_client_secret
$machineSecretsJson = terraform output -json machine_identity_client_secrets
$inventoryPath = Join-Path $PSScriptRoot "../../../identity/credentials-inventory.yaml"

Push-Location (Join-Path $PSScriptRoot "../../vault")
try {
    uv run --with pyyaml python -c "
import json
import sys
import yaml
from rfq_common.secrets import VaultAdmin

admin = VaultAdmin()
admin.put('rfq/ops-dashboard-web-client-secret', {'value': sys.argv[1]})
admin.put('rfq/qms-web-client-secret', {'value': sys.argv[2]})
print('pushed ops-dashboard-web-client-secret, qms-web-client-secret to Vault')

with open(sys.argv[4], encoding='utf-8') as f:
    inventory = yaml.safe_load(f)

# client_id = consumers[0] + '-svc' holds for every machine-identity entry
# (verified against every entry whose note mentions 'already provisions') --
# credentials-inventory.yaml has no client_id field of its own, so this is
# how consumers[] maps back to the terraform-generated client_id.
vault_path_by_client_id = {
    entry['consumers'][0] + '-svc': entry['vault_path']
    for entry in inventory.get('credentials', [])
    if 'already provisions' in (entry.get('note') or '') and entry.get('consumers')
}

machine_secrets = json.loads(sys.argv[3])
for client_id, secret in machine_secrets.items():
    path = vault_path_by_client_id.get(client_id, f'rfq/{client_id}-client-secret')
    admin.put(path, {'value': secret})
    print(f'pushed {path} to Vault ({client_id})')
" $opsSecret $qmsSecret $machineSecretsJson $inventoryPath
} finally {
    Pop-Location
}
