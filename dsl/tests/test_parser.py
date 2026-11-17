"""
Edge-case and regression tests for apivalidator.dsl.parser.

Tests marked xfail(strict=True) describe known defects. They state the desired
behaviour and turn red (XPASS) as soon as the defect is fixed, which is the
reminder to delete the marker.
"""

import dataclasses
import itertools
import warnings

import pytest
from lark import Token

from apivalidator.dsl.dslast import *
from apivalidator.dsl.grammar import (
    OPERATOR_RHS,
    AllowedComp,
    AllowedField,
    AllowedFunc,
    AllowedOperator,
    LogicOp,
)
from apivalidator.dsl.parser import DslSyntaxError, parse


# ---------------------------------------
# helpers and building blocks
# ---------------------------------------

def expr(text: str):
    """expression of the only predicate in 'r := p: <text>'"""
    return parse(f"r := p: {text}").predicates[0].expression


def exists(field: AllowedField) -> Comparison:
    return Comparison(Call(Func(AllowedFunc.EXISTS), (Field(field),)))


A = exists(AllowedField.QUERY)      # exists(query)
B = exists(AllowedField.PATH)       # exists(path)
C = exists(AllowedField.BODY)       # exists(body)


def parse_or_syntax_error(text: str):
    """any outcome is fine except an exception that is not a DslSyntaxError"""
    try:
        return parse(text)
    except DslSyntaxError as e:
        return e


def assert_syntax_error(text: str) -> DslSyntaxError:
    with pytest.raises(DslSyntaxError) as info:
        parse(text)
    return info.value


# ---------------------------------------
# every enum member works end to end (grows together with the enums)
# ---------------------------------------

@pytest.mark.parametrize("func", AllowedFunc)
def test_every_function_parses(func):
    assert expr(f"{func.value}(query)").left == Call(Func(func), (Field(AllowedField.QUERY),))


@pytest.mark.parametrize("comp", AllowedComp)
def test_every_comparator_parses(comp):
    e = expr(f"len(body) {comp.value} 1")
    assert e.op is comp
    assert e.right == Number(1)


@pytest.mark.parametrize("field", AllowedField)
def test_every_field_parses(field):
    assert expr(f"{field.value} == 1").left == Field(field)


_RHS_SAMPLES = {"list": "[1]", "string": '"a"', "number": "1", "field": "path", "call": "exists(query)"}
_RHS_ACCEPTS = {
    "list_lit": {"list"},
    "string": {"string"},
    "operand": {"string", "number", "field", "call"},
}
_OPERATOR_CASES = [
    (op, kind, kind in _RHS_ACCEPTS[OPERATOR_RHS[op]])
    for op, kind in itertools.product(AllowedOperator, _RHS_SAMPLES)
]


@pytest.mark.parametrize("op, kind, valid", _OPERATOR_CASES,
                         ids=[f"{op.name}-{kind}-{'ok' if valid else 'rejected'}" for op, kind, valid in _OPERATOR_CASES])
def test_word_operators_accept_only_their_rhs(op, kind, valid):
    text = f"r := p: path {op.value} {_RHS_SAMPLES[kind]}"
    if valid:
        assert parse(text).predicates[0].expression.op is op
    else:
        assert_syntax_error(text)


_KEYWORDS = sorted({e.value for enum in (AllowedFunc, AllowedField, AllowedOperator, LogicOp) for e in enum}
                   | {"True", "False"})


@pytest.mark.parametrize("word", _KEYWORDS)
def test_keywords_are_allowed_as_body_path_segments(word):
    assert expr(f"body.{word} == 1").left == Field(AllowedField.BODY, (word,))


@pytest.mark.parametrize("name", [
    "index", "inbound", "android", "order", "notes", "matchesAll", "starts_with_x",
    "lenient", "bodyguard", "True_", "Falsey", "int2", "header_ok", "_x", "x1", "_",
])
def test_names_that_merely_start_with_a_keyword(name):
    r = parse(f"{name} := {name}: exists(query)")
    assert (r.name, r.predicates[0].name) == (name, name)


