from dataclasses import dataclass
from typing import Dict, Any
from dslast import *


@dataclass(frozen=True)
class Request:
    """

    """
    d: Dict[str, Any]


@dataclass(frozen=True)
class Verdict:
    """

    """
    satisfied: bool
    what: str | None = None


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
        ...

    def and_expr(self, expr: AndExpr, req: Request) -> Verdict:
        """

        :param expr:
        :param req:
        :return:
        """
        ...

    def or_expr(self, expr: OrExpr, req: Request) -> Verdict:
        """

        :param expr:
        :param req:
        :return:
        """
        ...

    def comparison(self, comp: Comparison, req: Request) -> Verdict:
        """

        :param comp:
        :param req:
        :return:
        """
        ...

    def satisfied(self, pred: Pred, req: Request) -> Verdict:
        """

        :param pred:
        :param req:
        :return:
        """
        ...

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
