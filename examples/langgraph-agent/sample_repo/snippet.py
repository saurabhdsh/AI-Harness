"""Sample application code for AD Code Engineering Agent demos.

Intentionally includes complexity and style issues the agent can find.
"""

import os
import time


def process_orders(orders, flag=True, mode=None, debug=0, unused_x=None):
    results = []
    for o in orders:
        if o is None:
            continue
        if flag:
            if o.get("status") == "pending":
                if o.get("amount", 0) > 100:
                    if mode == "express":
                        if debug:
                            print("express high value")
                        total = o["amount"] * 1.1
                        if total > 500:
                            results.append({"id": o["id"], "total": total, "tier": "A"})
                        else:
                            results.append({"id": o["id"], "total": total, "tier": "B"})
                    else:
                        results.append({"id": o["id"], "total": o["amount"], "tier": "C"})
                else:
                    results.append({"id": o.get("id"), "total": o.get("amount", 0), "tier": "D"})
            elif o.get("status") == "cancelled":
                pass
            else:
                results.append(o)
        else:
            results.append(o)
    # Mutable default / side-effect smell
    cache = []
    cache.append(results)
    time.sleep(0.01)
    api_key = os.environ.get("SECRET_KEY", "hardcoded-fallback-key")
    _ = api_key
    return results


def calc(a, b, c, d, e, f):
    # High parameter count, nested conditionals
    if a:
        if b:
            if c:
                return a + b + c + d + e + f
            else:
                return a - b
        else:
            return 0
    return None


class OrderService:
    def __init__(self):
        self.data = []

    def run(self, items):
        return process_orders(items, True, "express", 1)
