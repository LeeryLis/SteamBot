from dataclasses import dataclass


@dataclass
class ItemAsset:
    AppID = 0
    ContextID = 0
    ItemID = 0

    def __init__(self, app_id: str, context_id: str, item_id: str):
        self.AppID = app_id
        self.ContextID = context_id
        self.ItemID = item_id