# ---------------------------------------
# logic: precedence, associativity, parentheses
# ---------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("exists(query) or exists(path) and exists(body)", OrExpr((A, AndExpr((B, C))))),
    ("exists(query) and exists(path) or exists(body)", OrExpr((AndExpr((A, B)), C))),
    ("not exists(query) and exists(path)", AndExpr((NotExpr(A), B))),
    ("not exists(query) or exists(path)", OrExpr((NotExpr(A), B))),
    ("not (exists(query) or exists(path))", NotExpr(OrExpr((A, B)))),
    ("(exists(query) or exists(path)) and exists(body)", AndExpr((OrExpr((A, B)), C))),
    ("exists(query) and exists(path) and exists(body)", AndExpr((A, B, C))),
    ("exists(query) or exists(path) or exists(body)", OrExpr((A, B, C))),
    ("exists(query) and (exists(path) and exists(body))", AndExpr((A, AndExpr((B, C))))),
    ("not not exists(query)", NotExpr(NotExpr(A))),
    ("not not not exists(query)", NotExpr(NotExpr(NotExpr(A)))),
    ("((exists(query)))", A),
    ("(exists(query) or exists(path))", OrExpr((A, B))),
    ('not method == "GET"', NotExpr(Comparison(Field(AllowedField.METHOD), AllowedComp.EQ, String("GET")))),
], ids=lambda v: v if isinstance(v, str) else "")
def test_logic_structure(text, expected):
    assert expr(text) == expected


def test_single_operand_expressions_are_not_wrapped():
    """no degenerate one-element and/or/not nodes"""
    assert expr("exists(query)") == A
    assert isinstance(expr("(exists(query))"), Comparison)


# ---------------------------------------
# operands
# ---------------------------------------

@pytest.mark.parametrize("source, operand", [
    ("True", Bool(True)),
    ("False", Bool(False)),
    ('"x"', String("x")),
    ("5", Number(5)),
    ("method", Field(AllowedField.METHOD)),
    ("body", Field(AllowedField.BODY)),
    ("body.a.b.c", Field(AllowedField.BODY, ("a", "b", "c"))),
    ("exists(query)", Call(Func(AllowedFunc.EXISTS), (Field(AllowedField.QUERY),))),
])
def test_bare_operand(source, operand):
    assert expr(source) == Comparison(left=operand, op=None, right=None)


def test_operands_on_both_sides():
    assert expr("method == path") == Comparison(
        Field(AllowedField.METHOD), AllowedComp.EQ, Field(AllowedField.PATH))
    assert expr("1 == 1") == Comparison(Number(1), AllowedComp.EQ, Number(1))


def test_calls_keep_argument_order_and_types():
    call = expr('header("a", 1, True, body.x, len(path))').left
    assert call.func == Func(AllowedFunc.HEADER)
    assert call.args == (
        String("a"), Number(1), Bool(True),
        Field(AllowedField.BODY, ("x",)),
        Call(Func(AllowedFunc.LEN), (Field(AllowedField.PATH),)),
    )


def test_call_without_arguments():
    assert expr("exists()").left == Call(Func(AllowedFunc.EXISTS), ())


def test_nested_calls():
    call = expr('len(lower(header("X")))').left
    assert call.func == Func(AllowedFunc.LEN)
    inner = call.args[0]
    assert inner.func == Func(AllowedFunc.LOWER)
    assert inner.args == (Call(Func(AllowedFunc.HEADER), (String("X"),)),)


# ---------------------------------------
# literals
# ---------------------------------------

@pytest.mark.parametrize("source, value", [
    (r'""', ""),
    (r'"abc"', "abc"),
    (r'"a\"b"', 'a"b'),
    (r'"a\\b"', "a\\b"),
    (r'"\\"', "\\"),                    # escaped backslash right before the closing quote
    (r'"\\\\"', "\\\\"),
    (r'"a\nb"', "a\nb"),
    (r'"a\tb"', "a\tb"),
    ('"привет"', "привет"),
    ('"and or not ( ) , ] [ := #"', "and or not ( ) , ] [ := #"),    # operators in strings are text
    ('"a,b"', "a,b"),
    ('"  spaces  "', "  spaces  "),
])
def test_string_values(source, value):
    assert expr(f"path == {source}").right == String(value)


@pytest.mark.parametrize("source, value", [
    ("0", 0),
    ("7", 7),
    ("-3", -3),
    ("7.0", 7.0),
    ("7.25", 7.25),
    ("-0.5", -0.5),
    ("9" * 30, int("9" * 30)),
])
def test_number_values_keep_their_type(source, value):
    number = expr(f"len(body) > {source}").right
    assert number == Number(value)
    assert type(number.value) is type(value)


