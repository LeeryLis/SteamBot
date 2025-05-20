class BuyOrderItem:
    def __init__(self, app_id: int = 0, context_id: int = 0, name: str = None, order_id: int = 0,
                 price: float = 0, quantity: int = 0) -> None:
        self.app_id = app_id
        self.context_id = context_id

        self.name = name
        self.order_id = order_id
        self.price = price
        self.quantity = quantity

    def __str__(self) -> str:
        return f"Buy Order Item:\n"\
               f"\tName: {self.name}\n"\
               f"\tApp ID: {self.app_id}\n"\
               f"\tContext ID: {self.context_id}\n"\
               f"\tOrder ID: {self.order_id}\n"\
               f"\tPrice: {self.price}\n"\
               f"\tQuantity: {self.quantity}\n"
