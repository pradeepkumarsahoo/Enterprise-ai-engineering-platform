# Tagging check · every cloud resource

> Run `0cac2cb2da` · tag policy v1.0 · inventory `inventory` · provider `mock`. The agent proposes; the owning team approves; nothing here writes a tag.

## Summary

18 resources checked against tag policy v1.0: 9 compliant, 8 tag proposals (5 waiting for the owning team, 3 with no team that could be established). Unallocated in Oct 2026: $10,332; approving the proposals would allocate $6,603 of it.

- Resources checked: **18**, compliant: **9**
- Proposals: **8** · waiting for the owning team: 5 · no team established: 3 · approved: 0 · rejected: 0
- Unallocated in Oct 2026: $10,332; the proposals would allocate $6,603 of it

## Proposals

| Proposal | Resource | Set | Remove | Confidence | Approver team | Monthly cost | Allocation today → after | Status |
|---|---|---|---|---|---|---:|---|---|
| `TAG-partner-gateway-egress` | partner-gateway-egress | `team=Commerce` | — | team: high | Commerce | $5,939 | Commerce → Commerce | proposed |
| `TAG-platform-logging` | platform-logging | `shared=true` | — | shared: medium | Platform | $5,938 | Platform → Platform | proposed |
| `TAG-shared-nat-gateway` | shared-nat-gateway | `team=Platform`, `env=prod`, `shared=true` | — | team: medium, env: medium, shared: high | Platform | $3,000 | Unallocated → Platform | proposed |
| `TAG-loyalty-cache` | loyalty-cache | `team=Loyalty`, `env=prod` | `Environment`, `Team` | team: high, env: high | Loyalty | $2,415 | Unallocated → Loyalty | proposed |
| `TAG-membership-api-alb` | membership-api-alb | `team=Membership & Identity`, `service=membership-api` | — | team: high, service: medium | Membership & Identity | $1,188 | Unallocated → Membership & Identity | proposed |
| `TAG-search-indexer-nodes` | search-indexer-nodes | `env=prod` | — | env: medium | — | $3,122 | Unallocated → Unallocated | needs owner |
| `TAG-dev-test-vm-7` | dev-test-vm-7 | `env=dev` | — | env: medium | — | $606 | Unallocated → Unallocated | needs owner |
| `TAG-old-promo-bucket` | old-promo-bucket | `env=prod` | — | env: medium | — | — | Unallocated → Unallocated | needs owner |

## Every resource

| Resource | Account | Tags today | Compliant | Issues |
|---|---|---|---|---|
| commerce-staging-nodes | 222222222222 | `team=Commerce`, `env=staging` | yes | — |
| dev-test-vm-7 | 222222222222 | none | no | no team tag; no env tag |
| loyalty-cache | 111111111111 | `Team=loyalty`, `Environment=Production` | no | no team tag; no env tag; non-canonical tag key(s) Environment, Team |
| loyalty-ledger-db | 111111111111 | `team=Loyalty`, `service=loyalty-ledger`, `env=prod` | yes | — |
| membership-api-alb | 111111111111 | `env=prod` | no | no team tag; production resource with no service tag |
| membership-api-nodes | 111111111111 | `team=Membership & Identity`, `service=membership-api`, `env=prod` | yes | — |
| membership-db | 111111111111 | `team=Membership & Identity`, `service=membership-api`, `env=prod` | yes | — |
| membership-orphan-volumes | 111111111111 | `team=Membership & Identity`, `env=prod` | no | production resource with no service tag |
| notification-worker-nodes | 111111111111 | `team=Platform`, `service=notification-worker`, `env=prod` | yes | — |
| old-promo-bucket | 111111111111 | `Owner=ana.smith` | no | no team tag; no env tag |
| order-service-db | 111111111111 | `team=Commerce`, `service=order-service`, `env=prod` | yes | — |
| order-service-nodes | 111111111111 | `team=Commerce`, `service=order-service`, `env=prod` | yes | — |
| partner-gateway-egress | 111111111111 | `service=partner-gateway`, `env=prod` | no | no team tag |
| platform-logging | 111111111111 | `team=Platform`, `service=shared-logging`, `env=prod` | no | shared infrastructure with no shared=true tag; service tag shared-logging is not in the catalogue |
| platform-sandbox-cluster | 222222222222 | `team=Platform`, `env=sandbox` | yes | — |
| promotion-engine-nodes | 111111111111 | `team=Loyalty`, `service=promotion-engine`, `env=prod` | yes | — |
| search-indexer-nodes | 111111111111 | none | no | no team tag; no env tag |
| shared-nat-gateway | 333333333333 | none | no | no team tag; no env tag; shared infrastructure with no shared=true tag |

## Could not establish

