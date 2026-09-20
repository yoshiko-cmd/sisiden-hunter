"""config/sisiden_media.yaml を読み込み、CMSモデル定義を提供する。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA_PATH = ROOT / "config" / "sisiden_media.yaml"
CONTENT_DIR = ROOT / "content"

SINGLE_REF = "ref:"
MULTI_REF = "refs:"


@dataclass(frozen=True)
class Property:
    name: str
    type: str
    label: str
    required: bool = False
    options: tuple[str, ...] = ()

    @property
    def is_single_ref(self) -> bool:
        return self.type.startswith(SINGLE_REF)

    @property
    def is_multi_ref(self) -> bool:
        return self.type.startswith(MULTI_REF)

    @property
    def is_ref(self) -> bool:
        return self.is_single_ref or self.is_multi_ref

    @property
    def ref_target(self) -> str | None:
        if self.is_multi_ref:
            return self.type[len(MULTI_REF):]
        if self.is_single_ref:
            return self.type[len(SINGLE_REF):]
        return None


@dataclass(frozen=True)
class Model:
    name: str
    label: str
    label_ja: str
    path: str
    noindex: bool
    properties: tuple[Property, ...]

    def get_property(self, name: str) -> Property | None:
        return next((p for p in self.properties if p.name == name), None)

    @property
    def required_properties(self) -> tuple[Property, ...]:
        return tuple(p for p in self.properties if p.required)

    @property
    def ref_properties(self) -> tuple[Property, ...]:
        return tuple(p for p in self.properties if p.is_ref)


@dataclass(frozen=True)
class Schema:
    site: dict[str, Any]
    models: dict[str, Model]
    validation: dict[str, Any]

    def model(self, name: str) -> Model:
        if name not in self.models:
            raise KeyError(f"未定義のモデルです: {name}")
        return self.models[name]

    def url_for(self, model_name: str, slug: str) -> str:
        base = self.site["base_url"].rstrip("/")
        return f"{base}/{self.model(model_name).path}/{slug}"


_cache: Schema | None = None


def load_schema(path: Path = SCHEMA_PATH, force_reload: bool = False) -> Schema:
    global _cache
    if _cache is not None and not force_reload:
        return _cache

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    models: dict[str, Model] = {}
    for model_name, spec in raw["models"].items():
        props = tuple(
            Property(
                name=prop_name,
                type=prop_spec["type"],
                label=prop_spec.get("label", prop_name),
                required=bool(prop_spec.get("required", False)),
                options=tuple(prop_spec.get("options", ())),
            )
            for prop_name, prop_spec in spec["properties"].items()
        )
        models[model_name] = Model(
            name=model_name,
            label=spec["label"],
            label_ja=spec["label_ja"],
            path=spec["path"],
            noindex=bool(spec.get("noindex", False)),
            properties=props,
        )

    for model in models.values():
        for prop in model.ref_properties:
            if prop.ref_target not in models:
                raise ValueError(
                    f"{model.name}.{prop.name} の参照先モデル "
                    f"'{prop.ref_target}' が定義されていません"
                )

    _cache = Schema(site=raw["site"], models=models, validation=raw.get("validation", {}))
    return _cache
