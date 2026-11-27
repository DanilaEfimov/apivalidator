import regex
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional, Union, Tuple, Mapping
from apivalidator.dsl.dslast import *
from apivalidator.dsl.grammar import AllowedComp, AllowedOperator, AllowedFunc, AllowedField
from apivalidator.dsl.limits import *


class Missing:
    """
    marker type for a value that is absent from the request
    (a missing header, a missing body key).
    differs from None, which is a real JSON null.
    falsy, so it can be checked with 'if not value'
    """

    def __repr__(self): return "MISSING"

    def __bool__(self): return False


_MISSING = Missing()


@dataclass(frozen=True)
class Request:
    """
    the http request the rules are checked against.
    immutable, so one request can be safely reused across rules and predicates
    """
    method: str
    path: str
    query: Mapping[str, Tuple[str, ...]] = field(default_factory=dict)
    headers: Mapping[str, str] = field(default_factory=dict)
    body: Any = _MISSING

    def __post_init__(self):
        """
        normalize: the method to upper case, header names to lower case
        """
        object.__setattr__(self, "method", self.method.upper())
        object.__setattr__(self, "headers", {k.lower(): v for k, v in self.headers.items()})

    def header(self, name: str) -> Any:
        """
        looks up a request header by name (case-insensitive).
        header names are stored in lower case (see __post_init__)
        :param name: header name
        :return: header value, or _MISSING if there is no such header
        """
        return self.headers.get(name.lower(), _MISSING)

    def body_at(self, path: Tuple[str, ...]) -> Any:
        """
        walks the parsed body by a chain of dict keys,
        e.g. ('user', 'name') for 'body.user.name'
        :param path: keys to follow, empty tuple means the whole body
        :return: the value at the path, or _MISSING if any key is absent
                 or an intermediate value is not a dict
        """
        cur = self.body
        for key in path:
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
            else:
                return _MISSING
        return cur


@dataclass
class Verdict:
    """
    result of evaluating an expression, predicate or rule
    """
    satisfied: bool
    what: List[str] | None = None  # human-readable reasons of failure, None if there is nothing to report


class DslComparisonError(ValueError):
    """
    semantic error while evaluating a comparison
    (for example an operand of an unexpected type).
    optionally carries the rule and the predicate where it happened
    """

    def __init__(self, message: str,
                 pred: Optional[str] = None,
                 rule: Optional[str] = None,
                 context: str = ""):
        """
        :param message: error description
        :param pred: name of the predicate where the error happened
        :param rule: name of the rule where the error happened
        :param context: extra context shown on a new line after the message
        """
        if rule is not None:
            where = f"(rule: {rule}"
            if pred is not None:
                where += f", predicate: {pred}"
            where += ")"
        else:
            where = ""

        super().__init__(f"{message} {where}" + f"\n{context if context else ''}")
        self.message = message
        self.pred = pred
        self.rule = rule
        self.context = context


class DslCallError(ValueError):
    """
    error while calling a DSL function
    (unknown function, wrong number or type of arguments).
    optionally carries what was expected and what was actually given
    """

    def __init__(self, message: str,
                 expected: str | None = None,
                 given: str | None = None,
                 context: str = ""):
        """
        :param message: error description
        :param expected: what the function expects, e.g. 'one string argument'
        :param given: what the function actually received
        :param context: extra context shown on a new line after the message
        """
        details = []
        if expected is not None:
            details.append(f"expected: {expected}")
        if given is not None:
            details.append(f"given: {given}")

        where = f"({', '.join(details)})" if details else ""

        full = f"{message} {where}".rstrip()
        if context:
            full += f"\n{context}"

        super().__init__(full)
        self.message = message
        self.expected = expected
        self.given = given
        self.context = context


# any value an operand can be resolved to: a literal node, a list literal,
# a dict (query or a part of the body), _MISSING (absent value) or None (JSON null)
_VALUE = Union[Literal, ListLit, Dict, Missing, None]

_ARGS = Tuple[_VALUE, ...]


def _describe(value: Any) -> str:
    """
    short text form of a resolved value, used in failure reasons (Verdict.what)
    :param value: literal node, list literal or anything else
    :return: readable representation
    """
    if isinstance(value, ListLit):
        return repr([getattr(item, "value", item) for item in value.values])
    return repr(getattr(value, "value", value))


