from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Union, Tuple
from dslast import *
from grammar import AllowedComp, AllowedOperator, AllowedFunc


@dataclass(frozen=True)
class Request:
    """

    """
    #TODO: implement HTTP request fields
    d: Dict[str, Any]


@dataclass
class Verdict:
    """

    """
    satisfied: bool
    what: List[str] | None = None


class DslComparisonError(ValueError):
    """

    """

    def __init__(self, message: str,
                 pred: Optional[str]=None,
                 rule: Optional[str]=None,
                 context: str=""):
        """
        :param message:
        :param pred:
        :param rule:
        :param context:
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

    """

    def __init__(self, message: str,
                 expected: str | None = None,
                 given: str | None = None,
                 context: str = ""):
        """
        :param message:
        :param expected:
        :param given:
        :param context:
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

_VALUE = Union[Literal, ListLit, Dict]

class Caller:
    """

    """

    def call_lower(self, args: Tuple[Operand, ...], req: Request) -> _VALUE:
        """

        :param args:
        :param req:
        :return:
        """
        ...

    def call_len(self, args: Tuple[Operand, ...], req: Request) -> _VALUE:
        """

        :param args:
        :param req:
        :return:
        """
        ...

    def call_exists(self, args: Tuple[Operand, ...], req: Request) -> _VALUE:
        """

        :param args:
        :param req:
        :return:
        """
        ...

    def call_int(self, args: Tuple[Operand, ...], req: Request) -> _VALUE:
        """

        :param args:
        :param req:
        :return:
        """
        ...

    def call_header(self, args: Tuple[Operand, ...], req: Request) -> _VALUE:
        """

        :param args:
        :param req:
        :return:
        """
        ...


class Resolver:
    """

    """

    def __init__(self):
        """

        """
        self.caller = Caller()

    def resolve_unary(self, comp: Comparison, req: Request) -> _VALUE:
        """

        :param comp:
        :param req:
        :return:
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

        :param call:
        :param req:
        :return:
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

        :param lit:
        :param req:
        :return:
        """
        ...

    def resolve_field(self, field: Field, req: Request) -> _VALUE:
        """

        :param field:
        :param req:
        :return:
        """
        ...

    def resolve_binary(self, comp: Comparison, req: Request) -> Verdict:
        """

        :param comp:
        :param req:
        :return:
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

        :param comp:
        :param req:
        :return:
        """
        ...

    def operate(self, comp: Comparison, req: Request) -> Verdict:
        """

        :param comp:
        :param req:
        :return:
        """
        ...


class Evaluator:
    """

    """

    def __init__(self):
        self.resolver = Resolver()

    def not_expr(self, expr: NotExpr, req: Request) -> Verdict:
        """

        :param expr:
        :param req:
        :return:
        """
        verdict = self.resolve_expression(expr.expression, req)
        verdict.satisfied = not verdict.satisfied
        return verdict

    def and_expr(self, expr: AndExpr, req: Request) -> Verdict:
        """

        :param expr:
        :param req:
        :return:
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

        :param expr:
        :param req:
        :return:
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

        :param comp:
        :param req:
        :return:
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

        :param expr:
        :param req:
        :return:
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

        :param pred:
        :param req:
        :return:
        """
        expr = pred.expression
        return self.resolve_expression(expr, req)

    def evaluate(self, rule: Rule, req: Request) -> Verdict:
        """

        :param rule:
        :param req:
        :return: True if the rule is all satisfied, False otherwise
        """
        verdict = Verdict(satisfied=True)
        satisfied = True
        for pred in rule.predicates:
            verdict = self.satisfied(pred, req)
            satisfied = satisfied and verdict.satisfied
            if not satisfied:
                return verdict
        return verdict
