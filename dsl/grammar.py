from datetime import datetime
from enum import Enum


GRAMMAR_FILENAME="grammar.lark"

# ---------------------------------------
# Enums
# ---------------------------------------

class AllowedFunc(Enum):
    """
    allowed function names
    """
    HEADER="header"
    LEN="len"
    EXISTS="exists"
    LOWER="lower"
    INT="int"


class AllowedComp(Enum):
    """
    allowed comparation notation
    """
    GE=">="
    LE="<="
    EQ="=="
    NEQ="!="
    LZ="<"
    GZ=">"


class AllowedFields(Enum):
    """
    allowed request fields
    """
    METHOD="method"
    PATH="path"
    QUERY="query"
    BODY="body"


class AllowedOperators(Enum):
    """
    allowed operations for using with operands
    """
    STARTS_WITH="starts_with"
    IN="in"
    MATCHES="matches"


def generate_lark_grammar(filepath: str = GRAMMAR_FILENAME) -> bool:
    """
    generates grammar file for Lark parser initialization
    avoiding magic strings
    :param filepath: grammar file name
    :return: True if file generated successfully, False otherwise
    """
    try:
        funcs = " | ".join(f'"{f.value}"' for f in AllowedFunc)
        cmp_ops = " | ".join(f'"{c.value}"' for c in AllowedComp)
        fields = "\n                        | ".join(f'"{f.value}"' for f in AllowedFields)
        ops = dict({o: o.value for o in AllowedOperators})

        with open(filepath, "w") as f:
            f.write(fr"""
            rule        = and_expr ;

            OR          = "or" ;
            AND         = "and" ;
            NOT         = "not" ;

            or_expr     = and_expr , {{ OR , and_expr }} ;
            and_expr    = not_expr , {{ AND , not_expr }} ;
            not_expr    = atom
                        | NOT , not_expr ;
            atom        = "(" , and_expr , ")"
                        | comparison ;

            comparison  = operand
                        | operand , cmp_op , operand
                        | operand , "{ops[AllowedOperators.IN]}" , list
                        | operand , "{ops[AllowedOperators.MATCHES]}" , string
                        | operand , "{ops[AllowedOperators.STARTS_WITH]}" , operand ;

            cmp_op      = {cmp_ops} ;

            operand     = literal | field | call ;

            field       = {fields}
                        | "{AllowedFields.BODY.value}" , {{ "." , ident }} ;

            call        = func , "(" , [operand , {{ "," , operand }}] , ")" ;
            func        = {funcs} ;

            list        = "[" , [literal , {{ "," , literal }}] , "]" ;

            literal     = string | number | "true" | "false" ;

            string      = '"' , {{ any_char_except_quote_or_backslash | "\" , any_char }} , '"' ;
            number      = [ "-" ] , digit , {{ digit }} , [ "." , digit , {{ digit }} ] ;
            ident       = ( letter | "_") , {{ letter , digit , "_" }} ;

            (* generated at {datetime.now()}, for details see grammar.py *)

            """)
        return True
    except Exception as e:
        return False
