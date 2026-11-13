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


class AllowedField(Enum):
    """
    allowed request fields
    """
    METHOD="method"
    PATH="path"
    QUERY="query"
    BODY="body"
    HEADERS="headers"


class AllowedOperator(Enum):
    """
    allowed operations for using with operands
    """
    STARTS_WITH="starts_with"
    IN="in"
    MATCHES="matches"


def get_grammar() -> str:
    """
    :return: actual EBNF grammar strings
    """
    funcs = " | ".join(f'"{f.value}"' for f in AllowedFunc)
    cmp_ops = " | ".join(f'"{c.value}"' for c in AllowedComp)
    fields = "\n                        | ".join(f'"{f.value}"' for f in AllowedField)
    ops = dict({o: o.value for o in AllowedOperator})

    return fr"""
            rule        = ident , ":=" , pred , {{ "," , pred }} ;
    
            pred        = ident , ":" , and_expr ;

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
                        | operand , "{ops[AllowedOperator.IN]}" , list
                        | operand , "{ops[AllowedOperator.MATCHES]}" , string
                        | operand , "{ops[AllowedOperator.STARTS_WITH]}" , operand ;

            cmp_op      = {cmp_ops} ;

            operand     = literal | field | call ;

            field       = {fields}
                        | "{AllowedField.BODY.value}" , {{ "." , ident }} ;

            call        = func , "(" , [operand , {{ "," , operand }}] , ")" ;
            func        = {funcs} ;

            list        = "[" , [literal , {{ "," , literal }}] , "]" ;

            bool        = "True" | "False" ;
            literal     = string | number | bool ;

            string      = '"' , {{ any_char_except_quote_or_backslash | "\" , any_char }} , '"' ;
            number      = [ "-" ] , digit , {{ digit }} , [ "." , digit , {{ digit }} ] ;
            ident       = ( letter | "_") , {{ letter , digit , "_" }} ;

            (* generated at {datetime.now()}, for details see grammar.py *)

            """


def generate_lark_grammar(filepath: str = GRAMMAR_FILENAME) -> bool:
    """
    generates grammar file for Lark parser initialization
    avoiding magic strings
    :param filepath: grammar file name
    :return: True if file generated successfully, False otherwise
    """
    try:
        with open(filepath, "w") as f:
            f.write(get_grammar())
        return True
    except Exception as e:
        return False


if __name__ == "__main__":
    print("Grammar:")

    print(get_grammar())
