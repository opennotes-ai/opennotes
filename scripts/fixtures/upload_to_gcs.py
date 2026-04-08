"""Upload a Greenmask dump directory to GCS."""
import sys
from pathlib import Path

from google.cloud import storage


def upload_dump(dump_dir: str, timestamp: str, bucket_name: str) -> None:
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    dump_path = Path(dump_dir)

    for file_path in dump_path.rglob("*"):
        if file_path.is_file():
            blob_name = f"fixtures/{timestamp}/{file_path.relative_to(dump_path)}"
            blob = bucket.blob(blob_name)
            blob.upload_from_filename(str(file_path))
            print(f"  Uploaded: {blob_name}")

    print(f"Upload complete: gs://{bucket_name}/fixtures/{timestamp}/")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: upload_to_gcs.py <dump_dir> <timestamp> <bucket_name>")
        sys.exit(1)
    upload_dump(sys.argv[1], sys.argv[2], sys.argv[3])
