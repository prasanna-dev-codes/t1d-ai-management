"""Fetch only public CC0 PhysioCGM cgm.csv entries using bounded HTTP ranges."""

import argparse
import hashlib
import io
import json
import re
import urllib.request
import zipfile
from pathlib import Path

ARTICLE = "https://api.figshare.com/v2/articles/28136294"


class RemoteZip(io.RawIOBase):
    def __init__(self, url: str, size: int) -> None:
        self.url, self.size, self.position = url, size, 0

    def seekable(self) -> bool:
        return True

    def seek(self, offset: int, whence: int = 0) -> int:
        self.position = offset + (0 if whence == 0 else self.position if whence == 1 else self.size)
        if not 0 <= self.position <= self.size:
            raise ValueError("Invalid archive position")
        return self.position

    def tell(self) -> int:
        return self.position

    def read(self, size: int = -1) -> bytes:
        count = self.size - self.position if size < 0 else min(size, self.size - self.position)
        if not count:
            return b""
        if count > 4_000_000:
            raise ValueError("Refusing large archive read")
        end = self.position + count - 1
        req = urllib.request.Request(self.url, headers={"Range": f"bytes={self.position}-{end}"})
        with urllib.request.urlopen(req, timeout=30) as response:
            expected = f"bytes {self.position}-{end}/{self.size}"
            if response.status != 206 or response.headers.get("Content-Range") != expected:
                raise ValueError("Server did not honor exact range; refusing full download")
            data = bytes(response.read(count + 1))
        if len(data) != count:
            raise ValueError("Incomplete range")
        self.position += count
        return data


def fetch(output: Path) -> dict[str, object]:
    with urllib.request.urlopen(ARTICLE, timeout=30) as response:
        metadata = json.load(response)
    if metadata["license"]["name"] != "CC0" or metadata["version"] != 1:
        raise ValueError("Dataset license changed; review before download")
    output.mkdir(parents=True, exist_ok=True)
    entries = []
    for item in metadata["files"]:
        if not item["name"].endswith("_raw.zip"):
            continue
        if not re.fullmatch(r"c[12]s0[1-5]_raw\.zip", item["name"]):
            raise ValueError("Unexpected source filename")
        subject = item["name"].removesuffix("_raw.zip")
        if re.fullmatch(r"c[12]s0[1-5]", subject) is None:
            raise ValueError("Unexpected participant archive name")
        target = output / (subject + ".csv")
        if not target.exists():
            with zipfile.ZipFile(RemoteZip(item["download_url"], item["size"])) as archive:
                choices = [
                    i for i in archive.infolist() if Path(i.filename).name.lower() == "cgm.csv"
                ]
                if len(choices) != 1 or choices[0].file_size > 4_000_000:
                    raise ValueError("Unexpected CGM entry")
                target.write_bytes(archive.read(choices[0]))
        raw = target.read_bytes()
        entries.append(
            {
                "file": target.name,
                "source_file_id": item["id"],
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
        print("Verified CGM file", len(entries), flush=True)
    result = {
        "doi": metadata["doi"],
        "version": metadata["version"],
        "license": metadata["license"],
        "entries": entries,
    }
    (output / "provenance.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = fetch(args.output)
    print("Completed", len(result["entries"]), "public CC0 glucose files")  # type: ignore[arg-type]
