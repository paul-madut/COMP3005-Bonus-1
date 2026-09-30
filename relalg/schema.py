"""Attributes, schemas, and name resolution (decisions 7, 9, 10)."""

from __future__ import annotations

from dataclasses import dataclass

from .errors import NameError, SchemaError, Span
from .values import Type, compatible


@dataclass(frozen=True)
class Attribute:
    """Attribute identity is (qualifier, name, type) - decision 7."""

    qualifier: str
    name: str
    type: Type

    def display(self) -> str:
        return f"{self.qualifier}.{self.name}"


@dataclass(frozen=True)
class Schema:
    """An ordered list of uniquely named qualified attributes.

    Invariant: every (qualifier, name) pair is unique. Constructors assert it.
    """

    attrs: tuple[Attribute, ...]

    def __post_init__(self) -> None:
        seen: set[tuple[str, str]] = set()
        for a in self.attrs:
            key = (a.qualifier, a.name)
            if key in seen:
                raise SchemaError(
                    f"duplicate attribute {a.display()} in schema",
                )
            seen.add(key)

    def __len__(self) -> int:
        return len(self.attrs)

    @property
    def arity(self) -> int:
        return len(self.attrs)

    def names(self) -> list[str]:
        return [a.name for a in self.attrs]

    def display(self) -> list[str]:
        return [a.display() for a in self.attrs]

    def types(self) -> list[Type]:
        return [a.type for a in self.attrs]

    def resolve(self, qualifier: str | None, name: str, span: Span | None) -> Attribute:
        """Resolve an (optionally qualified) reference (decision 7).

        A qualified reference must match exactly one attribute. An unqualified
        reference must match exactly one attribute *name*, otherwise it is an
        ambiguity error listing the candidates.
        """
        if qualifier is not None:
            matches = [a for a in self.attrs if a.qualifier == qualifier and a.name == name]
            if not matches:
                raise NameError(f"no attribute {qualifier}.{name}", span)
            return matches[0]
        matches = [a for a in self.attrs if a.name == name]
        if not matches:
            raise NameError(f"no attribute named {name!r}", span)
        if len(matches) > 1:
            cands = ", ".join(a.display() for a in matches)
            raise SchemaError(
                f"ambiguous attribute name {name!r} (could be {cands}); qualify it",
                span,
            )
        return matches[0]


def union_compatible(left: Schema, right: Schema, span: Span | None) -> None:
    """Union compatibility (decision 9): same arity, same names, compatible types."""
    if left.arity != right.arity:
        raise SchemaError(
            f"union compatibility: {left.arity} attributes vs {right.arity}",
            span,
        )
    for la, ra in zip(left.attrs, right.attrs, strict=True):
        if la.name != ra.name:
            raise SchemaError(
                f"union compatibility: attribute {la.name!r} vs {ra.name!r} "
                f"(names must match in order)",
                span,
            )
        if not compatible(la.type, ra.type):
            raise SchemaError(
                f"union compatibility: {la.display()} is {la.type.value} "
                f"but {ra.name} is {ra.type.value}",
                span,
            )


def concat(left: Schema, right: Schema, span: Span | None) -> Schema:
    """Concatenate two schemas (times / join). Rejects collisions (decision 8)."""
    seen: set[tuple[str, str]] = {(a.qualifier, a.name) for a in left.attrs}
    for a in right.attrs:
        if (a.qualifier, a.name) in seen:
            raise SchemaError(
                f"duplicate attribute {a.display()} after combining relations "
                f"(same qualifier and name on both sides); use rename first",
                span,
            )
    return Schema(left.attrs + right.attrs)
