"""
tests for the DSL evaluator (parser -> AST -> Evaluator.evaluate).
limits (limits.py) are not covered yet.

run from the project root:  python -m pytest tests -v
"""
import dataclasses

import pytest

from apivalidator.dsl.parser import parse, DslSyntaxError
from apivalidator.dsl.dslast import String, Number
from apivalidator.dsl.evaluator import (
    Evaluator, Request, Verdict, Caller,
    DslComparisonError, DslCallError, _MISSING,
)


# ---------------------------------------
# helpers
# ---------------------------------------

def R(**overrides) -> Request:
    """request with sensible defaults; override only what a test needs"""
    base = dict(method="GET", path="/api/v1/users")
    base.update(overrides)
    return Request(**base)


def run(expr: str, req: Request) -> Verdict:
    """parses 'r := p: <expr>' and evaluates it"""
    return Evaluator().evaluate(parse(f"r := p: {expr}"), req)


def sat(expr: str, req: Request) -> bool:
    return run(expr, req).satisfied


# ---------------------------------------
# Request model
# ---------------------------------------

class TestRequest:
    def test_method_is_upper_cased(self):
        assert Request("get", "/").method == "GET"

    def test_header_names_are_lower_cased(self):
        req = Request("GET", "/", headers={"Content-Type": "x", "X-NAME": "y"})
        assert dict(req.headers) == {"content-type": "x", "x-name": "y"}

    def test_header_lookup_is_case_insensitive(self):
        req = Request("GET", "/", headers={"Content-Type": "x"})
        assert req.header("content-type") == "x"
        assert req.header("CONTENT-TYPE") == "x"
        assert req.header("Content-Type") == "x"

    def test_absent_header_is_missing(self):
        assert Request("GET", "/").header("X-Nope") is _MISSING

    def test_body_defaults_to_missing(self):
        assert Request("GET", "/").body is _MISSING

    def test_body_at_empty_path_returns_whole_body(self):
        assert R(body={"a": 1}).body_at(()) == {"a": 1}

    def test_body_at_walks_nested_keys(self):
        assert R(body={"a": {"b": {"c": 5}}}).body_at(("a", "b", "c")) == 5

    def test_body_at_absent_key_is_missing(self):
        assert R(body={"a": 1}).body_at(("b",)) is _MISSING

    def test_body_at_through_non_dict_is_missing(self):
        assert R(body={"a": [1, 2]}).body_at(("a", "x")) is _MISSING
        assert R(body={"a": 5}).body_at(("a", "x")) is _MISSING

    def test_body_at_without_body_is_missing(self):
        assert R().body_at(("a",)) is _MISSING

    def test_request_is_immutable(self):
        with pytest.raises(dataclasses.FrozenInstanceError):
            R().method = "POST"

    def test_missing_is_falsy_and_has_repr(self):
        assert not _MISSING
        assert repr(_MISSING) == "MISSING"


# ---------------------------------------
# fields
# ---------------------------------------

class TestFields:
    def test_method(self):
        assert sat('method == "GET"', R())
        assert not sat('method == "POST"', R())

    def test_method_input_case_does_not_matter(self):
        assert sat('method == "GET"', R(method="get"))

    def test_path(self):
        assert sat('path == "/api/v1/users"', R())
        assert not sat('path == "/other"', R())

    def test_body_scalar_types(self):
        body = {"s": "x", "n": 10, "f": 1.5, "b": True}
        assert sat('body.s == "x"', R(body=body))
        assert sat("body.n == 10", R(body=body))
        assert sat("body.f == 1.5", R(body=body))
        assert sat("body.b == True", R(body=body))

    def test_body_nested_path(self):
        assert sat("body.a.b.c == 5", R(body={"a": {"b": {"c": 5}}}))

    def test_body_absent_path_is_not_satisfied_without_error(self):
        v = run("body.nope == 1", R(body={"a": 1}))
        assert v.satisfied is False

    def test_body_not_provided_is_not_satisfied_without_error(self):
        assert sat("body.x == 1", R()) is False

    def test_body_bool_is_not_confused_with_number(self):
        # bool is a subclass of int in python; True must stay a boolean
        assert sat("body.b == True", R(body={"b": True}))
        with pytest.raises(DslComparisonError):
            sat("body.b == 1", R(body={"b": True}))

    def test_body_null_is_not_comparable(self):
        with pytest.raises(DslComparisonError):
            sat("body.x == 1", R(body={"x": None}))

    def test_body_unsupported_value_type(self):
        with pytest.raises(DslComparisonError):
            sat("body.x == 1", R(body={"x": object()}))


