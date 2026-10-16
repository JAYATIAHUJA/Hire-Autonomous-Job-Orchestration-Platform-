# ADR-009: Dev object store is SeaweedFS, not MinIO

- Status: Accepted (2026-10-15)
- Plan: PLAN.md §20 item 3 listed MinIO.

## Context
MinIO's public Docker images (`minio/minio`, `minio/mc`, also on quay.io) can no longer be
pulled anonymously. A dev stack that only works on machines with a cached image is not a
one-command stack.

## Decision
Use SeaweedFS (`chrislusf/seaweedfs:4.00`, Apache-2.0) with its S3 gateway in `compose.yml`,
plus an `amazon/aws-cli` one-shot that creates the `hire-dev` bucket. The app only speaks S3
(`S3_ENDPOINT`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`), so production uses AWS S3 in ap-south-1 unchanged.

## Consequences
- No code depends on MinIO-specific APIs. Keep it that way: S3 API only.
