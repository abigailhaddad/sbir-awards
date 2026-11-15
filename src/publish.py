"""Upload out/awards.parquet, out/report.json and out/README.md (the dataset card) to Hugging Face.

    HF_TOKEN=... python src/publish.py
    python src/publish.py --force      # upload even if SBIR.gov's file hasn't changed

Skips, with a message and exit 0, when HF_TOKEN is empty, or when the dataset already holds a build of the same
SBIR.gov file (same Last-Modified). Reads the parquet back after uploading and checks the row count.
"""
import json
import os
import sys
import urllib.request

import pandas as pd

REPO = "abigailhaddad/sbir-awards"
FILES = ["awards.parquet", "report.json", "README.md"]


def main():
    token = os.environ.get("HF_TOKEN", "").strip()
    if not token:
        print("HF_TOKEN is empty: skipping the Hugging Face upload. Add the HF_TOKEN repository secret "
              "(a token with write access to abigailhaddad/sbir-awards) to publish.")
        return
    report = json.load(open("out/report.json"))
    try:
        with urllib.request.urlopen(f"https://huggingface.co/datasets/{REPO}/resolve/main/report.json", timeout=60) as r:
            old = json.load(r)
    except Exception as e:
        print(f"no report.json on Hugging Face yet ({e}); uploading")
        old = {}
    if "--force" not in sys.argv and old.get("current_file_last_modified") == report["current_file_last_modified"]:
        print(f"SBIR.gov's file is unchanged ({report['current_file_last_modified']}); nothing to upload")
        return
    if old.get("rows") and report["rows"] < old["rows"]:
        sys.exit(f"STOP: new build has {report['rows']} rows, fewer than the {old['rows']} on Hugging Face")
    from huggingface_hub import CommitOperationAdd, HfApi
    api = HfApi(token=token)
    api.create_repo(REPO, repo_type="dataset", exist_ok=True)
    ops = [CommitOperationAdd(path_in_repo=f, path_or_fileobj=f"out/{f}") for f in FILES]
    api.create_commit(repo_id=REPO, repo_type="dataset", operations=ops,
                      commit_message=f"Build of SBIR.gov file last modified {report['current_file_last_modified']}: "
                                     f"{report['rows']:,} rows")
    back = pd.read_parquet(f"https://huggingface.co/datasets/{REPO}/resolve/main/awards.parquet",
                           columns=["record_id"], storage_options={"Authorization": f"Bearer {token}"})
    if len(back) != report["rows"] or not back.record_id.is_unique:
        sys.exit(f"STOP: read back {len(back)} rows from Hugging Face, expected {report['rows']}")
    print(f"uploaded and read back {len(back):,} rows")


if __name__ == "__main__":
    main()