# ---------------------------------------
# symbol comparisons
# ---------------------------------------

class TestComparisons:
    @pytest.mark.parametrize("expr, expected", [
        ("body.n > 5", True),
        ("body.n > 10", False),
        ("body.n >= 10", True),
        ("body.n >= 11", False),
        ("body.n < 11", True),
        ("body.n < 10", False),
        ("body.n <= 10", True),
        ("body.n <= 9", False),
        ("body.n == 10", True),
        ("body.n == 11", False),
        ("body.n != 11", True),
        ("body.n != 10", False),
        ("body.n > -1", True),
        ("body.n > 9.5", True),
    ])
    def test_numbers(self, expr, expected):
        assert sat(expr, R(body={"n": 10})) is expected

    @pytest.mark.parametrize("expr, expected", [
        ('body.s == "bob"', True),
        ('body.s != "bob"', False),
        ('body.s < "carl"', True),
        ('body.s > "alice"', True),
        ('body.s >= "bob"', True),
        ('body.s <= "bob"', True),
        ('body.s > "carl"', False),
    ])
    def test_strings(self, expr, expected):
        assert sat(expr, R(body={"s": "bob"})) is expected

    def test_booleans_support_only_equality(self):
        req = R(body={"b": True})
        assert sat("body.b == True", req)
        assert sat("body.b != False", req)
        assert not sat("body.b == False", req)
        with pytest.raises(DslComparisonError):
            sat("body.b > False", req)

    def test_different_kinds_cannot_be_compared(self):
        with pytest.raises(DslComparisonError):
            sat('body.n == "10"', R(body={"n": 10}))
        with pytest.raises(DslComparisonError):
            sat("method == 1", R())

    def test_literal_on_both_sides(self):
        assert sat("1 == 1", R())
        assert sat("2 > 1", R())
        assert sat('"a" == "a"', R())
        assert not sat('"a" == "b"', R())

    def test_escaped_quote_in_string_literal(self):
        assert sat(r'body.s == "a\"b"', R(body={"s": 'a"b'}))

    def test_function_result_on_the_right_side(self):
        assert sat('method == lower("GET")', R()) is False  # 'GET' != 'get'
        assert sat('lower(method) == lower("GET")', R())


# ---------------------------------------
# word operators
# ---------------------------------------

class TestWordOperators:
    def test_in(self):
        assert sat('method in ["GET", "POST"]', R())
        assert not sat('method in ["POST", "PUT"]', R())

    def test_in_numbers(self):
        assert sat("body.n in [1, 10]", R(body={"n": 10}))
        assert not sat("body.n in [1, 2]", R(body={"n": 10}))

    def test_in_empty_list(self):
        assert not sat("method in []", R())

    def test_not_in(self):
        assert sat('not method in ["POST"]', R())

    def test_in_requires_scalar_on_the_left(self):
        with pytest.raises(DslComparisonError):
            sat('body.items in ["a"]', R(body={"items": [1, 2]}))

    def test_starts_with(self):
        assert sat('path starts_with "/api"', R())
        assert not sat('path starts_with "/admin"', R())

    def test_starts_with_accepts_a_call_on_the_right(self):
        assert sat('path starts_with lower("/API")', R())

    def test_starts_with_requires_strings(self):
        with pytest.raises(DslComparisonError):
            sat('body.n starts_with "1"', R(body={"n": 10}))

    def test_matches(self):
        assert sat('path matches "^/api/v[0-9]+/"', R())
        assert not sat('path matches "^/admin"', R())

    def test_matches_is_anchored_at_the_start_only(self):
        # documents re.match semantics: not a search, not a full match
        assert sat('path matches "/api"', R())
        assert not sat('path matches "users"', R())

    def test_matches_requires_strings(self):
        with pytest.raises(DslComparisonError):
            sat('body.n matches "1"', R(body={"n": 10}))


# ---------------------------------------
# functions
# ---------------------------------------

