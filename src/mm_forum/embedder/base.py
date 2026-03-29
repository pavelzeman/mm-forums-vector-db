from typing import Protocol, runtime_checkable


@runtime_checkable
class Embedder(Protocol):
    @property
    def dimension(self) -> int: ...

    @property
    def model_name(self) -> str: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...
