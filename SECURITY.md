# Security Model (NovaPact GCU v1)

## Authentication / Authorization
This API is intentionally designed to run behind an upstream security boundary:
- Reverse proxy / API gateway (NGINX, Envoy, Kong, Azure APIM, AWS ALB, etc.)
- Private network (VPN / VPC)
- Optional mTLS or JWT validation at the gateway

The GCU runtime focuses on:
- policy enforcement
- governance decisions (allow/deny/aborted/blocked)
- human-in-the-loop thresholds
- immutable audit artefacts