def _wrap(value: Any) -> _VALUE:
    """
    converts a raw python value taken from the parsed body into an AST value node,
    so that it can be passed to functions and comparisons like any literal.
    dicts stay raw (they are walked by key), lists become ListLit
    :param value: raw value (str, int, float, bool, list, dict, None) or _MISSING
    :return: String / Number / Bool / ListLit, a dict, None or _MISSING
    :raises DslComparisonError: if the value type is not supported
    """
    if value is _MISSING or value is None or isinstance(value, dict):
        return value
    if isinstance(value, (Bool, String, Number, ListLit)):
        return value
    if isinstance(value, bool):  # before int: bool is a subclass of int
        return Bool(value)
    if isinstance(value, (int, float)):
        return Number(value)
    if isinstance(value, str):
        return String(value)
    if isinstance(value, (list, tuple)):
        return ListLit(tuple(_wrap(item) for item in value))
    raise DslComparisonError(f"unsupported value type: {type(value).__name__}")


class LiteralValueType(Enum):
    """
    value types known to the call signatures.
    the member value is the AST node class (or a tuple of classes) of that type
    """
    BOOL = Bool
    STRING = String
    INT = Number
    LIST = ListLit
    BODY = dict
    SIZED = (String, ListLit, dict)
    VOID = None  # return type only


class CallSignature:
    """
    describes what a function accepts and returns:
    the list of argument types and the return type
    """

    def __init__(self, expects: List[LiteralValueType], returns: LiteralValueType):
        """
        :param expects: list of argument types
        :param returns: return value type
        """
        self.expects = expects
        self.returns = returns

    def args_match(self, args: _ARGS) -> bool:
        """
        checks the arguments against the signature: same count and same types, in order
        :param args: resolved argument values
        :return: True if the arguments fit the signature, False otherwise
        """
        if len(self.expects) != len(args):
            return False
        for arg, expected in zip(args, self.expects):
            if not self._matches(arg, expected):
                return False
        return True

    @staticmethod
    def _matches(arg: _VALUE, expected: LiteralValueType) -> bool:
        """
        checks that a resolved value is of the expected type
        :param arg: resolved value
        :param expected: expected type
        :return: True if the value is an instance of the type (or of any of its classes)
        """
        if expected is LiteralValueType.VOID:
            return False
        return isinstance(arg, expected.value)


_LOWER_SIGNATURE = CallSignature([LiteralValueType.STRING], LiteralValueType.STRING)
_LEN_SIGNATURE = CallSignature([LiteralValueType.SIZED], LiteralValueType.INT)
_INT_SIGNATURE = CallSignature([LiteralValueType.STRING], LiteralValueType.INT)
_HEADER_SIGNATURE = CallSignature([LiteralValueType.STRING], LiteralValueType.STRING)
# exists() has no signature: it takes any single value, including a missing one


