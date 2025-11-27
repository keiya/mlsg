from mlsg.result import Failure, Result, Success, aggregate_results


def test_success_and_failure_types() -> None:
    r1: Result[int, str] = Success(42)
    assert isinstance(r1, Success)
    assert r1.unwrap() == 42

    r2: Result[int, str] = Failure("fail")
    assert isinstance(r2, Failure)
    assert r2.failure() == "fail"


def test_map_on_success() -> None:
    r: Result[int, str] = Success(10)
    mapped = r.map(lambda x: x * 2)
    assert mapped.unwrap() == 20


def test_map_on_failure() -> None:
    r: Result[int, str] = Failure("error")
    mapped = r.map(lambda x: x * 2)
    assert isinstance(mapped, Failure)
    assert mapped.failure() == "error"


def test_bind_on_success() -> None:
    def double_if_positive(x: int) -> Result[int, str]:
        if x > 0:
            return Success(x * 2)
        return Failure("not positive")

    r: Result[int, str] = Success(5)
    bound = r.bind(double_if_positive)
    assert bound.unwrap() == 10


def test_bind_on_failure() -> None:
    def double_if_positive(x: int) -> Result[int, str]:
        if x > 0:
            return Success(x * 2)
        return Failure("not positive")

    r: Result[int, str] = Failure("initial error")
    bound = r.bind(double_if_positive)
    assert isinstance(bound, Failure)
    assert bound.failure() == "initial error"


def test_aggregate_results_all_success() -> None:
    results: list[Result[int, str]] = [Success(1), Success(2), Success(3)]
    aggregated = aggregate_results(results)
    assert aggregated.unwrap() == [1, 2, 3]


def test_aggregate_results_with_failure() -> None:
    results: list[Result[int, str]] = [Success(1), Failure("err"), Success(3)]
    aggregated = aggregate_results(results)
    assert isinstance(aggregated, Failure)
    assert aggregated.failure() == "err"


def test_aggregate_results_empty() -> None:
    results: list[Result[int, str]] = []
    aggregated = aggregate_results(results)
    assert aggregated.unwrap() == []


def test_match_statement() -> None:
    def process(r: Result[int, str]) -> str:
        match r:
            case Success(value):
                return f"got {value}"
            case Failure(error):
                return f"error: {error}"

    assert process(Success(42)) == "got 42"
    assert process(Failure("oops")) == "error: oops"
