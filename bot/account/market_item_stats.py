from dataclasses import dataclass


@dataclass
class MarketItemStats:
    item_name: str = ""
    total_bought: int = 0
    total_sold: int = 0
    sum_bought: float = 0.0
    sum_sold: float = 0.0

    @property
    def quantity_difference(self) -> int:
        return self.total_bought - self.total_sold

    @property
    def sum_difference(self) -> float:
        return round(self.sum_sold - self.sum_bought, 2)
