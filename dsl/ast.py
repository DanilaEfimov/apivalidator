from dataclasses import dataclass


# ---------------------------------------
# AST nodes
# ---------------------------------------

@dataclass(frozen=True)
class Func:
    """
    function ast node dataclass
    """
    pass


@dataclass(frozen=True)
class Number:
    """
    number ast node dataclass
    """
    pass


@dataclass(frozen=True)
class String:
    """
    string ast node dataclass
    """
    pass


@dataclass(frozen=True)
class Value:
    """
    value ast node dataclass
    """
    pass


@dataclass(frozen=True)
class LogicOp:
    """
    logic operation ast node dataclass
    """
    pass


@dataclass(frozen=True)
class Expr:
    """
    expression ast node dataclass
    """
    pass


@dataclass(frozen=True)
class Pred:
    """
    predicate ast node dataclass
    """
    pass


@dataclass(frozen=True)
class Rule:
    """
    rule ast node dataclass
    """
    pass
