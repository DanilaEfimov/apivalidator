from apivalidator.dsl.dslast import *
from apivalidator.dsl.grammar import AllowedComp, AllowedField, AllowedFunc, AllowedOperator
from apivalidator.dsl.parser import DslSyntaxError, parse


def pred_expr(text):
    return parse(text).predicates[0].expression


def test_simple_comparison():
    e = pred_expr('r := p: method == "GET"')
    assert e == Comparison(Field(AllowedField.METHOD), AllowedComp.EQ, String("GET"))


def test_bare_operand():
    e = pred_expr("r := p: exists(query)")
    assert e == Comparison(Call(Func(AllowedFunc.EXISTS), (Field(AllowedField.QUERY),)))


def test_call_without_args():
    e = pred_expr("r := p: exists()")
    assert e.left == Call(Func(AllowedFunc.EXISTS), ())


def test_in_list_and_empty_list():
    e = pred_expr('r := p: method in ["GET", "POST", 1, 2.5, True]')
    assert e.op is AllowedOperator.IN
    assert e.right == ListLit((String("GET"), String("POST"), Number(1), Number(2.5), Bool(True)))
    assert pred_expr("r := p: method in []").right == ListLit(())


def test_false_literal():
    assert pred_expr("r := p: exists(query) == False").right == Bool(False)


def test_matches_starts_with():
    assert pred_expr('r := p: path matches "^/api"').op is AllowedOperator.MATCHES
    e = pred_expr('r := p: path starts_with header("x")')
    assert e.op is AllowedOperator.STARTS_WITH and isinstance(e.right, Call)


def test_body_path():
    e = pred_expr("r := p: body.user.name == \"a\"")
    assert e.left == Field(AllowedField.BODY, ("user", "name"))
    assert pred_expr("r := p: body").left == Field(AllowedField.BODY)


def test_keywords_as_path_parts_and_names():
    e = pred_expr("r := p: body.in.and == 1")
    assert e.left.path == ("in", "and")
    r = parse("index := inbound: method == \"GET\"")
    assert r.name == "index" and r.predicates[0].name == "inbound"


def test_logic_structure_and_precedence():
    e = pred_expr("r := p: exists(query) or exists(body) and not exists(path)")
    assert isinstance(e, OrExpr) and len(e.expressions) == 2
    assert isinstance(e.expressions[1], AndExpr)
    assert isinstance(e.expressions[1].expressions[1], NotExpr)


def test_not_is_not_lost_and_double_not():
    e = pred_expr("r := p: not not exists(query)")
    assert isinstance(e, NotExpr) and isinstance(e.expression, NotExpr)
    assert isinstance(e.expression.expression, Comparison)


def test_parentheses():
    e = pred_expr("r := p: (exists(query) or exists(body)) and exists(path)")
    assert isinstance(e, AndExpr) and isinstance(e.expressions[0], OrExpr)
    assert isinstance(pred_expr("r := p: (exists(query))"), Comparison)    # no degenerate wrappers


def test_multiple_preds():
    r = parse('r := a: method == "GET", b: len(body.items) >= 1, c: path matches "x"')
    assert [p.name for p in r.predicates] == ["a", "b", "c"]


def test_string_escapes():
    assert pred_expr(r'r := p: path == "a\"b\\c"').right == String('a"b\\c')


def test_negative_number_and_comparators():
    for sym, enum in [(">=", AllowedComp.GE), ("<=", AllowedComp.LE), ("==", AllowedComp.EQ),
                      ("!=", AllowedComp.NEQ), ("<", AllowedComp.LT), (">", AllowedComp.GT)]:
        e = pred_expr(f"r := p: len(body) {sym} -3")
        assert e.op is enum and e.right == Number(-3)


def test_nodes_are_hashable():
    hash(parse('r := p: method in ["GET", "POST"] and not exists(query)'))


def test_whitespace_and_newlines():
    parse('r :=\n  a: method == "GET",\n  b: exists(query)\n')


def test_errors_have_position():
    bad = [
        'r := p: method == ',              # eof
        'r := p: method in "GET"',         # in needs a list
        'r := p: path matches 5',          # matches needs a string
        'r := p: len(1,) > 0',             # trailing comma
        'r := p: (exists(query)',          # missing bracket
        'r := p: unknown(1)',              # not a function
        'r := p: method == "a',            # unterminated string
        'r := ',                           # no preds
        'r := p: method == "GET" and',
        'r := p: method @ 1',
    ]
    for text in bad:
        try:
            parse(text)
        except DslSyntaxError as e:
            assert e.line is not None or "end of input" in e.message, text
        else:
            raise AssertionError(f"should not parse: {text!r}")


if __name__ == "__main__":
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_")]
    for name, fn in tests:
        fn()
        print("ok  ", name)
    print(f"{len(tests)} passed")