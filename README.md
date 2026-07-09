# AWS URL Redirect and Rewrite Platform

This project deploys a CloudFront + Lambda@Edge redirect engine that reads an Apache-style rule file from S3. It supports multiple domains in one config file and can process `Redirect`, `RedirectMatch`, `RewriteCond`, and `RewriteRule` directives at the edge.

## Project Layout

```text
terraform/
  main.tf
  variables.tf
  outputs.tf
  iam.tf
  cloudfront.tf
  lambda.tf
  s3.tf
  route53.tf
src/
  handler.py
  parser.py
  matcher.py
  compiler.py
  compiler_handler.py
  config_loader.py
  response.py
edge/
  fast_path.js.tftpl
tools/
  compile_fastpath.py
tests/
  test_parser.py
  test_matcher.py
  test_rewrite_conditions.py
  test_redirect_response.py
examples/
  redirects.conf
```

## Rule Configuration

The redirect file is stored in S3, versioned, and remains the source of truth. A compiler Lambda runs when the config object is created or updated and syncs fast-path-safe rules into CloudFront KeyValueStore. Lambda@Edge still loads the full S3 config as the fallback engine, so unsupported rules continue to work.

Example:

```apache
<VirtualHost example.com>
  ServerAlias www.example.com

  Redirect 301 /old-page /new-page
  RedirectMatch 301 ^/blog/(.*)$ /articles/$1
  Redirect 302 /promo/* /campaigns/$1 [QSD]

  RewriteCond %{HTTP_HOST} ^example\.com$ [NC]
  RewriteCond %{REQUEST_URI} ^/legacy
  RewriteRule ^/legacy/(.*)$ https://www.example.com/new/$1 [R=301,L]
</VirtualHost>

<VirtualHost anotherdomain.com>
  Redirect 302 / https://www.anotherdomain.com/home
</VirtualHost>
```

Supported behavior includes:

- `Redirect` prefix rules, including wildcard `*` captures.
- `RedirectMatch` regex rules with `$1` style captures.
- `RewriteCond` attached to the immediately following `RewriteRule`.
- `RewriteRule` redirects with `[R=301]`, `[R=302]`, `[R=307]`, or `[R=308]`.
- Internal rewrites when a `RewriteRule` does not include an `R` flag.
- Query handling flags: `[QSD]`, `[QSA]`, and `[QSPreserve]`.
- Case-insensitive matching with `[NC]`.
- Condition chaining with `[OR]`.
- Conditions for `%{HTTP_HOST}`, `%{REQUEST_URI}`, `%{REQUEST_PATH}`, `%{QUERY_STRING}`, `%{REQUEST_SCHEME}`, `%{HTTPS}`, `%{REQUEST_METHOD}`, `%{HTTP:Header-Name}`, and `%{HTTP_HEADER_NAME}`.

## Local Testing

Run the unit tests:

```bash
python3 -m unittest discover -s tests
```

The tests cover config parsing, virtual host matching, redirects, wildcard and regex captures, rewrite conditions, query-string behavior, internal rewrites, and CloudFront response generation.

## Terraform Setup

These steps deploy the S3 config bucket, CloudFront KeyValueStore, S3-triggered config compiler Lambda, Lambda@Edge fallback engine, CloudFront Function fast path, CloudFront distribution, IAM permissions, CloudWatch log groups, optional Route 53 DNS records, and the sample redirect config.

Terraform does not manage CloudFront alternate domain names or viewer certificates. It creates the distribution with the default CloudFront certificate, then ignores future changes to `aliases` and `viewer_certificate` so you can manage those settings in the AWS Console.

### Prerequisites

- Terraform `1.5.0` or newer.
- AWS CLI credentials with permission to manage S3, IAM, Lambda, CloudFront, CloudWatch Logs, KMS, SQS, CloudWatch alarms, and optionally Route 53.
- An ACM certificate in `us-east-1` if you plan to add custom domains to CloudFront in the AWS Console.
- Route 53 hosted zone IDs if you want Terraform to create DNS records. Leave them out if you want to manage DNS manually.

Lambda@Edge must be created in `us-east-1`, and CloudFront only accepts ACM certificates from `us-east-1`. The Terraform config uses a `us-east-1` provider alias for the Lambda function even if `aws_region` points regional resources elsewhere.

### 1. Configure AWS Credentials

