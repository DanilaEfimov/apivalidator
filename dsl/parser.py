from lark import Transformer
from apivalidator.dsl.ast import *


class ASTBuilder(Transformer):
    """

    """

    def rule(self, children) -> Rule:
        ...

    def pred(self, children) -> Pred:
        ...

    def or_expr(self, children) -> OrExpr:
        ...

    def and_expr(self, children) -> AndExpr:
        ...

    def not_expr(self, children) -> NotExpr:
        ...

    def comparison(self, children) -> Comparison:
        ...

    def cmp_op(self, children) -> grammar.AllowedComp:
        ...

    def field(self, children) -> grammar.AllowedField:
        ...

    def call(self, children) -> Call:
        ...

    def func(self, children) -> grammar.AllowedFunc:
        ...

    def list(self, children):
        ...

    def string(self, children):
        ...

    def number(self, children):
        ...
