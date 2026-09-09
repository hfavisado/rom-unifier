from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Platform:
    id: str
    title: str
    media: str
    extensions: tuple[str, ...]
    canonical_extension: str
    aliases: tuple[str, ...]
    output: str
    dat: str | None = None
    dat_family: str | None = None
    remove_headers: tuple[str, ...] = ()
    preserve_extensions: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    normalizer: str | None = None
    playlist: bool = False


def load(path: str | Path) -> dict[str, Platform]:
    with Path(path).open("rb") as handle:
        raw = tomllib.load(handle)["platforms"]
    result = {}
    for ident, item in raw.items():
        result[ident] = Platform(
            id=ident,
            title=item["title"], media=item["media"],
            extensions=tuple(x.lower().lstrip(".") for x in item["extensions"]),
            canonical_extension=item["canonical_extension"].lower().lstrip("."),
            aliases=tuple(item.get("aliases", ())), output=item.get("output", ident),
            dat=item.get("dat"), dat_family=item.get("dat_family"),
            remove_headers=tuple(item.get("remove_headers", ())),
            preserve_extensions=tuple(item.get("preserve_extensions", ())),
            requires=tuple(item.get("requires", ())), normalizer=item.get("normalizer"),
            playlist=bool(item.get("playlist", False)),
        )
    return result