class Caller:
    """
    implementations of the DSL functions (see AllowedFunc in grammar.py).
    each method receives the already resolved arguments and the request,
    and returns the resulting value.
    the grammar does not check arity or argument types, so every method
    has to validate its arguments itself and raise DslCallError on a mismatch
    """

    @staticmethod
    def _signature_assert(args: _ARGS, sign: CallSignature) -> None:
        """
        checks the arguments against the signature
        :param args: resolved argument values
        :param sign: expected signature
        :raises DslCallError: if the arguments do not match the signature
        """
        if not sign.args_match(args):
            raise DslCallError("call signature doesn't match given arguments",
                               ", ".join(t.name for t in sign.expects),
                               ", ".join(type(a).__name__ for a in args))

    def call_lower(self, args: _ARGS, req: Request) -> _VALUE:
        """
        lower(x): the string x converted to lower case
        :param args: exactly one argument, which must resolve to a string
        :param req: request being checked
        :return: lower-cased string
        """
        self._signature_assert(args, _LOWER_SIGNATURE)
        return_type = _LOWER_SIGNATURE.returns.value
        string = args[0].value
        return return_type(string.lower())

    def call_len(self, args: _ARGS, req: Request) -> _VALUE:
        """
        len(x): the length of x
        :param args: exactly one argument, which must resolve to a sized value (string, list, dict)
        :param req: request being checked
        :return: the length as a number
        """
        self._signature_assert(args, _LEN_SIGNATURE)
        return_type = _LEN_SIGNATURE.returns.value
        sized = args[0]
        if isinstance(sized, String):
            return return_type(len(sized.value))
        elif isinstance(sized, ListLit):
            return return_type(len(sized.values))
        else:
            return return_type(len(sized))

    def call_exists(self, args: _ARGS, req: Request) -> _VALUE:
        """
        exists(x): checks that x is present in the request.
        a missing value (absent header or body key) and an empty dict
        (e.g. a request without query parameters) do not exist
        :param args: exactly one argument (usually a field or a header call)
        :param req: request being checked
        :return: boolean literal, True if the value is present
        """
        if len(args) != 1:
            raise DslCallError("exists takes exactly one argument",
                               "1 argument",
                               f"{len(args)} arguments")
        value = args[0]
        if value is _MISSING:
            return Bool(False)
        if isinstance(value, dict) and not value:
            return Bool(False)
        return Bool(True)

    def call_int(self, args: _ARGS, req: Request) -> _VALUE:
        """
        int(x): the value x converted to an integer
        :param args: exactly one argument, which must be convertible to int
        :param req: request being checked
        :return: the integer as a number
        """
        self._signature_assert(args, _INT_SIGNATURE)
        return_type = _INT_SIGNATURE.returns.value
        try:
            converted = int(args[0].value)
        except ValueError:
            raise DslCallError("cannot convert value to int",
                               "a string with an integer",
                               repr(args[0].value)) from None
        return return_type(converted)

    def call_header(self, args: _ARGS, req: Request) -> _VALUE:
        """
        header(name): the value of the request header with the given name
        :param args: exactly one argument, the header name as a string
        :param req: request being checked
        :return: header value, or _MISSING for an absent header
        """
        self._signature_assert(args, _HEADER_SIGNATURE)
        return_type = _HEADER_SIGNATURE.returns.value
        name = args[0].value
        header = req.header(name)
        if header is _MISSING:
            return _MISSING
        return return_type(str(header))


class Comparator:
    """
    applies the symbol comparison operators (>=, <=, ==, !=, <, >)
    to two already resolved values.
    both sides must be literals of the same kind (two strings, two numbers, two booleans);
    ordering (>=, <=, <, >) is not defined for booleans
    """

    @staticmethod
    def compare(left: Literal, cmp: AllowedComp, right: Literal) -> Bool:
        """
        compares two literals with the given operator
        :param left: left value
        :param cmp: comparison operator
        :param right: right value
        :return: boolean literal with the result
        :raises DslComparisonError: if the operand kinds differ or the operator does not apply
        """
        if type(left) is not type(right):
            raise DslComparisonError(f"cannot compare {type(left).__name__} with {type(right).__name__}")

        l = left.value
        r = right.value
        if cmp == AllowedComp.EQ:
            return Bool(l == r)
        if cmp == AllowedComp.NEQ:
            return Bool(l != r)
        if isinstance(left, Bool):
            raise DslComparisonError(f"operator '{cmp.value}' does not apply to booleans")
        if cmp == AllowedComp.GE:
            return Bool(l >= r)
        if cmp == AllowedComp.GT:
            return Bool(l > r)
        if cmp == AllowedComp.LE:
            return Bool(l <= r)
        if cmp == AllowedComp.LT:
            return Bool(l < r)
        raise DslComparisonError(f"unknown comparison operator: {cmp}")


