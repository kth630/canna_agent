# Server record — mirae-agent-api

## Identity and lifecycle

| item | value |
|---|---|
| logical name | `mirae-agent-api` |
| purpose | Canna evaluation API test deployment target |
| provider | NAVER Cloud Platform (NCP) |
| platform | VPC |
| operating system | Ubuntu 24.04 |
| specification | 2 vCPU / 4 GB memory / 10 GB disk |
| network placement | public subnet |
| public IP | assigned; value intentionally not recorded in the repository |
| ACG | configured; individual rules not yet verified in this record |
| SSH | user reports password-authenticated administrative connection is available; account and credentials are not recorded here |
| lifecycle | server created |
| application deployed | no |
| deployment verified | no |

## Intended application boundary

- Repository: `canna_agent`
- Initial service: 0-B evaluation API minimum vertical slice
- Intended entrypoint: `uvicorn canna.api:create_app --factory`
- External contract: `contracts/EVALUATION_API.md`
- Explicitly not connected: official product data, incoming holdings, DuckDB,
  Runtime View, HCX, Semantic/Execution Registry, or product/portfolio joins.

## Access and secret handling

The public IP value, SSH username, authentication material, passwords, NCP
access keys, registry credentials, and future application secrets must not be
placed in Git, provenance files, deployment images, or application logs. They
are managed through the approved connection and secret-injection environment.

## Deployment preflight status

| item | status |
|---|---|
| outbound Internet for package installation | unverified |
| application deployment | not started |
| process manager / automatic restart | not selected |
| API exposure | undecided: direct port `8000` vs reverse proxy on `80`/`443` |
| API inbound ACG source range | undecided |
| Nginx or another reverse proxy | not installed or configured |

For the initial deployment test, do not broaden the API ACG rule until the
chosen caller path is known. SSH access and API access must remain separate
rules.

## Event log

| date | event | result | evidence |
|---|---|---|---|
| 2026-08-30 | server created | completed | user-provided infrastructure facts |
| 2026-08-30 | deployment access facts recorded | completed | user-provided SSH and network facts; no credentials stored |
| TBD | Canna API deployment | not started | `DEPLOYMENT_VALIDATION.md` after execution |