Use your normal AWS profile or environment variables:

```bash
aws configure sso
aws sts get-caller-identity
```

Or with a named profile:

```bash
export AWS_PROFILE=your-profile-name
aws sts get-caller-identity
```

### 2. Create Terraform Variables

Create `terraform/terraform.tfvars`:

```hcl
aws_region       = "us-east-1"
environment_name = "prod"
config_key       = "redirects.conf"

# Production hardening: allow absolute redirects only to these hosts.
allowed_redirect_hosts = [
  "www.example.com",
  "example.com",
]

# Fallback redirects stay uncached unless every fallback rule depends only on path, query, and host.
redirect_cache_ttl_seconds = 0
fastpath_redirect_cache_ttl_seconds = 600

# Leave empty when DNS is managed manually in the AWS Console.
route53_zone_ids = {}
```

If you want Terraform to create Route 53 DNS records, add hosted zone IDs for the names you will later attach to CloudFront in the AWS Console:

```hcl
route53_zone_ids = {
  "example.com"       = "Z1111111111111"
  "www.example.com"   = "Z1111111111111"
  "anotherdomain.com" = "Z2222222222222"
}
```

If another process will upload the redirect config, add:

```hcl
manage_sample_config_object = false
```

### 3. Initialize Terraform

```bash
cd terraform
terraform init
terraform validate
```

### 4. Review the Plan

```bash
terraform plan
```

Confirm that the plan includes:

- One versioned S3 bucket for redirect configuration, encrypted with a customer-managed KMS key.
- One private S3 bucket for CloudFront fallback origin content, encrypted with a customer-managed KMS key.
- One S3 access log bucket for S3 and CloudFront logs.
- An IAM role trusted by `lambda.amazonaws.com` and `edgelambda.amazonaws.com`.
- A published Lambda version for Lambda@Edge.
- A CloudFront distribution with access logging, security response headers, a viewer-request CloudFront Function fast path, and an origin-request Lambda@Edge fallback association.
- A CloudFront KeyValueStore populated by the S3-triggered config compiler Lambda.
- A default CloudFront viewer certificate. Custom aliases and certificates are intentionally left for AWS Console management.
- KMS keys, CloudWatch alarms, and a dead-letter queue for the config compiler Lambda.
- Route 53 records only for names included in `route53_zone_ids`.

### 5. Apply

```bash
terraform apply
```

CloudFront deployment can take several minutes. When the apply finishes, note these outputs:

```bash
terraform output cloudfront_distribution_domain
terraform output config_bucket_name
terraform output lambda_edge_qualified_arn
terraform output fastpath_key_value_store_arn
terraform output config_compiler_lambda_name
```

### 6. Add Domains and Certificates in the AWS Console

After Terraform creates the CloudFront distribution, manage custom domains and certificates directly in AWS:

1. Open ACM in `us-east-1` and request or import a certificate for your domains.
2. Validate the certificate.
3. Open CloudFront, select the distribution from `terraform output cloudfront_distribution_id`, then edit the distribution settings.
4. Add your alternate domain names, such as `example.com` and `www.example.com`.
5. Select your ACM certificate as the custom SSL certificate and save the distribution.
6. Create DNS records that point your domains to `terraform output cloudfront_distribution_domain`. You can do this in Route 53, another DNS provider, or Terraform if you filled in `route53_zone_ids`.

Future Terraform applies will not remove console-managed CloudFront aliases or viewer certificate settings.

### 7. Test the Distribution

Before DNS fully points at CloudFront, you can test a domain by sending the expected `Host` header:

```bash
curl -I \
  -H "Host: example.com" \
  "https://$(terraform output -raw cloudfront_distribution_domain)/old-page"
```

You should see the configured redirect status and a `Location` header.

### 8. Update Redirect Rules

Terraform uploads `examples/redirects.conf` by default. For Terraform Cloud, update redirects through the `redirect-config` branch and merge to `main` only after the GitHub validation workflow passes. Terraform Cloud can then run from `main` and update the S3 object through the `aws_s3_object.sample_config` resource.

When Terraform writes the config object to S3, the bucket notification invokes the config compiler Lambda. By default, Terraform also invokes the compiler synchronously after it writes `examples/redirects.conf`, which lets Terraform Cloud finish only after the fast-path KeyValueStore update has been attempted. Compatible rules are synced into CloudFront KeyValueStore for the fast path, while the full config remains available to Lambda@Edge fallback. If the config object already existed before this redesign was applied, run one Terraform apply after the S3 notification is in place to seed the KeyValueStore.

