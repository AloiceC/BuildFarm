from __future__ import annotations

import os
import sys
import urllib.request

CFUG_PUB = "https://pub.flutter-io.cn"
CFUG_STORAGE = "https://storage.flutter-io.cn"
OFFICIAL_PUB = "https://pub.dev"
OFFICIAL_STORAGE = "https://storage.googleapis.com"


def probe(url: str) -> bool:
    req = urllib.request.Request(
        url,
        method="HEAD",
        headers={"User-Agent": "AloiceC-BuildFarm-v1"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            return 200 <= response.status < 400
    except Exception:
        return False


def write_output(name: str, value: str) -> None:
    output = os.environ.get("GITHUB_OUTPUT")
    if not output:
        raise RuntimeError("GITHUB_OUTPUT is not available")
    with open(output, "a", encoding="utf-8") as handle:
        handle.write(f"{name}={value}\n")


def main() -> int:
    use_cfug = probe(f"{CFUG_STORAGE}/flutter_infra_release/releases/releases_linux.json") and probe(CFUG_PUB)
    if use_cfug:
        pub = CFUG_PUB
        storage = CFUG_STORAGE
        label = "cfug"
    else:
        pub = OFFICIAL_PUB
        storage = OFFICIAL_STORAGE
        label = "official"

    write_output("pub_hosted_url", pub)
    write_output("flutter_storage_base_url", storage)
    write_output("mirror", label)
    print(f"MIRROR flutter={label} status=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
