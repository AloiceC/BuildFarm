from __future__ import annotations

import os
import sys
import urllib.request

CFUG_PUB = "https://pub.flutter-io.cn"
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
    # Pub packages may use the reachable CFUG mirror, but Flutter SDK/engine
    # artifacts stay on the official storage source. A shallow HEAD probe of a
    # mirror index cannot validate multi-gigabyte SDK archive integrity.
    use_cfug_pub = probe(CFUG_PUB)
    pub = CFUG_PUB if use_cfug_pub else OFFICIAL_PUB
    pub_label = "cfug" if use_cfug_pub else "official"
    storage = OFFICIAL_STORAGE

    write_output("pub_hosted_url", pub)
    write_output("flutter_storage_base_url", storage)
    write_output("mirror", pub_label)
    print(f"MIRROR pub={pub_label} storage=official status=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