### 9. Destroy When Needed

For non-production test environments:

```bash
terraform destroy
```

By default, `force_destroy_buckets` is `false`, so Terraform will not delete non-empty buckets. Empty the buckets first or set `force_destroy_buckets = true` only for disposable environments.

## Hybrid Fast Path

The platform uses a hybrid fast path plus fallback design:

- S3 Apache-style config remains the source of truth.
- A compiler Lambda parses the config on S3 object create/update events.
- Fast-path-safe rules are written to CloudFront KeyValueStore.
- A CloudFront Function runs on `viewer-request` and evaluates the fast-path rules directly at the edge.
- Lambda@Edge runs on `origin-request` as the full Apache-style fallback engine for anything the compiler skips.

Fast-path rules can include practical `RewriteCond` usage for:

- `%{HTTP_HOST}`
- `%{REQUEST_URI}`
- `%{REQUEST_PATH}` / `%{URI}`
- `%{QUERY_STRING}`
- `%{REQUEST_SCHEME}` / `%{SCHEME}` / `%{HTTPS}`
- `%{REQUEST_METHOD}`
- `%{HTTP:Header-Name}` / `%{HTTP_HEADER_NAME}`
- `[NC]`, `[OR]`, regex matches, exact matches, simple negation, `-z`, and `-n`

The compiler stops fast-path compilation for a virtual host at the first unsupported rule. This preserves Apache rule order: rules after a fallback-only rule are evaluated by Lambda@Edge instead of being moved ahead of it.

Inspect the split locally before uploading a config:

```bash
python3 tools/compile_fastpath.py examples/redirects.conf
```

The output shows fast-path host keys, fast rule count, fallback rule count, and diagnostics explaining why any rule stayed on Lambda@Edge.

## CloudFront Caching

Fast-path redirects are returned by the CloudFront Function, avoiding Lambda@Edge entirely. Fallback redirects generated by Lambda@Edge can still be cached by CloudFront because Lambda runs on `origin-request`.

The fallback cache key includes:

- Request path
- Query string
- A trusted internal `x-redirect-host` value stamped by the CloudFront Function
- A generated internal `x-redirect-edge-token` header that lets Lambda@Edge trust that host value

Fallback redirect response caching defaults to disabled:

```hcl
redirect_cache_ttl_seconds = 0
```

Keep it at `0` unless every fallback rule depends only on path, query string, and host. Fast-path redirects avoid Lambda@Edge and can advertise client/proxy caching separately:

```hcl
fastpath_redirect_cache_ttl_seconds = 600
```

To make Terraform Cloud wait for the fast-path compiler after it writes the config object, leave this enabled:

```hcl
invoke_compiler_after_config_apply = true
```

This does not replace the S3 event trigger. It makes Terraform Cloud perform a deterministic compiler invocation as part of the apply, which reduces the short window where a first request can miss CloudFront KeyValueStore and fall through to Lambda@Edge.

## Troubleshooting CloudFront 503 Lambda@Edge Errors

If CloudFront returns `503 ERROR` with a message that the Lambda function is invalid or does not have the required permissions, check these items first. Fast-path redirects should not invoke Lambda@Edge. A 503 on a rule that should be fast-path usually means the rule was not compiled into KeyValueStore, the CloudFront Function was not deployed, or the request fell through to Lambda@Edge fallback.

1. Wait for CloudFront deployment to finish. In the CloudFront console, the distribution status should be `Deployed`. Lambda@Edge replication can take several minutes after a function or distribution update.
2. Confirm the default behavior has a `viewer-request` CloudFront Function association and an `origin-request` Lambda@Edge association using the numbered ARN from `terraform output lambda_edge_qualified_arn`. The Lambda ARN must end with a version number like `:1`, not `$LATEST` or an alias.
3. Confirm the Lambda function is in `us-east-1`. Lambda@Edge requires the function to live in US East (N. Virginia).
4. Confirm the Lambda execution role trust policy allows both `lambda.amazonaws.com` and `edgelambda.amazonaws.com`. The role name is available from `terraform output lambda_execution_role_name`.
5. Confirm the Lambda@Edge service-linked roles exist in IAM: `AWSServiceRoleForLambdaReplicator` and `AWSServiceRoleForCloudFrontLogger`. AWS normally creates these automatically when the edge association is created or updated.
6. Check the Lambda@Edge error logs in CloudWatch. The logs are written in the AWS Region where the edge function ran, not always `us-east-1`. In CloudFront, open the distribution, go to Monitoring, then the Lambda@Edge errors view, and choose the function log region. Invalid response logs commonly appear under `/aws/cloudfront/LambdaEdge/<distribution-id>`.

