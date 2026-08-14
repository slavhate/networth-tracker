import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("STORAGE_BACKEND", "s3")
os.environ.setdefault("DATA_BUCKET", "test-networth-data")
os.environ.setdefault("SECRET_KEY", "test-secret")

import boto3  # noqa: E402
import pytest  # noqa: E402
from moto import mock_aws  # noqa: E402

import s3_storage  # noqa: E402

BUCKET = os.environ["DATA_BUCKET"]


@pytest.fixture
def s3_bucket():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        s3_storage._client = None  # force a fresh client bound to the mock
        yield client