- The team of dev-test-vm-7: only Loyalty at low confidence (created by dana.dev of Loyalty (+1))
- The service of loyalty-cache: nothing found
- The service of membership-orphan-volumes: nothing found
- The team of old-promo-bucket: nothing found; the creator ana.smith is not in the team directory
- The service of old-promo-bucket: nothing found
- The team of search-indexer-nodes: only Commerce at low confidence (created by lee.dev of Commerce (+1))
- The service of search-indexer-nodes: nothing found

## Notes to owning teams (draft)

- **Commerce**: To Commerce: please review the proposed tags on partner-gateway-egress: set team=Commerce. partner-gateway-egress: team=Commerce (high confidence): service tag partner-gateway is owned by Commerce in the catalogue (+3); created by sam.owner of Commerce (+1). Your team decides, and applies approved tags through its own change process.
- **Loyalty**: To Loyalty: please review the proposed tags on loyalty-cache: set team=Loyalty, env=prod, remove Environment, Team. loyalty-cache: team=Loyalty (high confidence): tag Team=loyalty names team Loyalty (+3); created by dana.dev of Loyalty (+1). loyalty-cache: env=prod (high confidence): tag Environment=Production means prod (+3); account prod-main is prod (+2). loyalty-cache: $2,415 in Oct 2026, allocated to Unallocated today and to Loyalty with these tags. Your team decides, and applies approved tags through its own change process.
- **Membership & Identity**: To Membership & Identity: please review the proposed tags on membership-api-alb: set team=Membership & Identity, service=membership-api. membership-api-alb: team=Membership & Identity (high confidence): membership-api, which the name starts with, is owned by Membership & Identity (+2); created by ria.owner of Membership & Identity (+1). membership-api-alb: service=membership-api (medium confidence): the name membership-api-alb starts with catalogue service membership-api (+2). membership-api-alb: $1,188 in Oct 2026, allocated to Unallocated today and to Membership & Identity with these tags. Your team decides, and applies approved tags through its own change process.
- **Platform**: To Platform: please review the proposed tags on platform-logging: set shared=true; shared-nat-gateway: set team=Platform, env=prod, shared=true. platform-logging: shared=true (medium confidence): service tag shared-logging starts with shared- (+2). shared-nat-gateway: team=Platform (medium confidence): account network-hub is owned by Platform (+1); created by noor.lead of Platform (+1). shared-nat-gateway: env=prod (medium confidence): account network-hub is prod (+2). shared-nat-gateway: shared=true (high confidence): the name shared-nat-gateway starts with shared- (+2); account network-hub holds shared infrastructure (+2). shared-nat-gateway: $3,000 in Oct 2026, allocated to Unallocated today and to Platform with these tags. Your team decides, and applies approved tags through its own change process.

## Evidence

- **T1** dev-test-vm-7: env=dev (medium confidence): the name dev-test-vm-7 says dev (+2)
- **T2** loyalty-cache: team=Loyalty (high confidence): tag Team=loyalty names team Loyalty (+3); created by dana.dev of Loyalty (+1)
- **T3** loyalty-cache: env=prod (high confidence): tag Environment=Production means prod (+3); account prod-main is prod (+2)
- **T4** loyalty-cache: $2,415 in Oct 2026, allocated to Unallocated today and to Loyalty with these tags
- **T5** membership-api-alb: team=Membership & Identity (high confidence): membership-api, which the name starts with, is owned by Membership & Identity (+2); created by ria.owner of Membership & Identity (+1)
- **T6** membership-api-alb: service=membership-api (medium confidence): the name membership-api-alb starts with catalogue service membership-api (+2)
- **T7** membership-api-alb: $1,188 in Oct 2026, allocated to Unallocated today and to Membership & Identity with these tags
- **T8** old-promo-bucket: env=prod (medium confidence): account prod-main is prod (+2)
- **T9** partner-gateway-egress: team=Commerce (high confidence): service tag partner-gateway is owned by Commerce in the catalogue (+3); created by sam.owner of Commerce (+1)
- **T10** platform-logging: shared=true (medium confidence): service tag shared-logging starts with shared- (+2)
- **T11** search-indexer-nodes: env=prod (medium confidence): account prod-main is prod (+2)
- **T12** shared-nat-gateway: team=Platform (medium confidence): account network-hub is owned by Platform (+1); created by noor.lead of Platform (+1)
- **T13** shared-nat-gateway: env=prod (medium confidence): account network-hub is prod (+2)
- **T14** shared-nat-gateway: shared=true (high confidence): the name shared-nat-gateway starts with shared- (+2); account network-hub holds shared infrastructure (+2)
- **T15** shared-nat-gateway: $3,000 in Oct 2026, allocated to Unallocated today and to Platform with these tags
- **T16** 18 resources checked against tag policy v1.0: 9 compliant, 8 tag proposals (5 waiting for the owning team, 3 with no team that could be established). Unallocated in Oct 2026: $10,332; approving the proposals would allocate $6,603 of it

_Generated by Engineering Command Centre · use case 5 · tagging agent · synthetic data · Author: Pradeep Sahoo_