Useful commands:

```bash
terraform -chdir=terraform output cloudfront_distribution_id
terraform -chdir=terraform output lambda_edge_qualified_arn
terraform output fastpath_key_value_store_arn
terraform output config_compiler_lambda_name
terraform -chdir=terraform output lambda_execution_role_name
```

If the CloudFront behavior points at the wrong Lambda ARN, run `terraform apply` again and wait for the distribution to return to `Deployed`. Terraform will keep your console-managed aliases and certificate because `aliases` and `viewer_certificate` are ignored.

## Troubleshooting No Redirect Rule Matched

If every domain returns `No redirect rule matched this request.` even though the S3 config is correct, the fallback Lambda is probably not seeing the original visitor host. The CloudFront Function stamps two internal request headers before fallback:

- `x-redirect-host`, containing the original domain
- `x-redirect-edge-token`, containing a generated trust token

Both headers must be forwarded to the origin-request Lambda through the CloudFront cache policy. Terraform manages this in `terraform/cloudfront.tf`. After changing this policy, run `terraform apply` and wait for the CloudFront distribution status to return to `Deployed`.

You can temporarily set `enable_diagnostic_headers = true` while testing. Fast-path redirects return `x-redirect-engine: cloudfront-function`; fallback redirects return `x-redirect-engine: lambda-edge`.

If the service-linked roles are missing, create them once in IAM or with these AWS CLI commands:

```bash
aws iam create-service-linked-role --aws-service-name replicator.lambda.amazonaws.com
aws iam create-service-linked-role --aws-service-name logger.cloudfront.amazonaws.com
```

If either command says the role already exists, that part is already fine.

## GitHub Actions Config Validation

The repository includes a workflow at `.github/workflows/validate-redirect-config.yml` that validates the Apache-style redirect config without uploading anything to AWS. Terraform Cloud remains responsible for applying the S3 object from `main`.

Recommended branch flow:

1. Make redirect config edits on the `redirect-config` branch.
2. Push the branch. The validation workflow runs on push.
3. Open a pull request into `main`. The same validation workflow runs on the pull request.
4. Merge only after `Validate Apache redirect config` passes.
5. Let Terraform Cloud apply from `main`; Terraform updates S3, and the S3 event invokes the compiler Lambda.

The workflow performs these checks:

- Checks out the repository.
- Runs `python tools/validate_redirect_config.py examples/redirects.conf --github-annotations --summary-json`.
- Fails the run if the Apache-style config has syntax or security-policy errors.
- Emits warnings for rules that are valid but remain on Lambda@Edge fallback instead of CloudFront Function fast path.
- Runs the full unit test suite and Python compile checks.
- Runs `terraform fmt`, `terraform validate`, Checkov, and Trivy config scanning.

Optional GitHub repository variables:

- `REDIRECT_CONFIG_PATH`: override the config path if you move it from `examples/redirects.conf`.
- `ALLOWED_REDIRECT_HOSTS`: comma-separated absolute redirect destination hosts to enforce in CI.

To make GitHub enforce this before merges to `main`, open the repository settings in GitHub and add a branch protection or ruleset for `main` that requires pull requests and requires the `Validate Apache redirect config` status check to pass.

No GitHub Actions AWS role, OIDC trust, or S3 upload permission is required for this workflow.

## Production Security Notes

The production defaults intentionally prefer safety over convenience:

