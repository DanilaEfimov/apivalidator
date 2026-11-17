from dataclasses import dataclass
from typing import Union, Tuple, Optional

import apivalidator.dsl.grammar as grammar

__all__ = [
    "Func",
    "Number",
    "String",
    "Bool",
    "Field",
    "Call",
    "Literal",
    "Operand",
    "Operation",
    "ListLit",
    "Comparison",
    "NotExpr",
    "AndExpr",
    "OrExpr",
    "Expr",
    "Pred",
    "Rule",
]

# ---------------------------------------
# AST nodes
# ---------------------------------------

@dataclass(frozen=True)
class Func:
    """
    function ast node dataclass
    """
    func_name: grammar.AllowedFunc


@dataclass(frozen=True)
class Number:
    """
    number ast node dataclass
    """
    value: Union[int, float]


@dataclass(frozen=True)
class String:
    """
    string ast node dataclass
    """
    value: str


@dataclass(frozen=True)
class Bool:
    """
    boolean literal ast node dataclass
    """
    value: bool


@dataclass(frozen=True)
class Field:
    """
    field access ast node dataclass
    """
    field_name: grammar.AllowedField
    path: Tuple[str, ...] = ()  # body.size


@dataclass(frozen=True)
class Call:
    """
    function call ast node dataclass
    """
    func: Func
    args: Tuple["Operand", ...]


Literal = Union[String, Number, Bool]
Operand = Union[Literal, Field, Call]
Operation = Union[grammar.AllowedComp, grammar.AllowedOperator]


@dataclass(frozen=True)
class ListLit:
    """
    list literal ast node dataclass
    """
    values: Tuple[Literal, ...]


@dataclass(frozen=True)
class Comparison:
    """
    comparison predicate ast node dataclass.
    a bare operand ('exists(query)') has op=None and right=None
    """
    left: Operand
    op: Optional[Operation] = None
    right: Optional[Union[Operand, ListLit]] = None    # ListLit for 'in'


@dataclass(frozen=True)
class NotExpr:
    """
    logical not ast node dataclass, exists only when there really was a 'not'
    """
    expression: "Expr"


@dataclass(frozen=True)
class AndExpr:
    """
    logical and ast node dataclass, always has 2+ operands
    """
    expressions: Tuple["Expr", ...]


@dataclass(frozen=True)
class OrExpr:
    """
    logical or ast node dataclass, always has 2+ operands
    """
    expressions: Tuple["Expr", ...]


Expr = Union[Comparison, NotExpr, AndExpr, OrExpr]


@dataclass(frozen=True)
class Pred:
    """
    predicate ast node dataclass
    """
    name: str
    expression: Expr


@dataclass(frozen=True)
class Rule:
    """
    rule ast node dataclass
    """
    name: str
    predicates: Tuple[Pred, ...]
