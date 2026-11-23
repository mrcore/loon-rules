import argparse
import re
from pathlib import Path
from urllib.request import urlopen


REPOSITORY = "https://github.com/v2fly/domain-list-community"
SOURCE = "https://raw.githubusercontent.com/v2fly/domain-list-community/master/data/anthropic"
OUTPUT = Path(__file__).resolve().parents[1] / "Claude.list"
RULE_TYPES = {
    "domain": "DOMAIN-SUFFIX",
    "full": "DOMAIN",
    "keyword": "DOMAIN-KEYWORD",
}
LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
HOSTNAME = re.compile(rf"{LABEL}(?:\.{LABEL})*")
KEYWORD = re.compile(r"[a-z0-9_.-]+")


def convert(source: str) -> str:
    rules = set()

    for line_number, line in enumerate(source.splitlines(), start=1):
        entry, _, _ = line.partition("#")
        fields = entry.split()
        if not fields:
            continue

        rule, *metadata = fields
        if any(not re.fullmatch(r"[@&][a-zA-Z0-9_.-]+", field) for field in metadata):
            raise ValueError(f"line {line_number}: invalid rule metadata: {entry.strip()}")

        kind, separator, value = rule.partition(":")
        if not separator:
            kind, value = "domain", kind
        if kind not in RULE_TYPES:
            raise ValueError(f"line {line_number}: unsupported GeoSite rule type: {kind}")

        value = value.lower()
        pattern = KEYWORD if kind == "keyword" else HOSTNAME
        if not pattern.fullmatch(value) or len(value) > 253:
            raise ValueError(f"line {line_number}: invalid {kind} rule: {value}")
        rules.add(f"{RULE_TYPES[kind]},{value}")

    if not rules:
        raise ValueError("GeoSite source contains no rules")

    header = [
        "#",
        "#!name=Claude",
        "#!desc=从 GeoSite Anthropic 清单生成的 Loon 分流规则。",
        f"#!homepage={REPOSITORY}/blob/master/data/anthropic",
        "#!tag=Claude, GeoSite",
        f"#!support={len(rules)}",
        "# Copyright (c) 2018-2019 V2Ray",
        f"# Upstream license: {REPOSITORY}/blob/master/LICENSE",
        "#",
    ]
    return "\n".join([*header, *sorted(rules), ""])


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert GeoSite Anthropic rules to Loon syntax.")
    parser.add_argument("--source-file", type=Path, help="Use a local GeoSite file instead of GitHub.")
    parser.add_argument("--output", type=Path, default=OUTPUT, help="Path to the generated Loon list.")
    args = parser.parse_args()

    try:
        if args.source_file:
            source = args.source_file.read_text(encoding="utf-8-sig")
        else:
            with urlopen(SOURCE, timeout=30) as response:
                source = response.read().decode("utf-8-sig")
        output = convert(source)
        args.output.write_bytes(output.encode("utf-8"))
    except (OSError, ValueError) as error:
        parser.exit(1, f"Claude rule sync failed: {error}\n")


if __name__ == "__main__":
    main()
