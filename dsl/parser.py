from lark import Transformer
from apivalidator.dsl.ast import *

"""
due to 'isinstance' constraits we can not use 
Literal (aka Union[String, Number, Bool]) typing
in 'isinstance' clause
"""
_LITERAL_TYPES = (String, Bool, Number)


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
        """
        list := "[" , [literal , {{ "," , literal }}] , "]" ;
        :param children: list of subtrees
        :return: list of literals model
        """
        if len(children) < 2:
            raise ValueError("invalid value for list of literals")
            # TODO: implement syntax error

        opening_seen = str(children[0]) == "["
        closing_seen = str(children[-1]) == "]"
        if not opening_seen or not closing_seen:
            raise ValueError("missed opening or closing bracket")

        literals: List[Literal] = []
        waiting_for_comma = False

        for l in children[1:-1]:
            if str(l) == ",":
                if not waiting_for_comma:
                    raise ValueError("unexpected ',' in a list of literals")
                    # TODO: implement syntax error
                waiting_for_comma = False
            elif isinstance(l, _LITERAL_TYPES):
                if waiting_for_comma:
                    raise ValueError("expected ',' between list elements")
                    # TODO: implement syntax error
                literals.append(l)
                waiting_for_comma = True
            else:
                raise ValueError(f"Unexpected token '{str(l)}' in a list of literals")
                # TODO: implement syntax error

        # case [1, ]
        if literals != [] and not waiting_for_comma:
            raise ValueError("expected literal, gotten ','")
            # TODO: implement syntax error

        return ListLit(values=literals)

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
            # TODO: implement syntax error
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
