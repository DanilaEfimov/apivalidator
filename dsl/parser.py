from dataclasses import dataclass
from typing import TypeVar, Tuple, List, Optional

from django.contrib.sessions.backends import file
from lark import (
    Transformer, Lark, UnexpectedInput, UnexpectedCharacters,
    UnexpectedEOF, UnexpectedToken
)
from apivalidator.dsl.dslast import *
from apivalidator.dsl.grammar import *

import re
import ast


"""
generalized type annotation
"""
T = TypeVar("T")


@dataclass(frozen=True)
class TokenPos:
    """
    position of a token
    """
    line: int
    column: int


class DslSyntaxError(ValueError):
    """

    """

    def __init__(self, message: str,
                 line: Optional[int]=None,
                 column: Optional[int]=None,
                 context: str=""):
        """
        :param message: error description
        :param line: line of the token's pos
        :param column: column of the token's pos
        :param context: context of exception
        """
        where = f"at line {line}, at column {column}" if line is not None else ""
        super().__init__(f"{message} {where}" + f"\n{context if context else ''}")
        self.message = message
        self.line = line
        self.column = column
        self.context = context


def is_identifier(s: str) -> bool:
    """
    checks the ident grammar rule
    see the actual rules in **grammar.py**
    :param s: string
    :return: True if it's ascii identifier, False otherwise
    """
    return re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', s) is not None


class ASTBuilder(Transformer):
    """
    Lark transformer that builds DSL AST nodes from parse trees.

    Each method corresponds to a grammar rule (see ``grammar.py``) and
    receives a list of already-transformed children. Methods return the
    appropriate AST node or raise ``ValueError`` on invalid input.

    Terminal tokens are compared as strings; allowed values come from the
    enums in ``grammar.py``.
    """

    # rules / predicates

    def rule(self, children):
        raise NotImplementedError

    def pred(self, children):
        raise NotImplementedError

    # logic

    def or_expr(self, children):
        raise NotImplementedError

    def and_expr(self, children):
        raise NotImplementedError

    def not_expr(self, children):
        raise NotImplementedError

    def negation(self, children):
        # alias rule: _NOT not_expr -> negation
        raise NotImplementedError

    def atom(self, children):
        raise NotImplementedError

    # comparisons

    @staticmethod
    def comparison(children) -> Comparison:
        """
        comparison: operand
          | operand CMP_OP operand
          | {word_op_alts}
        see the actual rules in **grammar.py**
        :param children: list of tokens
        :return: comparison node
        """
        if len(children) == 1:
            return Comparison(left=children[0])
        left, op, right = children
        return Comparison(left=left, op=op, right=right)


    @staticmethod
    def cmp_op(children) -> AllowedComp:
        """
        CMP_OP: {_alternatives([c.value for c in AllowedComp], word=False)}
        see the actual rules in **grammar.py**
        :param children: list of tokens
        :return: comparison enumeration
        """
        return AllowedComp(str(children[0]))

    # operands

    @staticmethod
    def operand(children):
        # '?operand' usually disappears, but keep it for safety
        raise NotImplementedError

    @staticmethod
    def field(children) -> Field:
        """
        field: FIELD_NAME
            | BODY ("." IDENT)*
        :param children: list of tokens
        :return: field node
        """
        field_name, *path = children
        if len(children) == 1:
            return Field(field_name=AllowedField(str(field_name)))

        return Field(field_name=AllowedField(str(field_name)), path=tuple(path))

    @staticmethod
    def call(children) -> Call:
        """
        call: FUNC "(" (operand ("," operand)*)? ")"
        :param children: list of tokens
        :return: call node
        """
        func, *args = children
        return Call(func=func, args=tuple(args))

    @staticmethod
    def func(children):
        """
        FUNC: {_alternatives([f.value for f in AllowedFunc], word=True)}
        see the actual rules in **grammar.py**
        :param children: a single token
        :return: func node
        """
        raw = str(children[0])
        return Func(func_name=AllowedFunc(raw))

    # literals

    @staticmethod
    def list_lit(children):
        """
        list_lit: "[" (literal ("," literal)*)? "]"
        :param children: list of tokens or literals
        :return: literal list node
        """
        return ListLit(values=Tuple[Literal](children))

    @staticmethod
    def string(children) -> String:
        """
        string: STRING
        :param children: single token
        :return: string node
        """
        token = children[0]
        raw = str(token)
        value = ast.literal_eval(raw)
        return String(value=value)

    @staticmethod
    def number(children) -> Number:
        """
        number: NUMBER
        :param children: single token
        :return: number node
        """
        token = children[0]
        raw = str(token)
        value = float(raw) if "." in raw else int(raw)
        return Number(value=value)

    @staticmethod
    def boolean(children) -> Bool:
        """
        boolean: BOOL
        :param children: single token
        :return: boolean node
        """
        token = children[0]
        raw = str(token)
        value = raw == "True"
        return Bool(value=value)

    # terminals with word operators

    def IN(self, token):
        raise NotImplementedError

    def MATCHES(self, token):
        raise NotImplementedError

    def STARTS_WITH(self, token):
        raise NotImplementedError


_PARSER = Lark(get_grammar(), start="rule", parser="lalr", maybe_placeholders=False)


def parse(text: str) -> Rule:
    """
    parses DSL text into a Rule
    :param text: e.g. 'r := p: method == "GET" and len(body.items) > 0'
    :raises DslSyntaxError: on any syntax error, with line and column
    """
    try:
        tree = _PARSER.parse(text)
    except UnexpectedInput as e:
        raise _to_syntax_error(e, text) from None
    return ASTBuilder().transform(tree)


def _to_syntax_error(e: UnexpectedInput, text: str) -> DslSyntaxError:
    if isinstance(e, UnexpectedEOF):
        return DslSyntaxError("unexpected end of input", getattr(e, "line", None), getattr(e, "column", None))

    if isinstance(e, UnexpectedToken):
        found = f"unexpected {str(e.token)!r}"
        expected = e.accepts or e.expected
    elif isinstance(e, UnexpectedCharacters):
        found = f"unexpected character {text[e.pos_in_stream]!r}"
        expected = e.allowed
    else:
        found, expected = "syntax error", None

    if expected:
        found += f", expected one of: {', '.join(sorted(expected))}"
    return DslSyntaxError(found, e.line, e.column, e.get_context(text))


if __name__ == "__main__":
    from lark import Lark
    from apivalidator.dsl.grammar import get_grammar

    parser = Lark(get_grammar(), start="rule", parser="lalr")
    print(parser.parse('r := p: method in ["GET"]'))