class Operating:
    """
    applies the word operators (in, starts_with, matches)
    to two already resolved values
    """

    @staticmethod
    def is_in(left: Literal, right: ListLit) -> Bool:
        """
        'in': checks that the left value equals one of the list items
        :param left: value to look for
        :param right: list literal to look in
        :return: True if the value is in the list
        """
        for item in right.values:
            if left.value == item.value:
                return Bool(value=True)
        return Bool(value=False)

    @staticmethod
    def does_start_with(left: String, right: String) -> Bool:
        """
        'starts_with': checks the prefix of a string
        :param left: the string to check
        :param right: the expected prefix
        :return: True if left starts with right
        """
        return Bool(left.value.startswith(right.value))

    @staticmethod
    def does_match(left: String, right: String) -> Bool:
        """
        'matches': checks a string against a regular expression
        :param left: the string to check
        :param right: the regular expression
        :return: True if the pattern matches (re.match, i.e. anchored at the start)
        """
        try:
            pattern = regex.compile(right.value)
            return Bool(pattern.match(left.value) is not None)
        except regex.PatternError as e:
            raise DslComparisonError(f"invalid regular expression: {right.value}") from None

    @staticmethod
    def operate(left: _VALUE, op: AllowedOperator, right: _VALUE) -> Bool:
        """
        validates the operand types and dispatches on the word operator
        :param left: left operand
        :param op: word operator
        :param right: right operand
        :return: boolean literal with the result
        :raises DslComparisonError: if the operand types do not fit the operator
        """
        if op == AllowedOperator.IN:
            if not isinstance(left, Literal) or not isinstance(right, ListLit):
                raise DslComparisonError(f"invalid arguments for 'in' clause: "
                                         f"{type(left).__name__}, {type(right).__name__}")
            return Operating.is_in(left, right)
        if op == AllowedOperator.STARTS_WITH:
            if not isinstance(left, String) or not isinstance(right, String):
                raise DslComparisonError(f"invalid arguments for 'starts_with' clause: "
                                         f"{type(left).__name__}, {type(right).__name__}")
            return Operating.does_start_with(left, right)
        if op == AllowedOperator.MATCHES:
            if not isinstance(left, String) or not isinstance(right, String):
                raise DslComparisonError(f"invalid arguments for 'matches' clause: "
                                         f"{type(left).__name__}, {type(right).__name__}")
            return Operating.does_match(left, right)
        raise DslComparisonError(f"unknown operator: {op}")


