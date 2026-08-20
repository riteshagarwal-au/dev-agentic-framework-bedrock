# state-backend

Provisions the S3 bucket that backs Terraform remote state for one environment/target, per
Requirement 7.4 and the source design's "S3-native Terraform state locking" decision.

## What this module creates

- An S3 bucket (`<bucket_name_prefix>-<environment>-<account_id>`) with:
  - Versioning enabled.
  - Default encryption using AWS KMS (`aws:kms`), either a key this module creates
    (`create_kms_key = true`, the default) or an existing key ARN you pass in
    (`create_kms_key = false` + `kms_key_arn`).
  - All public access blocked (`aws_s3_bucket_public_access_block`) and bucket-owner-enforced
    object ownership (no ACLs).
  - A bucket policy that denies any request made over plain HTTP and denies any `PutObject` that
    isn't using KMS server-side encryption.
- Optionally, a dedicated KMS key + alias (`create_kms_key = true`).

## What this module does NOT create — native state locking

Terraform's S3 backend supports **native state locking** (`use_lockfile = true`, Terraform
>= 1.11) using S3 conditional writes (`If-None-Match`) to create a `.tflock` companion object next
to the state object. This replaces the older DynamoDB-lock-table pattern — **no DynamoDB table is
created by this module, and none is needed.**

`use_lockfile` is a setting in the **consumer's** `backend "s3" { ... }` block, not an attribute of
the S3 bucket resource itself, so there's nothing to configure on the bucket side beyond what's
already here (versioning + encryption + a bucket that allows conditional writes, which S3 supports
natively). See the example below.

## One backend per environment/target

Instantiate this module once per environment/target (e.g. `dev`, `staging`, `prod`, or a
per-deploy-target name), each with a distinct `environment` value. Each instance gets its own
bucket, so state for different environments/targets can never collide even if multiple root
modules point at buckets from the same AWS account.

```hcl
module "state_backend_dev" {
  source      = "../../modules/state-backend"
  environment = "dev"
}

module "state_backend_prod" {
  source      = "../../modules/state-backend"
  environment = "prod"
}
```

If two root modules share the *same* environment's bucket (e.g. this bootstrap module's own state
vs. the main DAF root module's state), give each a distinct `key` in their respective backend
blocks — the bucket is shared per environment, but state paths within it are not.

## Usage

This module has no backend block of its own (bootstrapping problem: you can't put a Terraform
state bucket's own state into a bucket that doesn't exist yet). Apply it once with local state (or
via a separate one-time bootstrap process), then point every other root module's backend at the
bucket it creates:

```hcl
module "state_backend" {
  source      = "../../modules/state-backend"
  environment = var.environment
}
```

```hcl
output "backend_config_example" {
  value = module.state_backend.backend_config_example
}
```

Then, in the consuming root module (e.g. `infra/`), configure the backend using the values from
this module's outputs:

```hcl
terraform {
  backend "s3" {
    bucket       = "daf-tfstate-dev-123456789012"
    key          = "daf-phase1/dev/terraform.tfstate"
    region       = "ap-southeast-2"
    kms_key_id   = "arn:aws:kms:ap-southeast-2:123456789012:key/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
    encrypt      = true
    use_lockfile = true
  }
}
```

Backend blocks cannot reference variables or module outputs directly (Terraform limitation), so in
practice these values are supplied via `terraform init -backend-config=...` or a generated
`backend.hcl` file per environment, using the values from this module's `bucket_name` /
`kms_key_arn` outputs.

## Inputs

| Name | Description | Type | Default |
|---|---|---|---|
| `environment` | Environment/target name; one bucket per value. | `string` | n/a (required) |
| `bucket_name_prefix` | Prefix for the generated bucket name. | `string` | `"daf-tfstate"` |
| `create_kms_key` | Whether to create a dedicated KMS key. | `bool` | `true` |
| `kms_key_arn` | Existing KMS key ARN to use when `create_kms_key = false`. | `string` | `null` |
| `kms_key_deletion_window_in_days` | KMS key deletion window. | `number` | `30` |
| `force_destroy` | Allow bucket destroy even if non-empty. Keep `false` outside scratch environments. | `bool` | `false` |
| `tags` | Extra tags merged onto all resources. | `map(string)` | `{}` |

## Outputs

| Name | Description |
|---|---|
| `bucket_name` | Name of the state bucket. |
| `bucket_arn` | ARN of the state bucket. |
| `kms_key_arn` | ARN of the KMS key used for bucket encryption. |
| `kms_key_id` | Key ID of the KMS key created by this module (`null` if reusing an existing key). |
| `backend_config_example` | Rendered example `backend "s3" {}` block, including `use_lockfile = true`, for consumers. |

## Requirements traceability

- Requirement 7.4: "...GitHub Actions SHALL run `terraform apply` using the S3-backed remote state
  with native state locking" — this module is the S3-backed remote state referenced by that
  requirement; the native-locking behavior itself is enabled by consumers via `use_lockfile = true`
  in their backend block (see above).
