# TODO: replace builtin errors with custom errors

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
    Lark transformer that builds DSL AST nodes from parse trees.

    Each method corresponds to a grammar rule (see ``grammar.py``) and
    receives a list of already-transformed children. Methods return the
    appropriate AST node or raise ``ValueError`` on invalid input.

    Terminal tokens are compared as strings; allowed values come from the
    enums in ``grammar.py``.
    """

    @staticmethod
    def _build_separated(children, separator: str, t: type[T] | tuple[type[T], ...]) -> List[T]:
        """
        trying to build a list of comma separated values of "t"
        :param children: list of subtrees
        :param separator: separator string
        :param t: type of an item
        :return: list of "t"
        """
        items: List[T] = []
        waiting_for_sep = False

        for l in children[1:-1]:
            if str(l) == separator:
                if not waiting_for_sep:
                    raise ValueError(f"unexpected '{separator}' in a list of literals")
                    # TODO: implement syntax error
                waiting_for_sep = False
            elif isinstance(l, t):
                if waiting_for_sep:
                    raise ValueError(f"expected '{separator}' between list elements")
                    # TODO: implement syntax error
                items.append(l)
                waiting_for_sep = True
            else:
                raise ValueError(f"Unexpected token '{str(l)}' in a list of literals")
                # TODO: implement syntax error

        # case "1, "
        if items != [] and not waiting_for_sep:
            raise ValueError(f"expected literal, gotten '{separator}'")
            # TODO: implement syntax error

        return items

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

        return ASTBuilder._build_separated(children[1:-1], ",", t)

    @staticmethod
    def rule(children) -> Rule:
        """
        rule := ident , ":=" , pred , {{ "," , pred }} ;
        see the actual rules in **grammar.py**
        :param children: list of subtrees
        :return: rule model
        """
        if len(children) < 3:
            raise ValueError("not enough tokens to build rule")

        ident_string: str = str(children[0])
        if not ident_string.isidentifier():
            raise ValueError(f"name '{ident_string}' is not an identifier")

        if str(children[1]) != ":=":
            raise ValueError(f"expected ':=', got {str(children[1])}")

        preds: List[Pred] = ASTBuilder._build_separated(children[2:], ",", Pred)
        return Rule(name=ident_string, predicates=preds)

    @staticmethod
    def pred(children) -> Pred:
        """
        pred := ident , ":" , and_expr ;
        see the actual rules in **grammar.py**
        :param children: list of subtrees
        :return: predicate model
        """
        if len(children) != 3:
            raise ValueError(f"invalid predicate: expected 3 children, got {len(children)}")

        ident_string: str = str(children[0])
        if not ident_string.isidentifier():
            raise ValueError(f"name '{ident_string}' is not an identifier")

        if str(children[1]) != ":":
            raise ValueError(f"expected ':', got {str(children[1])}")

        pred = children[2]
        if not isinstance(pred, AndExpr):
            raise ValueError(f"expected and-expression, got {type(pred).__name__}")

        return Pred(name=ident_string, expression=pred)

    @staticmethod
    def or_expr(children) -> OrExpr:
        """
        or_expr := and_expr , {{ "or" , and_expr }} ;
        see the actual rules in **grammar.py**
        :param children: list of subtreees
        :return: or expression model
        """
        exprs: List[AndExpr] = ASTBuilder._build_separated(children, LogicOp.AND.value, AndExpr)
        return OrExpr(expressions=exprs)

    @staticmethod
    def and_expr(children) -> AndExpr:
        """
        and_expr := not_expr , {{ "and" , not_expr }} ;
        see the actual rules in **grammar.py**
        :param children: list of subtrees
        :return: and expression model
        """
        exprs: List[NotExpr] = ASTBuilder._build_separated(children, LogicOp.AND.value, NotExpr)
        return AndExpr(expressions=exprs)

    @staticmethod
    def not_expr(children) -> NotExpr:
        """
        not_expr := atom | "not" , not_expr ;
        see the actual rules in **grammar.py**
        :param children: list of subtrees
        :return: not expression model
        """
        # atom case
        if len(children) == 1:
            if not isinstance(children[0], Atom):
                raise ValueError(f"expected comparison, got {type(children[0]).__name__}")
            return NotExpr(expression=children[0])

        # double not case
        if len(children) != 2:
            raise ValueError(f"invalid comparison: expected 1 or 2 children, got {len(children)}")

        op = children[0]
        expr = children[1]

        if LogicOp(str(op)) is not LogicOp.NOT:
            raise ValueError(f"expected 'not' operation, got {str(op)}")

        # DONT CHANGE GIVEN TYPES HERE BEFORE ast.py
        if not isinstance(expr, (OrExpr, AndExpr, Comparison)):
            raise ValueError(f"expected or/and-expression or comparison, got {type(expr).__name__}")

        return NotExpr(expression=expr)

    @staticmethod
    def atom(children) -> Atom:
        """
        atom := "(" , and_expr , ")"
                | "(" , or_expr , ")"
                | comparison ;
        :param children: list of subtrees
        :return: atom model
        """
        # comparison case
        if len(children) == 1:
            if not isinstance(children[0], Comparison):
                raise ValueError(f"expected comparison, got {type(children[0]).__name__}")
            return Atom(value=children[0])

        # and/or expression case
        if len(children) != 3:
            raise ValueError(f"invalid comparison: expected 1 or 3 children, got {len(children)}")

        if str(children[0]) != "(":
            raise ValueError("missed opening bracket")

        if str(children[-1]) != ")":
            raise ValueError("missed closing bracket")

        expr = children[1]
        if not isinstance(expr, AndExpr) and not isinstance(expr, OrExpr):
            raise ValueError(f"expected or/and-expression, got {type(expr).__name__}")

        return Atom(value=expr)

    @staticmethod
    def comparison(children) -> Comparison:
        """
        comparison = operand
              | operand , cmp_op , operand
              | operand , "in" , list
              | operand , "matches" , string
              | operand , "starts_with" , operand ;
        see the actual rules in **grammar.py**
        :param children: list of subtrees
        :return: comparison model
        """
        if len(children) == 1:
            if not isinstance(children[0], Operand):
                raise ValueError(f"expected operand, got {type(children[0]).__name__}")
            return Comparison(left=children[0], op=None, right=None)

        # binary case (3 children)
        if len(children) != 3:
            raise ValueError(f"invalid comparison: expected 1 or 3 children, got {len(children)}")

        left = children[0]
        op_raw = children[1]
        right = children[2]

        if not isinstance(left, Operand):
            raise ValueError(f"expected operand on the left, got {type(left).__name__}")

        # cmp_op: operand , cmp_op , operand
        if isinstance(op_raw, AllowedComp):
            if not isinstance(right, Operand):
                raise ValueError(f"expected operand on the right, got {type(right).__name__}")
            return Comparison(left=left, op=op_raw, right=right)

        # in: operand , "in" , list
        if isinstance(op_raw, AllowedOperator) and op_raw is AllowedOperator.IN:
            if not isinstance(right, ListLit):
                raise ValueError(f"expected list after 'in', got {type(right).__name__}")
            return Comparison(left=left, op=op_raw, right=right)

        # matches: operand , "matches" , string
        if isinstance(op_raw, AllowedOperator) and op_raw is AllowedOperator.MATCHES:
            if not isinstance(right, String):
                raise ValueError(f"expected string after 'matches', got {type(right).__name__}")
            return Comparison(left=left, op=op_raw, right=right)

        # starts_with: operand , "starts_with" , operand
        if isinstance(op_raw, AllowedOperator) and op_raw is AllowedOperator.STARTS_WITH:
            if not isinstance(right, Operand):
                raise ValueError(f"expected operand after 'starts_with', got {type(right).__name__}")
            return Comparison(left=left, op=op_raw, right=right)

        raise ValueError(f"unknown comparison operator: {op_raw!r}")

    @staticmethod
    def cmp_op(children) -> AllowedComp:
        """
        cmp_op := ">=" | "<=" | "==" | "!=" | "<" | ">" ;
        :param children: list of tokens
        :return: allowed comparisons enumeration
        """
        if len(children) != 1:
            raise ValueError("comparison may be built only from a single token")

        code: str = str(children[0])
        if code not in CMD_OPS:
            raise ValueError(f"no such comparison '{code}'")
            # TODO: implement syntax error

        return AllowedComp(code)

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
                # TODO: implement syntax error
            return Field(field_name=AllowedField(raw))
        # path case
        else:
            parts = raw.split(".")
            if AllowedField(parts[0]) is not AllowedField.BODY:
                raise ValueError(f"no such path {".".join(parts)}")
            valid_path = all(part.isidentifier() for part in parts[1:])
            if not valid_path:
                raise ValueError(f"path contains non-identifier parts '{".".join(parts)}'")
                # TODO: implement syntax error
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