class Resolver:
    """
    turns operands (literals, fields, calls) into values
    and applies comparison operators to them
    """

    def __init__(self):
        """
        initialize self, creates the caller that implements the DSL functions,
        the comparator for symbol comparisons and the operating for word operators
        """
        self.caller = Caller()
        self.comparator = Comparator()
        self.operating = Operating()

    def resolve_unary(self, comp: Comparison, req: Request) -> _VALUE:
        """
        resolves a comparison that consists of a single operand (op is None),
        e.g. 'exists(query)'. dispatches on the operand kind
        :param comp: comparison node, only comp.left is used
        :param req: request being checked
        :return: the resolved value of the operand
        :raises DslComparisonError: if the operand is of an unknown kind
        """
        l = comp.left
        if isinstance(l, Field):
            return self.resolve_field(l, req)
        elif isinstance(l, Literal):
            return self.resolve_literal(l, req)
        elif isinstance(l, Call):
            return self.resolve_call(l, req)
        else:
            raise DslComparisonError(f"unexpected comparison: {type(l).__name__}")

    def resolve_operands(self, operands: Tuple[Operand, ...], req: Request) -> Tuple[_VALUE, ...]:
        """
        resolves every operand (used for function arguments),
        so nested calls like lower(header("X")) are computed before the outer call
        :param operands: operand nodes
        :param req: request being checked
        :return: tuple of resolved values, in the same order
        """
        return tuple(self.resolve_unary(Comparison(operand), req) for operand in operands)

    @with_limits
    def resolve_call(self, call: Call, req: Request) -> _VALUE:
        """
        resolves a function call by dispatching on the function name
        to the matching method of the caller
        :param call: call node
        :param req: request being checked
        :return: the value returned by the function
        :raises DslCallError: if the function has no implementation
        """
        func = call.func.func_name
        caller = self.caller
        args = self.resolve_operands(call.args, req)
        if func == AllowedFunc.EXISTS:
            return caller.call_exists(args, req)
        elif func == AllowedFunc.HEADER:
            return caller.call_header(args, req)
        elif func == AllowedFunc.INT:
            return caller.call_int(args, req)
        elif func == AllowedFunc.LEN:
            return caller.call_len(args, req)
        elif func == AllowedFunc.LOWER:
            return caller.call_lower(args, req)
        else:
            raise DslCallError(f"undefined function: {func}")

    def resolve_literal(self, lit: Literal, req: Request) -> _VALUE:
        """
        resolves a literal (string, number or bool).
        a literal does not depend on the request
        :param lit: literal node
        :param req: request being checked (unused for literals)
        :return: the literal value
        """
        return lit

    def resolve_field(self, field: Field, req: Request) -> _VALUE:
        """
        resolves access to a request field (method, path, query, body),
        including a nested path for the body, e.g. 'body.user.name'.
        body values are wrapped into AST nodes (see _wrap)
        :param field: field node with its optional path
        :param req: request being checked
        :return: the value of the field taken from the request,
                 _MISSING if the body or the body path is absent
        :raises DslComparisonError: if the field is unknown or the body value type is unsupported
        """
        name = field.field_name
        if name == AllowedField.METHOD:
            return String(req.method)
        if name == AllowedField.PATH:
            return String(req.path)
        if name == AllowedField.QUERY:
            return dict(req.query)
        if name == AllowedField.BODY:
            return _wrap(req.body_at(field.path))
        raise DslComparisonError(f"unknown field: {name}")

    @staticmethod
    def _missing_verdict(comp: Comparison, left: _VALUE, right: _VALUE) -> Optional[Verdict]:
        """
        a comparison with an absent value (e.g. a missing header) is not satisfied
        :param comp: comparison node
        :param left: resolved left side
        :param right: resolved right side
        :return: unsatisfied verdict if any side is _MISSING, None otherwise
        """
        if left is _MISSING or right is _MISSING:
            return Verdict(satisfied=False, what=[f"'{comp.op.value}': value is missing in the request"])
        return None

    def resolve_binary(self, comp: Comparison, req: Request) -> Verdict:
        """
        resolves a comparison with an operator (op is not None).
        symbol comparisons (>=, ==, ...) go to compare(),
        word operators (starts_with, in, matches) go to operate()
        :param comp: comparison node with left, op and right
        :param req: request being checked
        :return: verdict of the comparison
        :raises DslComparisonError: if the operator is of an unknown kind
        """
        op = comp.op
        if isinstance(op, AllowedComp):
            return self.compare(comp, req)
        elif isinstance(op, AllowedOperator):
            return self.operate(comp, req)
        else:
            raise DslComparisonError(f"unexpected comparison: {type(op).__name__}")

    def compare(self, comp: Comparison, req: Request) -> Verdict:
        """
        applies a symbol comparison (>=, <=, ==, !=, <, >):
        resolves both sides and compares the values.
        if a side is missing from the request, the verdict is "not satisfied"
        :param comp: comparison node, comp.op is an AllowedComp
        :param req: request being checked
        :return: verdict of the comparison
        :raises DslComparisonError: if the operands are not literals of the same kind
        """
        if comp.right is None or isinstance(comp.right, ListLit):
            raise DslComparisonError(f"invalid comparing operand: {type(comp.right).__name__}")

        left = self.resolve_unary(Comparison(comp.left), req)
        right = self.resolve_unary(Comparison(comp.right), req)
        missing = self._missing_verdict(comp, left, right)
        if missing is not None:
            return missing
        if not isinstance(left, Literal) or not isinstance(right, Literal):
            raise DslComparisonError(
                f"invalid operands for {comp.op.value}: "
                f"left={type(left).__name__}, right={type(right).__name__}"
            )
        res = self.comparator.compare(left, comp.op, right)
        if res.value:
            return Verdict(satisfied=True)
        return Verdict(satisfied=False,
                       what=[f"{_describe(left)} {comp.op.value} {_describe(right)} is not true"])

    def operate(self, comp: Comparison, req: Request) -> Verdict:
        """
        applies a word operator:
        - starts_with: left starts with the right operand
        - in: left is one of the values of the right list literal
        - matches: left matches the regular expression in the right string
        if a side is missing from the request, the verdict is "not satisfied"
        :param comp: comparison node, comp.op is an AllowedOperator
        :param req: request being checked
        :return: verdict of the operation
        :raises DslComparisonError: if the operand types do not fit the operator
        """
        left = self.resolve_unary(Comparison(comp.left), req)
        if isinstance(comp.right, ListLit):
            right = comp.right
        else:
            right = self.resolve_unary(Comparison(comp.right), req)
        missing = self._missing_verdict(comp, left, right)
        if missing is not None:
            return missing
        if not isinstance(left, Literal) or not (isinstance(right, Literal) or isinstance(right, ListLit)):
            raise DslComparisonError(
                f"invalid operands for {comp.op.value}: "
                f"left={type(left).__name__}, right={type(right).__name__}"
            )
        res = self.operating.operate(left, comp.op, right)
        if res.value:
            return Verdict(satisfied=True)
        return Verdict(satisfied=False,
                       what=[f"{_describe(left)} {comp.op.value} {_describe(right)} is not true"])