- Lambda@Edge fallback redirect caching defaults to `0` because fallback rules can depend on headers, scheme, or method.
- Absolute redirect targets must use HTTPS.
- Protocol-relative targets, control characters, dynamic redirect hostnames, oversized configs, invalid regexes, and risky nested regex repetition are rejected.
- `allowed_redirect_hosts` should be populated for production so config authors cannot introduce arbitrary external redirect destinations.
- CloudFront uses a generated internal token header so Lambda@Edge only trusts `x-redirect-host` when it was stamped by the CloudFront Function.
- S3 buckets use public-access blocks, versioning, lifecycle rules, access logging, KMS encryption for application buckets, and explicit denies for insecure transport.
- Lambda and compiler logs use KMS-encrypted CloudWatch log groups with 365-day retention by default.
- The config compiler has reserved concurrency, X-Ray tracing, and an encrypted dead-letter queue.

Checkov and Trivy are part of the CI gate. The documented scan exceptions cover items that are intentionally out of scope or incompatible with the service shape: WAF is excluded by request, Lambda@Edge does not support several Lambda controls, CloudFront custom certificates are console-managed, the log delivery bucket requires ACL/SSE-S3 behavior, and cross-region S3 replication/geographic restrictions are business-continuity choices rather than redirect-engine requirements.

For local scans, use the helper script instead of installing Checkov into your global Python environment:

```bash
tools/run_security_scans.sh
```

The helper creates `.venv-checkov` and pins Checkov with its compatible `packaging` dependency. This avoids the common warning where Checkov requires `packaging<24.0` but another local tool upgraded `packaging` to a newer version.

## Updating Redirects

Validate and inspect the fast/fallback split locally before opening a pull request:

```bash
python3 tools/validate_redirect_config.py examples/redirects.conf --summary-json
python3 tools/compile_fastpath.py examples/redirects.conf
```

Commit redirect changes to the `redirect-config` branch and open a pull request to `main`. GitHub Actions validates the config on both push and pull request. After the pull request merges, Terraform Cloud should apply from `main` and write `examples/redirects.conf` to S3.

The S3 object change triggers the compiler Lambda, and Terraform Cloud also invokes the compiler during apply when `invoke_compiler_after_config_apply` is enabled. The compiler updates CloudFront KeyValueStore for fast-path-compatible rules. Lambda@Edge fallback also reads the same S3 config and refreshes warm runtimes based on `config_check_interval_seconds`.

Check which engine handled a redirect with:

```bash
curl -I https://example.com/old-page
```

Diagnostic response headers are disabled by default. To temporarily expose which engine handled a redirect, set:

```hcl
enable_diagnostic_headers = true
```

A fast redirect then includes `x-redirect-engine: cloudfront-function`. A slower fallback redirect includes `x-redirect-engine: lambda-edge`.

## Adding a Domain

1. Add or validate a certificate for the domain in ACM `us-east-1`.
2. In the CloudFront console, add the domain as an alternate domain name and select the certificate.
3. Create or update DNS to point the domain at the CloudFront distribution domain.
4. Add a matching `<VirtualHost domain.com>` block to the S3 redirect config.
5. Run `python3 tools/compile_fastpath.py examples/redirects.conf` to confirm the fast/fallback split.
6. Commit the updated redirect config to the `redirect-config` branch, open a pull request to `main`, and let Terraform Cloud apply after the validation workflow passes and the pull request is merged.

## Lambda@Edge Notes

- Lambda@Edge functions must be published numbered versions, so Terraform attaches `aws_lambda_function.redirect_engine.qualified_arn`.
- Lambda@Edge functions must be created in `us-east-1`.
- Lambda@Edge does not support custom environment variables, so Terraform embeds S3 config settings into the deployment zip as `settings.py`.
- CloudFront alternate domain names and viewer certificates are intentionally console-managed. Terraform ignores changes to those two distribution settings.
- CloudFront Function handles fast-path-safe rules from CloudFront KeyValueStore before Lambda@Edge is invoked.
- Lambda@Edge is attached to `origin-request` as the full fallback engine and for fallback redirect caching.
- CloudFront requires an origin even when Lambda returns redirects directly. This project creates a private S3 fallback origin that is separate from the private config bucket.
- Logs for Lambda@Edge executions appear in the AWS region where the edge invocation runs. Terraform creates the primary function log group in `us-east-1`; replica log groups may be created by AWS in other regions.

## Fallback Behavior

By default, unmatched requests return a `404` response directly from Lambda:

```hcl
fallback_behavior    = "not_found"
fallback_status_code = 404
```

To let unmatched requests pass to the private fallback S3 origin:

```hcl
fallback_behavior = "pass_through"
```
