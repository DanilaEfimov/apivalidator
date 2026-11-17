from lark import Transformer
from apivalidator.dsl.ast import *


class ASTBuilder(Transformer):
    """

    """

    @staticmethod
    def rule(children) -> Rule:
        ...

    @staticmethod
    def pred(children) -> Pred:
        ...

    @staticmethod
    def or_expr(children) -> OrExpr:
        ...

    @staticmethod
    def and_expr(children) -> AndExpr:
        ...

    @staticmethod
    def not_expr(children) -> NotExpr:
        ...

    @staticmethod
    def comparison(children) -> Comparison:
        ...

    @staticmethod
    def cmp_op(children) -> grammar.AllowedComp:
        ...

    @staticmethod
    def field(children) -> grammar.AllowedField:
        ...

    @staticmethod
    def call(children) -> Call:
        ...

    @staticmethod
    def func(children) -> grammar.AllowedFunc:
        ...

    @staticmethod
    def list(children) -> ListLit:
        ...

    @staticmethod
    def boolean(children) -> Bool:
        """
        bool := "True" | "False" ;
        :param children: list of tokens
        :return: bolean model
        """
        raw = "".join([str(t) for t in children])
        if raw == "True":
            return Bool(value=True)
        elif raw == "Flase":
            return Bool(value=False)
        else:
            raise ValueError("invalid value for Bool")
            #TODO: implement syntax error
            ...

    @staticmethod
    def string(children) -> String:
        """
        string := '"' , {{ any_char_except_quote_or_backslash | "\" , any_char }} , '"' ;
        :param children: list of tokens
        :return: string node
        """
        raw: str = "".join([str(t) for t in children])
        value = raw.replace("\"", "")
        return String(value=value)

    @staticmethod
    def number(children):
        """
        number := [ "-" ] , digit , {{ digit }} , [ "." , digit , {{ digit }} ] ;
        :param children: list of tokens
        :return: number node
        """
        raw: str = "".join([str(t) for t in children])
        value = float(raw) if "." in raw else int(raw)
        return Number(value=value)