class Evaluator:
    """
    evaluates a parsed rule against a request.
    walks the expression tree (not / and / or / comparison) and
    collects the verdicts of its parts
    """

    def __init__(self):
        """
        initialize self, creates the resolver that computes operands and comparisons
        """
        self.resolver = Resolver()

    def not_expr(self, expr: NotExpr, req: Request) -> Verdict:
        """
        logical not: evaluates the inner expression and inverts its verdict.
        :param expr: not node
        :param req: request being checked
        :return: inverted verdict
        """
        verdict = self.resolve_expression(expr.expression, req)
        satisfied = verdict.satisfied
        return Verdict(satisfied=not satisfied, what=[] if not satisfied else verdict.what)

    def and_expr(self, expr: AndExpr, req: Request) -> Verdict:
        """
        logical and: satisfied only if all operands are satisfied.
        every operand is evaluated (no short-circuit), so 'what'
        gathers the reasons from all unsatisfied operands
        :param expr: and node with 2+ operands
        :param req: request being checked
        :return: combined verdict
        """
        v = Verdict(satisfied=True, what=[])
        for e in expr.expressions:
            cur = self.resolve_expression(e, req)
            v.satisfied = cur.satisfied and v.satisfied
            if not cur.satisfied and cur.what is not None:
                v.what += cur.what
        return v

    def or_expr(self, expr: OrExpr, req: Request) -> Verdict:
        """
        logical or: satisfied if at least one operand is satisfied.
        every operand is evaluated (no short-circuit),
        'what' gathers the reasons from the unsatisfied operands
        :param expr: or node with 2+ operands
        :param req: request being checked
        :return: combined verdict
        """
        v = Verdict(satisfied=False, what=[])
        for e in expr.expressions:
            cur = self.resolve_expression(e, req)
            v.satisfied = cur.satisfied or v.satisfied
            if not cur.satisfied and cur.what is not None:
                v.what += cur.what
        return v

    def comparison(self, comp: Comparison, req: Request) -> Verdict:
        """
        evaluates a comparison.
        - unary (op is None): the operand itself must resolve to a Bool,
          which becomes the verdict, e.g. 'exists(query)'
        - binary: delegated to the resolver
        :param comp: comparison node
        :param req: request being checked
        :return: verdict of the comparison
        :raises DslComparisonError: if a unary operand does not resolve to a Bool
        """
        if comp.op is None:
            resolved = self.resolver.resolve_unary(comp, req)
            if not isinstance(resolved, Bool):
                raise DslComparisonError(f"invalid expression type: {type(resolved).__name__}")
            return Verdict(satisfied=resolved.value)
        else:
            return self.resolver.resolve_binary(comp, req)

    @with_limits
    def resolve_expression(self, expr: Expr, req: Request) -> Verdict:
        """
        evaluates any expression node by dispatching on its type
        :param expr: comparison, not, and or or node
        :param req: request being checked
        :return: verdict of the expression
        :raises ValueError: if the node type is unknown
        """
        if isinstance(expr, Comparison):
            return self.comparison(expr, req)
        elif isinstance(expr, NotExpr):
            return self.not_expr(expr, req)
        elif isinstance(expr, AndExpr):
            return self.and_expr(expr, req)
        elif isinstance(expr, OrExpr):
            return self.or_expr(expr, req)
        else:
            raise ValueError(f"unexpected expression category: {type(expr).__name__}")

    def satisfied(self, pred: Pred, req: Request) -> Verdict:
        """
        evaluates a single predicate, i.e. the expression it holds
        :param pred: predicate node
        :param req: request being checked
        :return: verdict of the predicate
        """
        expr = pred.expression
        return self.resolve_expression(expr, req)

    def evaluate(self, rule: Rule, req: Request) -> Verdict:
        """
        evaluates a rule: all its predicates must be satisfied.
        stops at the first unsatisfied predicate and returns its verdict,
        otherwise returns the verdict of the last predicate
        :param rule: rule node
        :param req: request being checked
        :return: verdict of the rule, satisfied is True only if every predicate is satisfied
        """
        satisfied = True
        for pred in rule.predicates:
            verdict = self.satisfied(pred, req)
            satisfied = satisfied and verdict.satisfied
            if not satisfied:
                return verdict
        return Verdict(satisfied=True)
