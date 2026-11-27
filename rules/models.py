from dataclasses import dataclass
from typing import List, Callable, Dict, Any
from enum import Enum
from urllib.request import Request
from abc import abstractmethod


class RequestFields(Enum):
    """
    allowed request fields
    """
    METHOD = "method"
    PATH = "path"
    QUERY = "query"
    HEADERS = "headers"
    BODY = "body"


@dataclass(frozen=True)
class Request:
    """
    alias for Dict type
    """
    r: Dict[str, Any]


class Severity(Enum):
    """
    status of a check
    """
    ERROR = "ERROR"
    WARNING = "WARNING"
    OK = "OK"

    def __bool__(self):
        """
        bool cast
        :return: true if it's OK, false otherwise
        """
        return self == Severity.OK


@dataclass
class CheckingVerdict:
    """
    verdict of a predicate's inspector
    """

    def __init__(self, level: Severity, message: str):
        """
        initialize self
        :param level: severity level
        :param message: details string, hints, fixes
        """
        self.level = level
        self.message = message

    def __bool__(self):
        return self.level.__bool__()


@dataclass
class Check:
    """
    return type of a predicate checker
    """
    severity: Severity
    details: Dict


class InspectorArgName:
    """
    names of the arguments of a predicate inspector.
    can be used for formatting
    """
    HINTS = "hints"
    FIXES = "fixes"


# ---------------------------------------
# Predicates
# ---------------------------------------

class Predicate:
    """
    Predicate model.
    a condition required for a request
    """

    def __init__(self, checker: Callable[[Request], Check], inspector: Callable[[Dict], str]):
        """
        initialize self
        :param checker: callback function for a check
        :param inspector: callback for a verdict message
        """
        self.checker = checker
        self.inspector = inspector

    def satisfies(self, request: Request) -> CheckingVerdict:
        """
        checks the predicate for a request
        :param request: peer's request dict
        :return: check verdict
        """
        check = self.checker(request)
        message = "" if check else self.inspector(check.details)
        return CheckingVerdict(check.severity, message)


# ---------------------------------------
# Statements
# ---------------------------------------

class Op(Enum):
    """
    allowed operations under predicates
    """
    Binary = Callable[[Request, Predicate, Predicate], bool]
    Unary = Callable[[Request, Predicate], bool]

    AND: Binary = lambda req, p1, p2: p1.satisfies(req) and p2.satisfies(req)
    OR: Binary = lambda req, p1, p2: p1.satisfies(req) or p2.satisfies(req)
    ID: Unary = lambda req, p: p.satisfies(req)
    NOT: Unary = lambda req, p: not p.satisfies(req)

    def __call__(self, *args, **kwargs):
        return self.value(args)


class Sentence:
    """
    base of a sentence.
    sentence is a statement expressing predicates
    """

    @abstractmethod
    def __bool__(self, req: Request) -> bool: ...

    def satisfies(self, req: Request) -> bool:
        """
        interface for nested sentences
        :param req: request
        :return: __bool__ implementation
        """
        return self.__bool__(req)


@dataclass(frozen=True)
class PrimeSentence(Sentence):
    """
    unary arg statement
    """
    op: Op
    pred: Predicate

    def __bool__(self, req: Request):
        return bool(self.op(req, self.pred))


@dataclass(frozen=True)
class ComplexSentence(Sentence):
    """
    binary arg statement
    """
    op: Op
    left: Sentence
    right: Sentence

    def __bool__(self, req: Request):
        """
        bool cast
        :return: True if op(left, right), False otherwise
        """
        return bool(self.op(req, self.left, self.right))


# ---------------------------------------
# Rules
# ---------------------------------------

class Rule:
    """
    model of a rule object.
    rule is a couple of conditions which have to be
    satisfied by a request
    """

    def __init__(self, name: str, condition: List[Sentence]):
        """
        initialize self
        :param name: name of a rule
        :param condition: statement
        """
        self.name = name
        self.condition = condition

    def satisfies(self, request: Request) -> bool:
        """
        checking all the sentences
        :param request: request to check
        :return: True if all satisfies, False otherwise
        """
        res = True  # presumption of satisfaction
        for sentence in self.condition:
            res = res and sentence.__bool__(request)
        return res


if __name__ == "__main__":
    print("Samples:")


    # --- 1. Predicates: one small check each, built by a factory ------------
    # checker  -> Check(severity, details): does the request satisfy it?
    # inspector -> turns details into a human-readable message (only on failure)
    def method_is(expected: str) -> Predicate:
        def checker(req: Request) -> Check:
            actual = req.r.get(RequestFields.METHOD.value)
            ok = actual == expected
            return Check(Severity.OK if ok else Severity.ERROR,
                         {"expected": expected, "actual": actual})

        def inspector(details: Dict) -> str:
            return f"method must be {details['expected']}, got {details['actual']}"

        return Predicate(checker, inspector)


    def header_present(name: str) -> Predicate:
        def checker(req: Request) -> Check:
            headers = req.r.get(RequestFields.HEADERS.value, {})
            ok = name.lower() in {h.lower() for h in headers}  # headers are case-insensitive
            return Check(Severity.OK if ok else Severity.ERROR, {"header": name})

        def inspector(details: Dict) -> str:
            return f"missing header {details['header']}"

        return Predicate(checker, inspector)


    is_post = method_is("POST")
    has_idempotency_key = header_present("Idempotency-Key")
    has_signature = header_present("X-Signature")

    # --- 2. Sentences: predicates joined by operations ----------------------
    # "if it's a POST, an Idempotency-Key is required"  ==  (NOT is_post) OR has_key
    post_needs_key = ComplexSentence(
        Op.OR,
        PrimeSentence(Op.NOT, is_post),
        PrimeSentence(Op.ID, has_idempotency_key),
    )
    signed = PrimeSentence(Op.ID, has_signature)

    # --- 3. Rules: a name + a list of sentences (all of them must hold) -----
    rules = [
        Rule("post-needs-idempotency-key", [post_needs_key]),
        Rule("webhook-signed", [signed]),
    ]

    # --- 4. Requests are plain dicts wrapped in Request ---------------------
    good = Request({
        RequestFields.METHOD.value: "POST",
        RequestFields.PATH.value: "/orders",
        RequestFields.HEADERS.value: {"Idempotency-Key": "7f3a", "X-Signature": "sha256=ab12"},
    })
    bad = Request({
        RequestFields.METHOD.value: "POST",
        RequestFields.PATH.value: "/orders",
        RequestFields.HEADERS.value: {},
    })

    for label, req in (("good", good), ("bad", bad)):
        print(f"\n{label} request:")
        for rule in rules:
            print(f"  {rule.name}: {'OK' if rule.satisfies(req) else 'VIOLATION'}")

    # --- 5. A Rule answers yes/no; a Predicate also explains why ------------
    verdict = has_idempotency_key.satisfies(bad)
    print(f"\nverdict for the bad request: {verdict.level.value} - {verdict.message}")
