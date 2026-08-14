# Serverless Migration: Lambda + S3 + CloudFront — Design Spec

**Date:** 2026-08-14
**Context:** Personal/hobby project — move hosting from local-only Docker Compose to a
cost-conscious AWS serverless deployment, reachable at a custom domain over HTTPS.
Local Docker Compose dev workflow is kept unchanged.

---

## 1. Goals & Non-Goals

**Goals:**
- Host the existing FastAPI backend on Lambda, static React frontend on S3, both served
  through one CloudFront distribution at `nwt.shrikantlavhate.in`.
- Persist data on S3 instead of a local JSON file.
- Lock the Lambda Function URL down so only this CloudFront distribution can invoke it —
  random direct hits to the Function URL bounce with a 403 at the edge, at zero cost.
- Stay inside (or very near) the AWS Free Tier / a $5/month budget. No mandatory WAF.

**Non-Goals:**
- No change to app features, UI, or API contract.
- No multi-region / multi-edge performance optimization — single user, based in India,
  accessing a US-hosted app; CloudFront's job here is TLS + custom domain, not latency.
- No migration off the existing "one JSON blob, load-modify-save" persistence model —
  just relocating it to S3 and re-partitioning per user (see §3).

---

## 2. Architecture

```
Browser (nwt.shrikantlavhate.in)
        |
        v
   Route 53 (A/alias) -> CloudFront distribution (PriceClass_100, ACM cert, TLS1.2_2021)
        |
        +-- default behavior "/*"     -> S3 origin (frontend bucket) via S3 OAC
        |                                  403/404 custom-error -> 200 /index.html (SPA)
        |
        +-- behavior "/api/*"         -> Lambda Function URL origin via Lambda OAC (SigV4)
                                            AuthType: AWS_IAM
                                            Resource policy: only principal
                                            cloudfront.amazonaws.com with
                                            AWS:SourceArn = this distribution's ARN
                                            |
                                            v
                                     Lambda (FastAPI + Mangum, reserved concurrency 2,
                                     no VPC — direct internet egress for Yahoo Finance /
                                     mfapi.in / exchange-rate APIs)
                                            |
                                            v
                                     S3 data bucket (one JSON object per user)
```

Frontend and API share one origin domain, so the frontend keeps calling relative
`/api/...` paths exactly as it does today (`frontend/src/api.js` already defaults
`VITE_API_URL` to `''`). No CORS needed in production; the existing CORS middleware in
`main.py` stays as-is for local dev and is simply unreachable/unnecessary in prod.

---

## 3. Backend: FastAPI on Lambda

**Approach:** Add `backend/lambda_handler.py` exposing `handler = Mangum(app)`. Mangum
translates the Lambda Function URL request/response payload (same shape as API Gateway
HTTP API v2) to/from ASGI, so `main.py`, `auth.py`, `models.py`, `stock_service.py`,
`exchange_service.py`, and `nav_service.py` need **no changes**. The same `app` object
runs under `uvicorn` (Docker) and under Mangum (Lambda).

**Networking:** Lambda is *not* placed in a VPC. Default Lambda networking already has
outbound internet access, which is all the external API calls (Yahoo Finance, mfapi.in,
exchange rate APIs) need. Attaching a VPC would require a NAT Gateway to keep that
internet access, which costs far more than the $5/month budget — so this is a deliberate
choice, not an oversight.

**Runtime settings:** Python 3.12 runtime, 512 MB memory, **25s timeout**, **reserved
concurrency: 2**. The 25s Lambda timeout is deliberately kept below CloudFront's default
30s origin-response timeout, so a slow upstream call (Yahoo Finance/mfapi.in) causes
Lambda to return its own error first rather than racing CloudFront's timeout.

---

## 4. Storage: `database.py` → S3, one object per user

**Problem:** `database.py` currently does `load_data()` / `save_data()` against a single
local `data.json` file containing every user's data. Lambda has no local persistent
disk, so this needs to move to S3 — and a single shared blob would mean every request
(from any user) reads and rewrites the *entire* dataset, which is unnecessary contention
even at small scale.

**Fix:** Repartition storage to one S3 object per user:
`s3://<data-bucket>/users/{username}.json`, holding that user's account record plus all
their assets/liabilities/bank_accounts/insurances/mutual_funds/equities/snapshots/goal —
i.e. today's blob shape, scoped to one user instead of all users. This is a small change
from the current pattern (still "load this user's blob, mutate, save it back"), and
removes cross-user contention entirely.

- Reads: `GetObject(users/{username}.json)`.
- Writes: conditional `PutObject` with `If-Match: <etag from the read>`; on
  `PreconditionFailed` (412), re-read and retry once. Guards against two concurrent
  requests from the same logged-in user clobbering each other. Not a concern across
  users since they now live in separate objects.
- `get_user_by_id(user_id)` in the current `database.py` is dead code (confirmed unused
  anywhere in `main.py`) and is dropped rather than ported, since a username-keyed store
  has no cheap way to look up by id and nothing needs it.
- A `STORAGE_BACKEND` env var (`local` default, `s3` in Lambda) selects the
  implementation inside `database.py`. `docker-compose` sets nothing and keeps using the
  existing local-file code path untouched, satisfying "keep Docker Compose for local
  dev" with zero behavior change there.
- The Lambda execution role's S3 permissions are scoped to `GetObject`/`PutObject` on
  `arn:aws:s3:::<data-bucket>/users/*` only — least privilege, no bucket-wide access,
  no `ListBucket`/`DeleteObject` needed by the app.

---

## 5. Locking down the Lambda Function URL

