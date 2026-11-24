from dataclasses import dataclass
from typing import Dict, Any, List
from dslast import *


@dataclass(frozen=True)
class Request:
    """

    """
    d: Dict[str, Any]


@dataclass
class Verdict:
    """

    """
    satisfied: bool
    what: List[str] | None = None


class Evaluator:
    """

    """

    def __init__(self):
        """
        initialize self
        """
        pass

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
        ...

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
