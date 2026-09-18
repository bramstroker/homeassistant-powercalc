from dataclasses import dataclass, field


@dataclass(frozen=True)
class TapoCredentials:
    """TP-Link account credentials used to authenticate a Tapo power meter."""

    username: str = field(repr=False)
    password: str = field(repr=False)