- Lambda Function URL `AuthType: AWS_IAM` (not `NONE`) — anonymous requests are rejected
  by Lambda itself before billing for an invocation.
- A CloudFront **Origin Access Control** (`OriginAccessControlOriginType: lambda`,
  `SigningProtocol: sigv4`, `SigningBehavior: always`) attached to the `/api/*` origin,
  so CloudFront signs every request to the Function URL with its own identity.
- A Lambda resource policy (`AWS::Lambda::Permission`,
  `Action: lambda:InvokeFunctionUrl`, `Principal: cloudfront.amazonaws.com`,
  `SourceArn: <this distribution's ARN>`) — scoped to this one distribution, not
  "any CloudFront distribution in the account."
- Net effect: hitting the raw `*.lambda-url.*.on.aws` URL directly gets a 403 with no
  Lambda invocation (and therefore no cost) at all. Only requests signed by this specific
  distribution succeed.

---

## 6. Frontend: S3 + CloudFront

- Frontend bucket is fully private; reachable only via CloudFront through a standard S3
  Origin Access Control + bucket policy restricting `s3:GetObject` to this distribution's
  ARN.
- SPA client-side routing (React Router) is preserved via a CloudFront custom error
  response: `403 -> 200, /index.html` (a private S3 bucket returns 403, not 404, for a
  missing key) — replacing nginx's `try_files $uri /index.html` from the Docker setup.
- Deploy script builds `frontend/` with Vite (`VITE_API_URL` left empty, same as local
  dev) and syncs `frontend/dist/` to the bucket, then issues a CloudFront invalidation.

---

## 7. Domain & TLS

- ACM certificate for `nwt.shrikantlavhate.in`, issued in `us-east-1` (required region
  for any CloudFront custom-domain cert), `ValidationMethod: DNS`, with
  `DomainValidationOptions` pointed at the existing Route 53 hosted zone for
  `shrikantlavhate.in` — CloudFormation writes the validation record and waits for
  issuance automatically; no manual DNS steps.
- CloudFront distribution `Aliases: [nwt.shrikantlavhate.in]`, viewer certificate = that
  ACM cert, `MinimumProtocolVersion: TLSv1.2_2021`, `SSLSupportMethod: sni-only`.
- Route 53 `A` record (alias) for `nwt.shrikantlavhate.in` -> the CloudFront
  distribution, in the same stack.
- The Hosted Zone ID for `shrikantlavhate.in` is a required CloudFormation parameter
  (not looked up automatically) — find it with
  `aws route53 list-hosted-zones-by-name --dns-name shrikantlavhate.in`.

---

## 8. Cost controls

- **Reserved concurrency: 2** on the Lambda function — hard cap on simultaneous
  executions, bounding worst-case cost from any traffic spike, retry storm, or abuse.
- **AWS Budget, $5/month**, emailing at 80% and 100% of threshold. Implemented via AWS
  Budgets' native `SubscriptionType: EMAIL` subscriber, not a separate SNS topic —
  a third implementation-time refinement (alongside the two noted below): functionally
  equivalent, one fewer resource, and it skips the "confirm subscription" click an SNS
  email subscription would otherwise require. The notification email is a
  CloudFormation parameter, not hardcoded, since this template lives in a public GitHub
  repo.
- **CloudFront PriceClass_100** (US/Canada/Europe edge locations only) — cheapest class;
  acceptable because CloudFront's role here is TLS termination + custom domain, not
  edge caching for a geographically distributed audience.
- **No WAF.** Deliberately excluded: the IAM-authenticated Function URL + OAC trust
  boundary already rejects unauthenticated/direct traffic before any Lambda invocation
  or meaningful cost is incurred. Adding WAF would introduce a mandatory recurring
  charge to defend against a threat this design already closes for free. Can be added
  later if traffic patterns ever warrant it.

---

## 9. Infrastructure as Code

Plain **AWS CloudFormation** (per your preference — not Terraform/CDK/SAM), split as:

- `infra/template.yaml` — single stack containing: data bucket, frontend bucket + OAC +
  bucket policy, Lambda function + execution role + reserved concurrency + Function URL
  + resource policy, Lambda-origin OAC, CloudFront distribution (two origins/behaviors,
  custom error response, aliases, ACM cert), ACM certificate, Route 53 record, AWS Budget
  with a native EMAIL subscriber (see §8 — no separate SNS topic).
- Parameters: `NotificationEmail`, `HostedZoneId`, `DomainName` (default
  `nwt.shrikantlavhate.in`), `ReservedConcurrency` (default `2`).
- `infra/deploy.sh` — builds the Lambda deployment package (Python deps installed for
  the Lambda Linux runtime), uploads it to an artifacts location, runs
  `aws cloudformation deploy`, builds the frontend, syncs it to the frontend bucket, and
  invalidates the CloudFront cache. You run this yourself after `aws configure`/SSO
  login; nothing here runs `terraform apply`/`aws cloudformation deploy` on your behalf
  automatically.

---

## 10. Explicitly out of scope

- No changes to app features, business logic, or API contract.
- No CI/CD pipeline — deploys are manual via `infra/deploy.sh`, matching "you deploy it
  yourself."
- No multi-user data migration tooling — this is a fresh deployment; the existing local
  `data/data.json` (if any) is not auto-imported into S3. (The app's existing
  `/api/export` and `/api/import` JSON backup feature can be used manually to move data
  if needed.)
- No autoscaling/production-hardening beyond what's described — reserved concurrency of
  2 means at most 2 concurrent requests; a burst beyond that queues/throttles rather than
  scaling out, which is an accepted trade-off for a single-user personal app.
