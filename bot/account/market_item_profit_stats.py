from dataclasses import dataclass


@dataclass
class MarketItemProfitStats:
    item_name: str = ""
    total_profitable: int = 0
    total_unprofitable: int = 0
    sum_profitable: float = 0.0
    sum_unprofitable: float = 0.0
    bought_queue: list[tuple[float, int]] = None

    def __init__(self):
        self.bought_queue = []

    @property
    def quantity_difference(self) -> int:
        return self.total_profitable - self.total_unprofitable

    @property
    def sum_difference(self) -> float:
        return round(self.sum_profitable + self.sum_unprofitable, 2)
