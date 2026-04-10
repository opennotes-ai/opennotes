"""Download fixture dumps from GCS."""
import sys
from pathlib import Path

from google.cloud import storage


def download_fixture(bucket_name: str, timestamp: str = "latest") -> str:
    client = storage.Client()
    bucket = client.bucket(bucket_name)

    if timestamp == "latest":
        blobs = list(bucket.list_blobs(prefix="fixtures/"))
        if not blobs:
            print("Error: No fixtures found in GCS bucket", file=sys.stderr)
            sys.exit(1)
        timestamps = sorted({b.name.split("/")[1] for b in blobs if len(b.name.split("/")) > 2})
        if not timestamps:
            print("Error: No fixture timestamps found", file=sys.stderr)
            sys.exit(1)
        timestamp = timestamps[-1]
        print(f"Latest fixture: {timestamp}", file=sys.stderr)

    prefix = f"fixtures/{timestamp}/"
    blobs = list(bucket.list_blobs(prefix=prefix))
    if not blobs:
        print(f"Error: No fixture found for timestamp {timestamp}", file=sys.stderr)
        sys.exit(1)

    local_dir = f"/tmp/opennotes-fixture-{timestamp}"
    Path(local_dir).mkdir(parents=True, exist_ok=True)

    local_dir_resolved = Path(local_dir).resolve()
    for blob in blobs:
        relative = blob.name[len(prefix):]
        if not relative:
            continue
        local_path = (Path(local_dir) / relative).resolve()
        if not str(local_path).startswith(str(local_dir_resolved)):
            print(f"  Skipping suspicious path: {relative}", file=sys.stderr)
            continue
        local_path.parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(str(local_path))
        print(f"  Downloaded: {blob.name}", file=sys.stderr)

    print(local_dir)
    return local_dir


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: download_from_gcs.py <bucket_name> [timestamp]", file=sys.stderr)
        sys.exit(1)
    bucket_name = sys.argv[1]
    timestamp = sys.argv[2] if len(sys.argv) > 2 else "latest"
    download_fixture(bucket_name, timestamp)
