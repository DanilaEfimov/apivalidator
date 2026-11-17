from typing import TypeVar

from lark import Transformer
from apivalidator.dsl.ast import *
from apivalidator.dsl.grammar import *

"""
due to 'isinstance' constraits we can not use 
Literal (aka Union[String, Number, Bool]) typing
in 'isinstance' clause
"""
_LITERAL_TYPES = (String, Bool, Number)

"""
type annotation for describing typing params
"""
T = TypeVar("T")


class ASTBuilder(Transformer):
    """

    """

    @staticmethod
    def _build_list_of(children, t: type[T] | tuple[type[T], ...]) -> List[T]:
        """
        trying to build a list of "t"
        :param children: list of subtrees
        :param t: type of an item
        :return: list of "t"
        """
        if len(children) < 2:
            raise ValueError("invalid value for list of literals")
            # TODO: implement syntax error

        opening_seen = str(children[0]) == "["
        closing_seen = str(children[-1]) == "]"
        if not opening_seen or not closing_seen:
            raise ValueError("missed opening or closing bracket")

        items: List[T] = []
        waiting_for_comma = False

        for l in children[1:-1]:
            if str(l) == ",":
                if not waiting_for_comma:
                    raise ValueError("unexpected ',' in a list of literals")
                    # TODO: implement syntax error
                waiting_for_comma = False
            elif isinstance(l, t):
                if waiting_for_comma:
                    raise ValueError("expected ',' between list elements")
                    # TODO: implement syntax error
                items.append(l)
                waiting_for_comma = True
            else:
                raise ValueError(f"Unexpected token '{str(l)}' in a list of literals")
                # TODO: implement syntax error

        # case [1, ]
        if items != [] and not waiting_for_comma:
            raise ValueError("expected literal, gotten ','")
            # TODO: implement syntax error

        return items

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
    def field(children) -> Field:
        """
        field := "method" | "path" | "query" | "body" | "body" , { "." , ident } ;
        see the actual rules in **grammar.py**
        :param children: list of subtrees
        :return: field model
        """
        raw: str = "".join([str(t) for t in children])

        # empty field case
        if not children:
            raise ValueError("empty field")
        # no path case
        if len(children) == 1:
            if raw not in FIELDS:
                raise ValueError(f"no such field '{raw}'")
                #TODO: implement syntax error
            return Field(field_name=AllowedField(raw))
        # path case
        else:
            parts = raw.split(".")
            if AllowedField(parts[0]) is not AllowedField.BODY:
                raise ValueError(f"no such path {".".join(parts)}")
            valid_path = all(part.isidentifier() for part in parts[1:])
            if not valid_path:
                raise ValueError(f"path contains non-identifier parts '{".".join(parts[])}'")
                #TODO: implement syntax error
            return Field(field_name=AllowedField.BODY, path=tuple(parts[1:]))

    @staticmethod
    def call(children) -> Call:
        """
        call := func , "(" , [operand , {{ "," , operand }}] , ")" ;
        :param children: list of subtrees
        :return: call model
        """
        if len(children) < 3:
            raise ValueError("not enough tokens for building a call")
            # TODO: implement syntax error

        func: Func = children[0]
        if str(children[1]) != "(":
            raise ValueError("missed opening bracket")
            # TODO: implement syntax error
        if str(children[-1] != ")"):
            raise ValueError("missed closing bracket")
            # TODO: implement syntax error

        args: List[Operand] = ASTBuilder._build_list_of(children[2:-1], Operand)
        return Call(func=func, args=args)

    @staticmethod
    def func(children) -> Func:
        """
        func := "header" | "len" | "exists" | "lower" | "int"
        see the actual rules in **grammar.py**
        :param children: list of subtrees
        :return: function model
        """
        if len(children) != 1:
            raise ValueError("name of a function has to be a single word")
            # TODO: implement syntax error

        raw: str = "".join([str(t) for t in children])
        if raw in FUNCS:
            return Func(func_name=AllowedFunc(raw))

        raise ValueError(f"invalid function name '{raw}'")
        # TODO: implement syntax error

    @staticmethod
    def list(children) -> ListLit:
        """
        list := "[" , [literal , {{ "," , literal }}] , "]" ;
        :param children: list of subtrees
        :return: list of literals model
        """
        items: List[Literal] = ASTBuilder._build_list_of(children, _LITERAL_TYPES)
        return ListLit(values=items)

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
