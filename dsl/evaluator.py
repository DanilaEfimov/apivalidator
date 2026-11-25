from ast import literal_eval
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any, List, Optional, Union, Tuple
from dslast import *
from grammar import AllowedComp, AllowedOperator, AllowedFunc


@dataclass(frozen=True)
class Request:
    """
    the http request the rules are checked against.
    immutable, so one request can be safely reused across rules and predicates
    """
    #TODO: implement HTTP request fields
    d: Dict[str, Any]


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


# any value an operand can be resolved to: a literal node, a list literal or a dict (e.g. a part of the body)
_VALUE = Union[Literal, ListLit, Dict]

_ARGS = Tuple[Operand, ...]


class LiteralValueType(Enum):
    """

    """
    BOOL = Bool
    STRING = String
    INT = Number
    LIST = ListLit
    BODY = Dict
    SIZED = (String, ListLit, Dict)
    VOID = None # return type only


class CallSignature:
    """

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
        :param args:
        :return:
        """
        if len(self.expects) != len(args):
            return False
        for arg, expected in zip(args, self.expects):
            if self._type_of(arg) != expected:
                return False
        return True

    @staticmethod
    def _type_of(arg: Operand) -> LiteralValueType:
        """

        :param arg:
        :return:
        """
        try:
            return LiteralValueType(type(arg))
        except ValueError:
            raise DslCallError(f"unexpected operand: {type(arg).__name__}") from None


_LOWER_SIGNATURE = CallSignature([LiteralValueType.STRING], LiteralValueType.STRING)
_LEN_SIGNATURE = CallSignature([LiteralValueType.SIZED], LiteralValueType.INT)
_EXISTS_SIGNATURE = CallSignature([LiteralValueType.BODY, LiteralValueType.STRING], LiteralValueType.BOOL)
_INT_SIGNATURE = CallSignature([LiteralValueType.STRING], LiteralValueType.INT)
_HEADER_SIGNATURE = CallSignature([LiteralValueType.STRING], LiteralValueType.STRING)


class Caller:
    """
    implementations of the DSL functions (see AllowedFunc in grammar.py).
    each method receives the raw, not yet resolved argument nodes and the request,
    and returns the resulting value.
    the grammar does not check arity or argument types, so every method
    has to validate its arguments itself and raise DslCallError on a mismatch
    """

    def _signature_assert(self, args: _ARGS, sign: CallSignature) -> None:
        """

        :param args:
        :param sign:
        :return:
        """
        if not sign.args_match(args):
            raise DslCallError(f"call signature doesn't match given arguments: {type(args).__name__}",
                               None,
                               None,
                               f"expected: {type(sign.expects).__name__}")

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
        exists(x): checks that x is present in the request
        :param args: exactly one argument (usually a field or a header call)
        :param req: request being checked
        :return: boolean literal, True if the value is present
        """
        self._signature_assert(args, _EXISTS_SIGNATURE)
        return_type = _EXISTS_SIGNATURE.returns.value
        key = args[1].value
        exists = args[0].__contains__(key)
        return return_type(exists)

    def call_int(self, args: _ARGS, req: Request) -> _VALUE:
        """
        int(x): the value x converted to an integer
        :param args: exactly one argument, which must be convertible to int
        :param req: request being checked
        :return: the integer as a number
        """
        self._signature_assert(args, _INT_SIGNATURE)
        return_type = _INT_SIGNATURE.returns.value
        converted = int(args[0].value)
        return return_type(converted)

    def call_header(self, args: _ARGS, req: Request) -> _VALUE:
        """
        header(name): the value of the request header with the given name
        :param args: exactly one argument, the header name as a string
        :param req: request being checked
        :return: header value, or whatever the DSL uses for an absent header
        """
        ...


class Resolver:
    """
    turns operands (literals, fields, calls) into values
    and applies comparison operators to them
    """

    def __init__(self):
        """
        initialize self, creates the caller that implements the DSL functions
        """
        self.caller = Caller()

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
        args = call.args
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
        ...

    def resolve_field(self, field: Field, req: Request) -> _VALUE:
        """
        resolves access to a request field (method, path, query, body),
        including a nested path for the body, e.g. 'body.user.name'
        :param field: field node with its optional path
        :param req: request being checked
        :return: the value of the field taken from the request
        """
        ...

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
        resolves both sides and compares the values
        :param comp: comparison node, comp.op is an AllowedComp
        :param req: request being checked
        :return: verdict of the comparison
        """
        ...

    def operate(self, comp: Comparison, req: Request) -> Verdict:
        """
        applies a word operator:
        - starts_with: left starts with the right operand
        - in: left is one of the values of the right list literal
        - matches: left matches the regular expression in the right string
        :param comp: comparison node, comp.op is an AllowedOperator
        :param req: request being checked
        :return: verdict of the operation
        """
        ...


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
        note: 'what' of the inner verdict is kept as is
        :param expr: not node
        :param req: request being checked
        :return: inverted verdict
        """
        verdict = self.resolve_expression(expr.expression, req)
        verdict.satisfied = not verdict.satisfied
        return verdict

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
        verdict = Verdict(satisfied=True)
        satisfied = True
        for pred in rule.predicates:
            verdict = self.satisfied(pred, req)
            satisfied = satisfied and verdict.satisfied
            if not satisfied:
                return verdict
        return verdict
