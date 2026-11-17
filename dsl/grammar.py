import re
from enum import Enum
from pathlib import Path


GRAMMAR_FILENAME = "grammar.lark"

# ---------------------------------------
# Enums (single source of truth)
# ---------------------------------------

class AllowedFunc(Enum):
    """
    allowed function names
    """
    HEADER = "header"
    LEN = "len"
    EXISTS = "exists"
    LOWER = "lower"
    INT = "int"


class AllowedComp(Enum):
    """
    allowed comparison notation
    """
    GE = ">="
    LE = "<="
    EQ = "=="
    NEQ = "!="
    LT = "<"
    GT = ">"


class AllowedField(Enum):
    """
    allowed request fields
    """
    METHOD = "method"
    PATH = "path"
    QUERY = "query"
    BODY = "body"


class AllowedOperator(Enum):
    """
    allowed word operators.
    the member NAME is also the terminal name in the grammar
    """
    STARTS_WITH = "starts_with"
    IN = "in"
    MATCHES = "matches"


class LogicOp(Enum):
    """
    allowed logic operations
    the member NAME is also the terminal name in the grammar (with a leading '_')
    """
    OR = "or"
    AND = "and"
    NOT = "not"


# what may stand to the right of each word operator (a grammar rule name).
# the grammar enforces this, so the transformer does not have to re-check it
OPERATOR_RHS = {
    AllowedOperator.IN: "list_lit",
    AllowedOperator.MATCHES: "string",
    AllowedOperator.STARTS_WITH: "operand",
}

_missing = set(AllowedOperator) - set(OPERATOR_RHS)
if _missing:
    raise RuntimeError(f"OPERATOR_RHS has no entry for: {sorted(m.name for m in _missing)}")


# ---------------------------------------
# Grammar generation
# ---------------------------------------

def _alternatives(values, *, word: bool) -> str:
    """
    builds a Lark regex terminal that matches any of the values,
    longest first (so '<=' wins over '<').
    for words a trailing \\b keeps 'in' from matching the start of 'index'
    """
    body = "|".join(re.escape(v) for v in sorted(values, key=len, reverse=True))
    return f"/(?:{body})\\b/" if word else f"/(?:{body})/"


def get_grammar() -> str:
    """
    :return: Lark grammar text, built from the enums above.
             deterministic: no timestamps, so generated files do not produce noisy diffs
    """
    plain_fields = [f.value for f in AllowedField if f is not AllowedField.BODY]

    word_op_alts = "\n          | ".join(
        f"operand {op.name} {OPERATOR_RHS[op]}" for op in AllowedOperator
    )
    word_op_terminals = "\n".join(
        f"{op.name}: {_alternatives([op.value], word=True)}" for op in AllowedOperator
    )
    logic_terminals = "\n".join(
        f"_{op.name}: {_alternatives([op.value], word=True)}" for op in LogicOp
    )

    return rf"""// generated from grammar.py, do not edit by hand

rule: IDENT ":=" pred ("," pred)*
pred: IDENT ":" or_expr

// '?' rules disappear when they have a single child,
// so 'a' stays a plain comparison and only 'a and b' becomes an and_expr
?or_expr: and_expr (_OR and_expr)*
?and_expr: not_expr (_AND not_expr)*
?not_expr: atom
         | _NOT not_expr -> negation
?atom: "(" or_expr ")"
     | comparison

comparison: operand
          | operand CMP_OP operand
          | {word_op_alts}

?operand: literal | field | call

field: FIELD_NAME
     | BODY ("." IDENT)*
call: FUNC "(" (operand ("," operand)*)? ")"
list_lit: "[" (literal ("," literal)*)? "]"

?literal: string | number | boolean
string: STRING
number: NUMBER
boolean: BOOL

// terminals
{logic_terminals}
{word_op_terminals}
CMP_OP: {_alternatives([c.value for c in AllowedComp], word=False)}
FUNC: {_alternatives([f.value for f in AllowedFunc], word=True)}
FIELD_NAME: {_alternatives(plain_fields, word=True)}
BODY: {_alternatives([AllowedField.BODY.value], word=True)}
BOOL: /(?:True|False)\b/
STRING: /"(?:[^"\\]|\\.)*"/
NUMBER: /-?\d+(?:\.\d+)?/
IDENT: /[A-Za-z_][A-Za-z0-9_]*/

%import common.WS
%ignore WS
"""


def generate_lark_grammar(filepath: str | Path | None = None) -> bool:
    """
    writes the grammar to a file (handy for reading it; the parser itself
    takes the text straight from get_grammar())
    :param filepath: target file, by default next to this module
    :return: True if file generated successfully, False otherwise
    """
    path = Path(filepath) if filepath else Path(__file__).with_name(GRAMMAR_FILENAME)
    try:
        path.write_text(get_grammar(), encoding="utf-8")
        return True
    except OSError:
        return False


if __name__ == "__main__":
    print(get_grammar())

    choice = input(f"do you want to generate grammar to file '{GRAMMAR_FILENAME}' (yes/no): ").lower()
    if choice == "y" or choice == "yes":
        generate_lark_grammar(GRAMMAR_FILENAME)
