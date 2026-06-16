"""실행층: paper(출력)→실거래(KIS/키움 API)."""
class PaperBroker:
    def __init__(self, capital=100_000_000):
        self.capital = capital; self.positions = {}
    def place(self, orders):
        print(f"[PAPER] 주문 {len(orders)}건 (자본 {self.capital:,.0f}원)")
        for o in orders:
            print(f"  매수 {o['name']}({o['code']}) ~{self.capital*o['weight']:,.0f}원 @ {o['entry']:,.0f}")
        return orders