class TestFunctions:
    # lower
    def test_lower(self):
        assert sat('lower(method) == "get"', R())
        assert sat('lower(header("X-Name")) == "alice"', R(headers={"X-Name": "ALICE"}))

    def test_lower_rejects_non_string(self):
        with pytest.raises(DslCallError):
            sat("lower(body.n) == 1", R(body={"n": 10}))

    # len
    def test_len_of_string(self):
        assert sat("len(body.name) == 5", R(body={"name": "alice"}))
        assert sat('len("abc") == 3', R())

    def test_len_of_list(self):
        assert sat("len(body.items) == 3", R(body={"items": [1, 2, 3]}))
        assert sat("len(body.items) > 0", R(body={"items": [{"a": 1}]}))
        assert sat("len(body.items) == 0", R(body={"items": []}))

    def test_len_of_top_level_list_body(self):
        assert sat("len(body) == 2", R(body=[1, 2]))

    def test_len_of_dict(self):
        assert sat("len(body.obj) == 2", R(body={"obj": {"a": 1, "b": 2}}))
        assert sat("len(query) == 2", R(query={"a": ("1",), "b": ("2",)}))

    def test_len_rejects_unsized(self):
        with pytest.raises(DslCallError):
            sat("len(body.n) == 1", R(body={"n": 10}))

    # int
    def test_int(self):
        req = R(headers={"Content-Length": "120"})
        assert sat('int(header("Content-Length")) < 1000', req)
        assert not sat('int(header("Content-Length")) < 100', req)

    def test_int_invalid_string(self):
        with pytest.raises(DslCallError):
            sat('int(header("Content-Length")) < 1', R(headers={"Content-Length": "abc"}))

    def test_int_rejects_non_string(self):
        with pytest.raises(DslCallError):
            sat("int(body.n) == 1", R(body={"n": 10}))

    # header
    def test_header(self):
        req = R(headers={"Content-Type": "application/json"})
        assert sat('header("content-type") == "application/json"', req)
        assert sat('header("Content-Type") == "application/json"', req)
        assert sat('header("CONTENT-TYPE") == "application/json"', req)

    def test_header_name_must_be_string(self):
        with pytest.raises(DslCallError):
            sat("header(1) == 1", R())

    # exists
    def test_exists_header(self):
        assert sat('exists(header("X-Name"))', R(headers={"X-Name": "a"}))
        assert not sat('exists(header("X-Name"))', R())

    def test_exists_body_key(self):
        assert sat("exists(body.a)", R(body={"a": 1}))
        assert not sat("exists(body.b)", R(body={"a": 1}))
        assert not sat("exists(body.a)", R())

    def test_exists_treats_json_null_as_present(self):
        assert sat("exists(body.a)", R(body={"a": None}))

    def test_exists_query(self):
        assert sat("exists(query)", R(query={"a": ("1",)}))
        assert not sat("exists(query)", R())

    def test_exists_nested_missing_through_list(self):
        assert not sat("exists(body.items.a)", R(body={"items": [{"a": 1}]}))

    def test_exists_arity(self):
        with pytest.raises(DslCallError):
            sat("exists()", R())
        with pytest.raises(DslCallError):
            sat("exists(method, path)", R())

    def test_wrong_arity_for_other_functions(self):
        with pytest.raises(DslCallError):
            sat("lower() == 1", R())
        with pytest.raises(DslCallError):
            sat('lower("a", "b") == "a"', R())

    def test_caller_exists_directly(self):
        c, req = Caller(), R()
        assert c.call_exists((String("x"),), req).value is True
        assert c.call_exists((_MISSING,), req).value is False
        assert c.call_exists(({},), req).value is False

    def test_caller_len_directly(self):
        assert Caller().call_len((String("abcd"),), R()) == Number(4)


# ---------------------------------------
# missing values in comparisons
# ---------------------------------------

class TestMissingValues:
    @pytest.mark.parametrize("expr", [
        'header("X-Nope") == "a"',
        'header("X-Nope") != "a"',
        'header("X-Nope") in ["a"]',
        'header("X-Nope") starts_with "a"',
        'header("X-Nope") matches "a"',
        'method == header("X-Nope")',
    ])
    def test_comparison_with_absent_value_is_unsatisfied(self, expr):
        v = run(expr, R())
        assert v.satisfied is False
        assert v.what and "missing" in v.what[0]

    def test_int_of_absent_header_raises(self):
        # currently a call error, not an unsatisfied verdict
        with pytest.raises(DslCallError):
            sat('int(header("X-Nope")) > 5', R())

    @pytest.mark.xfail(strict=True, reason="and does not short-circuit, so exists() "
                                           "cannot guard a call that fails on a missing value")
    def test_exists_guard_protects_following_call(self):
        assert sat('exists(header("X-Nope")) and int(header("X-Nope")) > 5', R()) is False


# ---------------------------------------
# logic
# ---------------------------------------

