from dataclasses import dataclass
from typing import Union, List, Optional

import apivalidator.dsl.grammar as grammar


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
    path: tuple[str, ...] = ()  # body.size


@dataclass(frozen=True)
class Call:
    """
    function call ast node dataclass
    """
    func: Func
    args: List["Operand"]


Literal = Union[String, Number, Bool]
Operand = Union[Literal, Field, Call]
Operation = Union[grammar.AllowedComp, grammar.AllowedOperator]


@dataclass(frozen=True)
class ListLit:
    """
    list literal ast node dataclass
    """
    values: List[Literal]


@dataclass(frozen=True)
class Comparison:
    """
    comparison predicate ast node dataclass
    """
    left: Operand
    op: Optional[Operation]
    right: Optional[Union[Operand, ListLit]]    # list required for 'in' syntax


@dataclass(frozen=True)
class NotExpr:
    """
    logical not ast node dataclass
    """
    expression: Union[Comparison, "AndExpr", "OrExpr"]


@dataclass(frozen=True)
class AndExpr:
    """
    logical and ast node dataclass
    """
    expressions: List[NotExpr]


@dataclass(frozen=True)
class OrExpr:
    """
    logical or ast node dataclass
    """
    expressions: List[AndExpr]


@dataclass(frozen=True)
class Pred:
    """
    predicate ast node dataclass
    """
    name: str
    expression: AndExpr


@dataclass(frozen=True)
class Rule:
    """
    rule ast node dataclass
    """
    name: str
    predicates: List[Pred]

