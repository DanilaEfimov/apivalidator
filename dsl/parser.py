"""
Parses DSL text into AST nodes using a Lark grammar.

Public entry point is ``parse``; syntax errors are raised as ``DslSyntaxError``
with line and column of the offending token.
"""

from typing import Optional

from lark import (
    Transformer, Lark, UnexpectedInput, UnexpectedCharacters,
    UnexpectedEOF, UnexpectedToken
)
from apivalidator.dsl.dslast import *
from apivalidator.dsl.grammar import *

import ast


class DslSyntaxError(ValueError):
    """
    Syntax error of the DSL text.

    Carries the 1-based ``line`` and ``column`` of the offending token
    (when known) and an optional ``context`` snippet showing where it happened.
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

    @staticmethod
    def rule(children) -> Rule:
        """
        rule: IDENT ":=" pred ("," pred)*
        :param children: list of values
        :return: rule node
        """
        ident, *preds = children
        return Rule(name=ident, predicates=tuple(preds))

    @staticmethod
    def pred(children) -> Pred:
        """
        pred: IDENT ":" or_expr
        :param children: list of values
        :return: predicate node
        """
        ident, expr = children
        return Pred(name=ident, expression=expr)

    # logic

    @staticmethod
    def or_expr(children):
        """
        ?or_expr: and_expr (_OR and_expr)*
        :param children: list of values
        :return: or expression node
        """
        return OrExpr(expressions=tuple(children))

    @staticmethod
    def and_expr(children) -> AndExpr:
        """
        ?and_expr: not_expr (_AND not_expr)*
        :param children: list of values
        :return: and expression node
        """
        return AndExpr(expressions=tuple(children))

    @staticmethod
    def not_expr(children) -> NotExpr:
        """
        ?not_expr: atom
         | _NOT not_expr -> negation
        :param children: a single token
        :return: not expression node
        """
        return NotExpr(expression=children[0])

    @staticmethod
    def negation(children) -> NotExpr:
        """
        alias
        ?not_expr: atom
         | _NOT not_expr -> negation
        :param children: a single token
        :return: not expression node
        """
        return NotExpr(expression=children[0])

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

    # operands

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

    # literals

    @staticmethod
    def list_lit(children):
        """
        list_lit: "[" (literal ("," literal)*)? "]"
        :param children: list of tokens or literals
        :return: literal list node
        """
        return ListLit(values=tuple(children))

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

    @staticmethod
    def IDENT(token) -> str:
        """
        IDENT: /[A-Za-z_][A-Za-z0-9_]*/
        :return: string
        """
        return str(token)

    @staticmethod
    def CMP_OP(token) -> AllowedComp:
        """
        CMP_OP: {_alternatives([c.value for c in AllowedComp], word=False)}
        see the actual rules in **grammar.py**
        :param token: a single token
        :return: comparison enumeration
        """
        return AllowedComp(str(token))

    @staticmethod
    def FUNC(token):
        """
        FUNC: {_alternatives([f.value for f in AllowedFunc], word=True)}
        see the actual rules in **grammar.py**
        :param token: a single token
        :return: func node
        """
        return Func(func_name=AllowedFunc(token))

    def __default_token__(self, token):
        """
        catches every untracked token
        :param token: untracked token
        :return: processed token
        """
        if token.type in AllowedOperator.__members__:
            return AllowedOperator[token.type]
        return token


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
