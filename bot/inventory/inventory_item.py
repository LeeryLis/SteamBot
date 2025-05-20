class InventoryItem:
    def __init__(self, name: str, marketable: bool) -> None:
        self.name = name
        self.marketable = marketable

        self.list_asset_id: list[int] = []

    def add_asset_id(self, asset_id: int) -> None:
        self.list_asset_id.append(asset_id)
