class SellOrderItem:
    def __init__(self, app_id: int = 0, context_id: int = 0, name: str = None, order_id: int = 0,
                 buyer_price: float = 0, seller_price: float = 0, creation_date: str = None) -> None:
        self.app_id = app_id
        self.context_id = context_id

        self.name = name
        self.order_id = order_id
        self.buyer_price = buyer_price
        self.seller_price = seller_price
        self.creation_date = creation_date

    def __str__(self) -> str:
        return f"Sell Order Item:\n"\
               f"\tName: {self.name}\n"\
               f"\tApp ID: {self.app_id}\n"\
               f"\tContext ID: {self.context_id}\n"\
               f"\tOrder ID: {self.order_id}\n"\
               f"\tBuyer Price: {self.buyer_price}\n"\
               f"\tSeller Price: {self.seller_price}\n"\
               f"\tCreation Date: {self.creation_date}"