class TestLogic:
    def test_and(self):
        assert sat('method == "GET" and path starts_with "/api"', R())
        assert not sat('method == "GET" and path starts_with "/x"', R())
        assert not sat('method == "POST" and path starts_with "/x"', R())

    def test_or(self):
        assert sat('method == "POST" or path starts_with "/api"', R())
        assert not sat('method == "POST" or path starts_with "/x"', R())

    def test_not(self):
        assert sat('not method == "POST"', R())
        assert not sat('not method == "GET"', R())

    def test_double_not(self):
        assert sat('not not method == "GET"', R())

    def test_not_exists(self):
        assert sat('not exists(header("X-Nope"))', R())

    def test_and_binds_tighter_than_or(self):
        # True or (True and False) -> True
        assert sat('method == "GET" or method == "POST" and path == "/nope"', R())

    def test_parentheses_change_grouping(self):
        # (True or True) and False -> False
        assert not sat('(method == "GET" or method == "POST") and path == "/nope"', R())

    def test_not_binds_tighter_than_or(self):
        assert sat('not method == "GET" or path == "/api/v1/users"', R())
        assert not sat('not (method == "GET" or path == "/api/v1/users")', R())

    def test_three_operands(self):
        assert sat('method == "GET" and path starts_with "/api" and exists(query)',
                   R(query={"a": ("1",)}))
        assert not sat('method == "GET" and path starts_with "/api" and exists(query)', R())

    def test_bare_boolean_literals(self):
        assert sat("True", R())
        assert not sat("False", R())

    def test_unary_operand_must_be_boolean(self):
        with pytest.raises(DslComparisonError):
            sat("method", R())
        with pytest.raises(DslComparisonError):
            sat("1", R())
        with pytest.raises(DslComparisonError):
            sat("len(body.s)", R(body={"s": "abc"}))

    def test_unary_boolean_field(self):
        assert sat("body.flag", R(body={"flag": True}))
        assert not sat("body.flag", R(body={"flag": False}))


# ---------------------------------------
# rules, predicates and verdicts
# ---------------------------------------

class TestRules:
    def evaluate(self, text: str, req: Request) -> Verdict:
        return Evaluator().evaluate(parse(text), req)

    def test_all_predicates_satisfied(self):
        v = self.evaluate('r := a: method == "GET", b: path starts_with "/api"', R())
        assert v.satisfied is True

    def test_one_failing_predicate_fails_the_rule(self):
        v = self.evaluate('r := a: method == "GET", b: path starts_with "/admin"', R())
        assert v.satisfied is False

    def test_stops_at_first_failing_predicate(self):
        # the second predicate would raise (len of a number) if it were evaluated
        v = self.evaluate('r := a: method == "POST", b: len(body.n) > 1', R(body={"n": 10}))
        assert v.satisfied is False

    def test_error_in_a_reached_predicate_propagates(self):
        with pytest.raises(DslCallError):
            self.evaluate('r := a: method == "GET", b: len(body.n) > 1', R(body={"n": 10}))

    def test_satisfied_verdict_has_no_reasons(self):
        assert run('method == "GET"', R()).what is None

    def test_failed_comparison_explains_itself(self):
        v = run('method == "POST"', R())
        assert v.what == ["'GET' == 'POST' is not true"]

    def test_failed_in_explains_itself(self):
        v = run('method in ["POST", "PUT"]', R())
        assert v.what == ["'GET' in ['POST', 'PUT'] is not true"]

    def test_and_collects_reasons_of_all_failed_operands(self):
        v = run('method == "POST" and path == "/x"', R())
        assert v.satisfied is False
        assert len(v.what) == 2

    def test_or_collects_reasons_when_everything_fails(self):
        v = run('method == "POST" or path == "/x"', R())
        assert v.satisfied is False
        assert len(v.what) == 2

    def test_unknown_expression_node(self):
        with pytest.raises(ValueError):
            Evaluator().resolve_expression(object(), R())


# ---------------------------------------
# parser integration
# ---------------------------------------

class TestSyntax:
    @pytest.mark.parametrize("text", [
        "garbage",
        "r := p:",
        'r := p: method ==',
        'r := p: method == "GET" and',
        'r := p: foo(method)',
        'r := p: (method == "GET"',
        'r := p: method in "GET"',
        'r := p: path matches 5',
    ])
    def test_syntax_errors(self, text):
        with pytest.raises(DslSyntaxError):
            parse(text)

    def test_syntax_error_carries_position(self):
        with pytest.raises(DslSyntaxError) as info:
            parse('r := p: method ==')
        assert info.value.line is not None
