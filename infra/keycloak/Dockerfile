# Thin wrapper — adds only an identifying label on top of the upstream
# Keycloak image, no other changes. Runtime config lives in docker-compose.yml.
FROM quay.io/keycloak/keycloak:26.0

LABEL org.opencontainers.image.title="eaop-infra-keycloak" \
      org.opencontainers.image.description="Local Keycloak sandbox — dev IdP for the ops-dashboard's human SSO login (test/prod target: Entra)"
