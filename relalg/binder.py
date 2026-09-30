"""The binder: parse tree -> bound plan (static checking before execution).

Every name, schema and type error is raised here, before a single tuple is
touched - so `select[Age>'30'](R)` is a type error even when R is empty.
The bound plan carries compiled predicates (closures over resolved attribute
indexes) so the executor does no name resolution at run time.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from . import nodes
from .catalog import Catalog
from .errors import NameError, SchemaError, Span
from .errors import TypeError as RATypeError
from .schema import Attribute, Schema, concat, union_compatible
from .values import Type, Value, compare, compatible

# A compiled predicate takes a row (tuple of Values) and answers a condition.
Predicate = Callable[[tuple[Value, ...]], bool]


@dataclass(frozen=True)
class BoundRelation:
    """A base relation: resolved schema and rows."""

    name: str
    schema: Schema
    rows: list[tuple[Value, ...]]
    span: Span


@dataclass(frozen=True)
class BoundSelect:
    cond: Predicate
    input: BoundNode
    span: Span


@dataclass(frozen=True)
class BoundProject:
    indexes: tuple[int, ...]
    input: BoundNode
    span: Span


@dataclass(frozen=True)
class BoundRename:
    """A rename produces a new schema; rows are unchanged."""

    schema: Schema
    input: BoundNode
    span: Span


@dataclass(frozen=True)
class BoundUnion:
    left: BoundNode
    right: BoundNode
    span: Span


@dataclass(frozen=True)
class BoundMinus:
    left: BoundNode
    right: BoundNode
    span: Span


@dataclass(frozen=True)
class BoundIntersect:
    left: BoundNode
    right: BoundNode
    span: Span


@dataclass(frozen=True)
class BoundTimes:
    left: BoundNode
    right: BoundNode
    span: Span


@dataclass(frozen=True)
class BoundJoin:
    cond: Predicate
    left: BoundNode
    right: BoundNode
    span: Span
    # Equi-join keys (left index, right index) when every conjunct of the
    # condition is `left-attr = right-attr`.  None for a pure theta join.
    # The default plan is the fused nested loop (decision 11); the hash join
    # is an alternative strategy the benchmark can select (plan Q6).
    equi_keys: tuple[tuple[int, int], ...] | None = None
    strategy: str = "nested"


BoundNode = (
    BoundRelation
    | BoundSelect
    | BoundProject
    | BoundRename
    | BoundUnion
    | BoundMinus
    | BoundIntersect
    | BoundTimes
    | BoundJoin
)


def schema_of(node: BoundNode) -> Schema:
    """The output schema of a bound node, computed bottom-up."""
    match node:
        case BoundRelation():
            return node.schema
        case BoundRename():
            return node.schema
        case BoundSelect():
            return schema_of(node.input)
        case BoundProject():
            s = schema_of(node.input)
            return Schema(tuple(s.attrs[i] for i in node.indexes))
        case BoundUnion() | BoundMinus() | BoundIntersect():
            return schema_of(node.left)
        case BoundTimes() | BoundJoin():
            return concat(schema_of(node.left), schema_of(node.right), node.span)
    raise AssertionError(f"unreachable: {node!r}")


def _equi_keys(
    cond: nodes.Cond, combined: Schema, left_arity: int
) -> tuple[tuple[int, int], ...] | None:
    """Collect cross-side equality conjuncts as hash-key pairs (plan Q6).

    Each pair is (left_index, right_index) in concatenated-row coordinates.
    Returns None when there are none at all (a pure theta join).  Non-equality
    conjuncts are fine: the hash join uses the equality keys as candidates and
    the full predicate still filters each candidate pair.
    """
    conjuncts: list[nodes.Cond] = []
    stack = [cond]
    while stack:
        c = stack.pop()
        if isinstance(c, nodes.And):
            stack.append(c.right)
            stack.append(c.left)
        else:
            conjuncts.append(c)
    keys: list[tuple[int, int]] = []
    for c in conjuncts:
        if not isinstance(c, nodes.Comparison) or c.op != "=":
            continue
        if not (isinstance(c.left, nodes.AttrRef) and isinstance(c.right, nodes.AttrRef)):
            continue
        a = combined.resolve(c.left.qualifier, c.left.name, c.left.span)
        b = combined.resolve(c.right.qualifier, c.right.name, c.right.span)
        i, j = combined.attrs.index(a), combined.attrs.index(b)
        if i < left_arity <= j:
            keys.append((i, j))
        elif j < left_arity <= i:
            keys.append((j, i))
    return tuple(keys) or None


def _describe(op: nodes.Operand) -> str:
    if isinstance(op, nodes.Literal):
        return repr(op.value)
    return f"{op.qualifier}.{op.name}" if op.qualifier else op.name


def _lit_type(v: Value) -> Type:
    return Type.STRING if isinstance(v, str) else Type.NUMBER


class Binder:
    """Binds a parse tree against the catalog; raises before any execution."""

    def __init__(self, catalog: Catalog) -> None:
        self._catalog = catalog

    def bind(self, query: nodes.Query) -> BoundNode:
        return self._expr(query.expr)

    # -- expressions -----------------------------------------------------------

    def _expr(self, node: nodes.Expr) -> BoundNode:
        match node:
            case nodes.Relation():
                return self._relation(node)
            case nodes.Select():
                inner = self._expr(node.input)
                cond = self._cond(node.cond, schema_of(inner))
                return BoundSelect(cond, inner, node.span)
            case nodes.Project():
                return self._project(node)
            case nodes.Rename():
                return self._rename(node)
            case nodes.Union() | nodes.Minus() | nodes.Intersect():
                left = self._expr(node.left)
                right = self._expr(node.right)
                union_compatible(schema_of(left), schema_of(right), node.span)
                cls = {
                    nodes.Union: BoundUnion,
                    nodes.Minus: BoundMinus,
                    nodes.Intersect: BoundIntersect,
                }[type(node)]
                return cls(left, right, node.span)  # type: ignore[return-value]
            case nodes.Times():
                left = self._expr(node.left)
                right = self._expr(node.right)
                # The collision check happens inside concat (decision 8).
                concat(schema_of(left), schema_of(right), node.span)
                return BoundTimes(left, right, node.span)
            case nodes.Join():
                left = self._expr(node.left)
                right = self._expr(node.right)
                left_schema = schema_of(left)
                schema = concat(left_schema, schema_of(right), node.span)
                cond = self._cond(node.cond, schema)
                keys = _equi_keys(node.cond, schema, len(left_schema.attrs))
                return BoundJoin(cond, left, right, node.span, keys)
        raise AssertionError(f"unreachable expression node {node!r}")

    def _relation(self, node: nodes.Relation) -> BoundRelation:
        if not self._catalog.has(node.name):
            raise NameError(f"no relation named {node.name!r}", node.span)
        return BoundRelation(
            node.name,
            self._catalog.schema(node.name),
            self._catalog.rows(node.name),
            node.span,
        )

    def _project(self, node: nodes.Project) -> BoundProject:
        inner = self._expr(node.input)
        schema = schema_of(inner)
        indexes: list[int] = []
        seen: set[tuple[str, str]] = set()
        for ref in node.attrs:
            attr = schema.resolve(ref.qualifier, ref.name, ref.span)
            key = (attr.qualifier, attr.name)
            if key in seen:
                raise SchemaError(f"duplicate output attribute {attr.display()}", ref.span)
            seen.add(key)
            indexes.append(schema.attrs.index(attr))
        return BoundProject(tuple(indexes), inner, node.span)

    def _rename(self, node: nodes.Rename) -> BoundRename:
        inner = self._expr(node.input)
        schema = schema_of(inner)
        if node.rel_name is not None:
            # rename[New](R): re-qualify every attribute with New.
            new_attrs = tuple(Attribute(node.rel_name, a.name, a.type) for a in schema.attrs)
            return BoundRename(Schema(new_attrs), inner, node.span)
        # rename[old->new, ...](R): rename the listed attributes.
        renamed: dict[tuple[str, str], str] = {}
        for old, new in node.columns:
            attr = schema.resolve(old.qualifier, old.name, old.span)
            renamed[(attr.qualifier, attr.name)] = new
        new_attrs = tuple(
            Attribute(a.qualifier, renamed.get((a.qualifier, a.name), a.name), a.type)
            for a in schema.attrs
        )
        return BoundRename(Schema(new_attrs), inner, node.span)

    # -- conditions ------------------------------------------------------------

    def _cond(self, node: nodes.Cond, schema: Schema) -> Predicate:
        """Compile a condition tree into one row predicate."""
        match node:
            case nodes.Comparison():
                return self._comparison(node, schema)
            case nodes.Not():
                child = self._cond(node.child, schema)
                return lambda row: not child(row)
            case nodes.And():
                left = self._cond(node.left, schema)
                right = self._cond(node.right, schema)
                return lambda row: left(row) and right(row)
            case nodes.Or():
                left = self._cond(node.left, schema)
                right = self._cond(node.right, schema)
                return lambda row: left(row) or right(row)
        raise AssertionError(f"unreachable condition node {node!r}")

    def _comparison(self, node: nodes.Comparison, schema: Schema) -> Predicate:
        """Compile one comparison against a row.

        Operands resolve to attribute indexes at bind time; literals are baked
        into the closure.  The declared column types are checked here (static
        checking), so `select[Age>'30'](R)` fails before execution.
        """
        left, right = node.left, node.right

        def resolve(op: nodes.Operand) -> tuple[int | None, Value | None, Type]:
            if isinstance(op, nodes.Literal):
                return None, op.value, _lit_type(op.value)
            attr = schema.resolve(op.qualifier, op.name, op.span)
            return schema.attrs.index(attr), None, attr.type

        li, llit, lt = resolve(left)
        ri, rlit, rt = resolve(right)

        if not compatible(lt, rt):
            raise RATypeError(
                f"cannot compare {lt.value} with {rt.value}: "
                f"{_describe(left)} is {lt.value}, {_describe(right)} is {rt.value}",
                node.span,
            )

        op, span = node.op, node.span

        if li is not None and ri is not None:
            # Column vs column: types are re-checked per row only because an
            # UNKNOWN-typed (empty) column can meet a populated one via union.
            def col_vs_col(row: tuple[Value, ...], i: int = li, j: int = ri) -> bool:
                a, b = row[i], row[j]
                return compare(op, a, b, span, _lit_type(a), _lit_type(b))

            return col_vs_col

        if li is not None and rlit is not None:
            i, lit = li, rlit

            def col_vs_lit(row: tuple[Value, ...], i: int = i, lit: Value = lit) -> bool:
                return compare(op, row[i], lit, span, _lit_type(row[i]), _lit_type(lit))

            return col_vs_lit

        if llit is not None and ri is not None:
            lit, j = llit, ri

            def lit_vs_col(row: tuple[Value, ...], j: int = j, lit: Value = lit) -> bool:
                return compare(op, lit, row[j], span, _lit_type(lit), _lit_type(row[j]))

            return lit_vs_col

        raise AssertionError("comparison with two literals is rejected by the parser")
