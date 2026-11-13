from dataclasses import dataclass
from typing import Union, List
from lark import Transformer
from uritemplate.variable import Operator

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


@dataclass(frozen=True)
class Call:
    """
    function call ast node dataclass
    """
    func: Func
    args: List[str]


Literal = Union[String, Number, Bool]
Operand = Union[Literal, grammar.AllowedField, Call]


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
    Operation=Union[grammar.AllowedComp, grammar.AllowedOperator]
    left: Operand
    op: Operator
    right: Operand


@dataclass(frozen=True)
class NotExpr:
    """
    logical not ast node dataclass
    """
    ...


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


class ASTBuilder(Transformer):

    def rule(self, children) -> Rule:
        ...

    def pred(self, children) -> Pred:

    def or_expr(self, children) -> OrExpr:
        ...

    def and_expr(self, children) -> AndExpr:
        ...

    def not_expr(self, children) -> NotExpr:
        ...

    def comparison(self, children) -> Comparison:
        ...

    def cmp_op(self, children):
        ...

    def field(self, children):
        ...

    def call(self, children):
        ...

    def func(self, children):
        ...

    def list(self, children):
        ...

    def string(self, children):
        ...

    def number(self, children):
        ...
