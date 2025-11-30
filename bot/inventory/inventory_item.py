class InventoryItem:
    def __init__(self, name: str, marketable: bool, has_owner_description: bool = False) -> None:
        self.name = name
        self.marketable = marketable
        self.has_owner_descriptions = has_owner_description  # Для определения предметов с временным ограничением

        self.list_asset_id: list[int] = []

    def add_asset_id(self, asset_id: int) -> None:
        self.list_asset_id.append(asset_id)
