"""Real artifact storage — writes spoke-agent output bytes to S3 so `ArtifactRef.location`
points at a genuine, downloadable object instead of a fabricated string (Phase 1's stub
agents built an `ArtifactRef` with an `s3://daf-artifacts/...` location that was never
actually written to any bucket).
"""

from __future__ import annotations

from typing import Protocol

import boto3

from daf.models.common import ArtifactRef
from daf.models.enums import ArtifactKind, ArtifactLocationKind


class ArtifactWriterProtocol(Protocol):
    def write(self, trace_id: str, filename: str, content: str, kind: ArtifactKind, artifact_id: str) -> ArtifactRef: ...


class S3ArtifactStore:
    """Real `ArtifactWriterProtocol` implementation backed by an S3 bucket
    (Terraform-provisioned, name passed in via `ARTIFACT_BUCKET_NAME`)."""

    def __init__(self, bucket_name: str) -> None:
        self._bucket_name = bucket_name
        self._s3 = boto3.client("s3")

    def write(self, trace_id: str, filename: str, content: str, kind: ArtifactKind, artifact_id: str) -> ArtifactRef:
        key = f"{trace_id}/{filename}"
        self._s3.put_object(
            Bucket=self._bucket_name,
            Key=key,
            Body=content.encode("utf-8"),
            ContentType="application/json" if filename.endswith(".json") else "text/plain",
        )
        return ArtifactRef(
            artifactId=artifact_id,
            location=f"s3://{self._bucket_name}/{key}",
            locationKind=ArtifactLocationKind.S3_URI,
            kind=kind,
        )

    def read_text(self, location: str) -> str:
        """`location` is an `s3://bucket/key` URI as produced by `write()`."""
        _, _, rest = location.partition("s3://")
        bucket, _, key = rest.partition("/")
        obj = self._s3.get_object(Bucket=bucket, Key=key)
        return obj["Body"].read().decode("utf-8")