@pytest.mark.parametrize("source", [
    "1.", ".5", "+1", "--1", "- 1", "1e3", "1_000", "0x10", "1.2.3", "NaN", "inf",
])
def test_malformed_numbers(source):
    assert_syntax_error(f"r := p: len(body) > {source}")


@pytest.mark.parametrize("source", ["true", "false", "TRUE", "None", "null", "Truex", "True1"])
def test_malformed_booleans(source):
    assert_syntax_error(f"r := p: exists(query) == {source}")


@pytest.mark.parametrize("source, values", [
    ("[]", ()),
    ('["a"]', (String("a"),)),
    ('["a", 1, 2.5, True, False]', (String("a"), Number(1), Number(2.5), Bool(True), Bool(False))),
    ('["a,b", "c"]', (String("a,b"), String("c"))),
    ('["]"]', (String("]"),)),
    ('[ "a" ,\n "b" ]', (String("a"), String("b"))),
])
def test_list_values(source, values):
    assert expr(f"method in {source}").right == ListLit(values)


@pytest.mark.parametrize("source", [
    "[,]", "[1,]", "[,1]", "[1 2]", "[[1]]", "[len(body)]", "[body]", "[method]", "[1", "1]",
    "[1,,2]", "1", '"a"', "",
])
def test_malformed_lists(source):
    assert_syntax_error(f"r := p: method in {source}")


# ---------------------------------------
# whitespace and layout
# ---------------------------------------

@pytest.mark.parametrize("text", [
    "r:=p:exists(query)",
    'r := p: method=="GET"',
    "r := p: len(body)>1",
    "r := p: len(body)>=-1",
    'r := p: method in["a","b"]',
    "r := p: exists(query)and exists(path)",
    "r := p: exists(query) and(exists(path))",
    "r := p: not(exists(query))",
    "r := p: exists(query)or(exists(path))",
    'r := p: method in["a"]and exists(query)',
    "  r := p: exists(query)  ",
    "r :=\r\n\tp:\texists(query)\r\n",
    "r\n:=\np\n:\nexists\n(\nquery\n)",
])
def test_whitespace_is_free_where_tokens_are_separated_anyway(text):
    assert isinstance(parse(text), Rule)


@pytest.mark.parametrize("text", [
    "r := p: notexists(query)",
    "r := p: exists(query)andexists(path)",
    "r := p: exists(query) aand exists(path)",
    "r := p: exists(query) andexists(path)",
    'r := p: method in"a"',
    'r := p: method startswith "a"',
    "r := p: len(body)>1>0",
])
def test_keywords_must_be_separate_words(text):
    assert_syntax_error(text)


@pytest.mark.parametrize("text", [
    'r := p: METHOD == "x"',
    "r := p: EXISTS(query)",
    "r := p: exists(query) AND exists(path)",
    "r := p: exists(query) Or exists(path)",
    "r := p: Not exists(query)",
    'r := p: method IN ["a"]',
    'r := p: path MATCHES "x"',
])
def test_language_is_case_sensitive(text):
    assert_syntax_error(text)


def test_multiple_predicates_keep_order():
    r = parse('r := a: method == "GET",\n  b: len(body) >= 1 ,\tc: path matches "x"')
    assert r.name == "r"
    assert [p.name for p in r.predicates] == ["a", "b", "c"]
    assert isinstance(r.predicates[1].expression, Comparison)


def test_commas_between_predicates_do_not_leak_into_expressions():
    r = parse('r := a: method in ["x", "y"], b: exists(query)')
    assert r.predicates[0].expression.right == ListLit((String("x"), String("y")))
    assert r.predicates[1].expression == A


# ---------------------------------------
# structural errors
# ---------------------------------------

