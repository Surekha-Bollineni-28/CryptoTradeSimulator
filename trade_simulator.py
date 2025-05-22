import asyncio
import websockets
import json
from collections import defaultdict
from typing import Dict, List, Tuple

# Constants
WS_URL = "wss://ws.okx.com:8443/ws/v5/public"
SYMBOL = "BTC-USDT"
TAKER_FEE_RATE = 0.0006  # 0.06%

class OrderBook:
    def __init__(self):
        self.bids: Dict[float, float] = defaultdict(float)
        self.asks: Dict[float, float] = defaultdict(float)

    def update(self, data: dict):
        # Update bids and asks from snapshot or delta update
        for side in ["bids", "asks"]:
            for price_str, size_str, *_ in data.get(side, []):
                price = float(price_str)
                size = float(size_str)
                book_side = self.bids if side == "bids" else self.asks
                if size == 0:
                    if price in book_side:
                        del book_side[price]
                else:
                    book_side[price] = size

    def get_sorted_bids(self) -> List[Tuple[float, float]]:
        return sorted(self.bids.items(), key=lambda x: x[0], reverse=True)

    def get_sorted_asks(self) -> List[Tuple[float, float]]:
        return sorted(self.asks.items(), key=lambda x: x[0])

class TradeSimulator:
    def __init__(self, orderbook: OrderBook, taker_fee_rate=TAKER_FEE_RATE):
        self.orderbook = orderbook
        self.taker_fee_rate = taker_fee_rate

    def simulate_buy(self, quantity: float) -> dict:
        return self._simulate_trade(quantity, is_buy=True)

    def simulate_sell(self, quantity: float) -> dict:
        return self._simulate_trade(quantity, is_buy=False)

    def _simulate_trade(self, quantity: float, is_buy: bool) -> dict:
        book_side = self.orderbook.get_sorted_asks() if is_buy else self.orderbook.get_sorted_bids()
        remaining_qty = quantity
        total_cost = 0.0
        executed_qty = 0.0

        for price, size in book_side:
            available = size
            trade_qty = min(remaining_qty, available)
            total_cost += trade_qty * price
            remaining_qty -= trade_qty
            executed_qty += trade_qty
            if remaining_qty <= 0:
                break

        if executed_qty == 0:
            avg_price = 0.0
        else:
            avg_price = total_cost / executed_qty

        slippage = avg_price - (book_side[0][0] if is_buy else book_side[-1][0]) if executed_qty > 0 else 0.0
        fee = total_cost * self.taker_fee_rate

        return {
            "executed_quantity": executed_qty,
            "average_price": avg_price,
            "total_cost": total_cost,
            "slippage": slippage,
            "fee": fee,
            "remaining_quantity": remaining_qty
        }

async def listen_orderbook(orderbook: OrderBook):
    async with websockets.connect(WS_URL) as ws:
        # Subscribe to orderbook channel for BTC-USDT
        subscribe_msg = {
            "op": "subscribe",
            "args": [
                {
                    "channel": "books5",
                    "instId": SYMBOL
                }
            ]
        }
        await ws.send(json.dumps(subscribe_msg))
        print(f"Subscribed to {SYMBOL} orderbook")

        while True:
            response = await ws.recv()
            msg = json.loads(response)

            if "data" in msg:
                for data in msg["data"]:
                    orderbook.update(data)

async def main():
    orderbook = OrderBook()
    simulator = TradeSimulator(orderbook)

    # Run websocket listener in background
    listener_task = asyncio.create_task(listen_orderbook(orderbook))

    # Simulate trades every 5 seconds
    while True:
        await asyncio.sleep(5)
        qty = 0.1  # Example trade quantity

        buy_result = simulator.simulate_buy(qty)
        sell_result = simulator.simulate_sell(qty)

        print(f"Simulated Buy {qty} BTC: Avg Price = {buy_result['average_price']:.2f}, "
              f"Slippage = {buy_result['slippage']:.5f}, Fee = {buy_result['fee']:.5f}")

        print(f"Simulated Sell {qty} BTC: Avg Price = {sell_result['average_price']:.2f}, "
              f"Slippage = {sell_result['slippage']:.5f}, Fee = {sell_result['fee']:.5f}")
        print("-" * 60)

if __name__ == "__main__":
    asyncio.run(main())
