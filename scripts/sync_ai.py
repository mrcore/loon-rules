import argparse
import io
import sys
import tarfile
from pathlib import Path
from urllib.request import urlopen

from sync_claude import HOSTNAME, KEYWORD, REPOSITORY, RULE_TYPES


ARCHIVE_URL = "https://codeload.github.com/v2fly/domain-list-community/tar.gz/refs/heads/master"
ARCHIVE_ROOT = "domain-list-community-master"
CATEGORIES = ("category-ai-!cn", "category-ai-ru")
# GeoSite's !cn category also includes overseas endpoints of Chinese services.
EXCLUDED_CATEGORIES = ("category-ai-cn", "bytedance-ai-!cn", "manus", "youmind")
EXCLUDED_DOMAINS = {
    "dify.ai",
    "kimi.ai",
    "lovart.ai",
    "minimax.io",
    "moonshot.ai",
    "notegpt.io",
    "qoder.com",
    "sider.ai",
    "tapnow.ai",
    "tripo3d.ai",
}
OUTPUT = Path(__file__).resolve().parents[1] / "AI.list"
EXTRA_DOMAINS = (
    "character.ai",
    "lovable.dev",
    "runway.com",
    "runwayml.com",
    "suno.ai",
    "suno.com",
    "udio.com",
)
EXCLUDED_ATTRIBUTES = {"ads", "telemetry"}


def read_text(archive, path):
    member = archive.getmember(f"{ARCHIVE_ROOT}/{path}")
    if not member.isfile():
        raise ValueError(f"expected a text file at {path}")
    with archive.extractfile(member) as source:
        return source.read().decode("utf-8-sig")


def expand(archive, name, parents=()):
    if name in parents:
        raise ValueError(f"circular GeoSite include: {' -> '.join((*parents, name))}")

    for number, line in enumerate(read_text(archive, f"data/{name}").splitlines(), 1):
        fields = line.partition("#")[0].split()
        if not fields:
            continue

        rule, *metadata = fields
        attributes = {tag[1:] for tag in metadata if tag.startswith("@")}
        kind, separator, value = rule.partition(":")
        if not separator:
            kind, value = "domain", kind

        if kind == "include":
            required = {tag for tag in attributes if not tag.startswith("-")}
            excluded = {tag[1:] for tag in attributes if tag.startswith("-")}
            for child in expand(archive, value, (*parents, name)):
                child_attributes = child[2]
                if required <= child_attributes and excluded.isdisjoint(child_attributes):
                    yield child
        else:
            yield kind, value, attributes, f"{name}:{number}"


def convert(archive):
    excluded_suffixes = {"cn", *EXCLUDED_DOMAINS}
    excluded_hosts = set()
    excluded_keywords = set()
    for category in EXCLUDED_CATEGORIES:
        for kind, value, _, _ in expand(archive, category):
            if kind == "domain":
                excluded_suffixes.add(value.lower())
            elif kind == "full":
                excluded_hosts.add(value.lower())
            elif kind == "keyword":
                excluded_keywords.add(value.lower())

    def is_excluded(kind, value):
        if kind == "keyword":
            return any(value in host for host in excluded_suffixes | excluded_hosts) or any(
                value in keyword or keyword in value for keyword in excluded_keywords
            )
        return (
            value in excluded_hosts
            or any(value == suffix or value.endswith(f".{suffix}") for suffix in excluded_suffixes)
            or any(keyword in value for keyword in excluded_keywords)
            or (kind == "domain" and any(
                host.endswith(f".{value}") for host in excluded_suffixes | excluded_hosts
            ))
        )

    rules = set()
    for category in CATEGORIES:
        for kind, value, attributes, location in expand(archive, category):
            if attributes & EXCLUDED_ATTRIBUTES:
                continue
            if kind == "regexp":
                print(f"Skipped GeoSite regexp at {location}: Loon has no hostname regex rule.", file=sys.stderr)
                continue
            if kind not in RULE_TYPES:
                raise ValueError(f"{location}: unsupported GeoSite rule type: {kind}")

            value = value.lower()
            pattern = KEYWORD if kind == "keyword" else HOSTNAME
            if not pattern.fullmatch(value) or len(value) > 253:
                raise ValueError(f"{location}: invalid {kind} rule: {value}")
            if not is_excluded(kind, value):
                rules.add(f"{RULE_TYPES[kind]},{value}")

    if not rules:
        raise ValueError("GeoSite AI categories contain no supported rules")
    rules.update(f"DOMAIN-SUFFIX,{domain}" for domain in EXTRA_DOMAINS if not is_excluded("domain", domain))

    header = [
        "#",
        "#!name=AI",
        "#!desc=非中国 AI 服务的 Loon 分流规则，包含 GeoSite AI 分类和补充域名。",
        "#!homepage=https://github.com/mrcore/loon-rules",
        "#!raw-url=https://raw.githubusercontent.com/mrcore/loon-rules/main/AI.list",
        "#!tag=AI, GeoSite",
        f"#!support={len(rules)}",
        *(f"# Source: {REPOSITORY}/blob/master/data/{category}" for category in CATEGORIES),
        "#",
        *(f"# {line}".rstrip() for line in read_text(archive, "LICENSE").splitlines()),
        "#",
    ]
    return "\n".join([*header, *sorted(rules), ""])


def main():
    parser = argparse.ArgumentParser(description="Combine GeoSite AI categories into one Loon list.")
    parser.add_argument("--source-archive", type=Path, help="Use a local GeoSite tar.gz snapshot.")
    parser.add_argument("--output", type=Path, default=OUTPUT, help="Path to the generated list.")
    args = parser.parse_args()

    try:
        if args.source_archive:
            data = args.source_archive.read_bytes()
        else:
            with urlopen(ARCHIVE_URL, timeout=30) as response:
                data = response.read()
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            output = convert(archive)
        args.output.write_bytes(output.encode("utf-8"))
    except (KeyError, OSError, ValueError, tarfile.TarError) as error:
        parser.exit(1, f"AI rule sync failed: {error}\n")


if __name__ == "__main__":
    main()