@pytest.mark.parametrize("text", [
    # rule / predicate skeleton
    "r p: exists(query)",
    "r = p: exists(query)",
    "r := : exists(query)",
    "r := p exists(query)",
    "r := p:",
    "r := p: exists(query),",
    "r := p: exists(query) extra",
    "r := p: exists(query);",
    "r := a: exists(query) b := q: exists(path)",
    "1r := p: exists(query)",
    "r-x := p: exists(query)",
    "r := 1p: exists(query)",
    "r.x := p: exists(query)",
    "п := p: exists(query)",
    # logic
    "r := p: exists(query) and",
    "r := p: and exists(query)",
    "r := p: exists(query) or or exists(path)",
    "r := p: not",
    "r := p: ()",
    "r := p: (exists(query)",
    "r := p: exists(query))",
    "r := p: ) exists(query)",
    # comparisons
    "r := p: method ==",
    'r := p: == "x"',
    'r := p: method == == "x"',
    'r := p: method = "x"',
    'r := p: method <> "x"',
    'r := p: method == "a" == "b"',
    # calls and paths
    "r := p: len",
    "r := p: len(",
    "r := p: len)",
    "r := p: len(,)",
    "r := p: len(1,)",
    "r := p: len(1 2)",
    "r := p: foo(1)",
    "r := p: LEN(body)",
    "r := p: body.1 == 1",
    "r := p: body. == 1",
    "r := p: body..a == 1",
    "r := p: body.a. == 1",
    "r := p: body.a-b == 1",
    'r := p: body."a" == 1',
    "r := p: body.a b",
    "r := p: query.a == 1",
    "r := p: method.a == 1",
    # strings
    'r := p: path == "abc',
    r'r := p: path == "abc\"',
    'r := p: path == abc"',
    # characters outside the language
    "r := p: exists(query) # comment",
    "r := p: exists(query) @",
    "r := p: path == 'single'",
])
def test_invalid_input_raises_dsl_syntax_error(text):
    assert_syntax_error(text)


@pytest.mark.parametrize("text", ["", "   ", "\n\n", "r :=", "r := p:", "r := p: (exists(query)", "r := p: exists("])
def test_truncated_input_raises_dsl_syntax_error(text):
    assert_syntax_error(text)


# ---------------------------------------
# DslSyntaxError
# ---------------------------------------

@pytest.mark.parametrize("text, line, column, found", [
    ('r := p: method in "GET"', 1, 19, '"GET"'),
    ("r := p method", 1, 8, "method"),
    ("r := p: exists(query) @", 1, 23, "@"),
    ("r := p: exists(query) and and exists(path)", 1, 27, "and"),
    ('r := a: method == "GET",\n  b: len(1,) > 0', 2, 12, ")"),
    ("r := p: exists(query)\n  and\n    @", 3, 5, "@"),
])
def test_syntax_error_points_at_the_offending_input(text, line, column, found):
    e = assert_syntax_error(text)
    assert (e.line, e.column) == (line, column)
    assert repr(found) in e.message
    assert f"line {line}" in str(e)
    # the context snippet has a caret under the offending column
    assert e.context.splitlines()[-1].index("^") + 1 == column


def test_syntax_error_lists_what_was_expected():
    e = assert_syntax_error('r := p: method in "GET"')
    assert "expected" in e.message
    assert "LSQB" in e.message          # the '[' that 'in' needs


def test_dsl_syntax_error_is_a_value_error():
    assert issubclass(DslSyntaxError, ValueError)


def test_dsl_syntax_error_without_position():
    e = DslSyntaxError("boom")
    assert e.message == "boom"
    assert e.line is None and e.column is None and e.context == ""
    assert "boom" in str(e)
    assert "None" not in str(e)


def test_dsl_syntax_error_with_position_and_context():
    e = DslSyntaxError("boom", 3, 7, "ctx")
    assert (e.line, e.column, e.context) == (3, 7, "ctx")
    assert "boom" in str(e) and "3" in str(e) and "7" in str(e) and "ctx" in str(e)


# ---------------------------------------
# AST hygiene
# ---------------------------------------

def _leaves(node):
    if dataclasses.is_dataclass(node):
        for f in dataclasses.fields(node):
            yield from _leaves(getattr(node, f.name))
    elif isinstance(node, tuple):
        for item in node:
            yield from _leaves(item)
    else:
        yield node


_BIG_RULE = (
    'big := a: method in ["a", 1, 2.5, True] and not (len(lower(header("X"))) >= -1 '
    'or body.a.b matches "x" or path starts_with "/"), b: exists(query)'
)


def test_ast_contains_no_lark_tokens_or_str_subclasses():
    for leaf in _leaves(parse(_BIG_RULE)):
        assert not isinstance(leaf, Token), leaf
        if isinstance(leaf, str):
            assert type(leaf) is str, leaf


def test_ast_collections_are_tuples():
    r = parse(_BIG_RULE)
    assert isinstance(r.predicates, tuple)
    first = r.predicates[0].expression
    assert isinstance(first.expressions, tuple)


def test_parsing_twice_gives_equal_hashable_results():
    a, b = parse(_BIG_RULE), parse(_BIG_RULE)
    assert a == b
    assert hash(a) == hash(b)
    assert len({a, b}) == 1


def test_different_texts_give_different_results():
    assert parse("r := p: exists(query)") != parse("r := p: exists(path)")
    assert parse("r := p: exists(query)") != parse("r := q: exists(query)")
    assert parse("r := p: exists(query)") != parse("s := p: exists(query)")


def test_parser_is_reusable_after_errors():
    good = parse("r := p: exists(query)")
    for text in ("r := p: ", "r :=", "r := p: method in 1"):
        assert_syntax_error(text)
        assert parse("r := p: exists(query)") == good


# ---------------------------------------
# size
# ---------------------------------------

def test_long_flat_inputs():
    n = 1000
    assert len(expr(" and ".join(["exists(query)"] * n)).expressions) == n
    assert len(expr(" or ".join(["exists(query)"] * n)).expressions) == n
    assert len(expr(f"method in [{', '.join(['1'] * n)}]").right.values) == n
    r = parse("r := " + ", ".join(f"p{i}: exists(query)" for i in range(n)))
    assert len(r.predicates) == n


@pytest.mark.parametrize("text", [
    "not " * 100 + "exists(query)",
    "len(" * 100 + "body" + ")" * 100 + " > 1",
    "(exists(query) and " * 100 + "exists(path)" + ")" * 100,
    "(" * 1000 + "exists(query)" + ")" * 1000,
], ids=["not-x100", "calls-x100", "parens-x100", "parens-x1000"])
def test_reasonable_nesting_parses(text):
    assert isinstance(parse(f"r := p: {text}"), Rule)


def test_nesting_depth_is_preserved():
    node = expr("not " * 50 + "exists(query)")
    depth = 0
    while isinstance(node, NotExpr):
        node, depth = node.expression, depth + 1
    assert depth == 50 and node == A


# ---------------------------------------
# known defects (xfail strict: remove the marker once fixed)
# ---------------------------------------

_LITERAL_EVAL = ("ASTBuilder.string uses ast.literal_eval, which is stricter than the grammar's "
                 "STRING terminal, so the failure escapes as lark VisitError instead of DslSyntaxError")


@pytest.mark.parametrize("text", [
    pytest.param(r'r := p: path == "\x"', id="truncated-hex-escape",
                 marks=pytest.mark.xfail(strict=True, reason=_LITERAL_EVAL)),
    pytest.param(r'r := p: path == "\u12"', id="truncated-unicode-escape",
                 marks=pytest.mark.xfail(strict=True, reason=_LITERAL_EVAL)),
    pytest.param('r := p: path == "a\nb"', id="raw-newline-in-string",
                 marks=pytest.mark.xfail(strict=True, reason=_LITERAL_EVAL)),
    pytest.param("r := p: " + "not " * 5000 + "exists(query)", id="not-x5000",
                 marks=pytest.mark.xfail(strict=True, reason=(
                     "ASTBuilder is a recursive Transformer, deep trees raise RecursionError; "
                     "lark.visitors.Transformer_NonRecursive is a drop-in base class"))),
    pytest.param("r := p: method == 1", id="sanity-valid-input"),
])
def test_bad_input_never_leaks_foreign_exceptions(text):
    """the result is either a Rule or a DslSyntaxError, never VisitError / RecursionError"""
    assert isinstance(parse_or_syntax_error(text), (Rule, DslSyntaxError))


@pytest.mark.xfail(strict=True, reason=(
    "ast.literal_eval warns about escapes it does not know ('\\d', '\\.'): "
    "SyntaxWarning since Python 3.12, a hard error in a future version. "
    "These escapes are the whole point of 'matches'"))
def test_regex_escapes_in_matches_do_not_warn():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        e = expr(r'path matches "^/users/\d+\.json$"')
    assert e.right == String(r"^/users/\d+\.json$")      # unknown escapes keep their backslash
    assert [w for w in caught if issubclass(w.category, (SyntaxWarning, DeprecationWarning))] == []


@pytest.mark.xfail(strict=True, reason=(
    "UnexpectedEOF is raised by Earley only; LALR reports the end as UnexpectedToken('$END'), "
    "so the 'unexpected end of input' branch of _to_syntax_error is unreachable"))
@pytest.mark.parametrize("text", ["r := p: method ==", "r := p: (exists(query)", "r :="])
def test_truncated_input_says_so(text):
    assert "end of input" in assert_syntax_error(text).message
