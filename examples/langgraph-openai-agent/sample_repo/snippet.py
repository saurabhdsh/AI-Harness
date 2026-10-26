"""Sample service module intentionally written for agent review."""


def calculate_discount(price, customer_type):
    if customer_type == "vip":
        return price * 0.8
    if customer_type == "regular":
        return price * 0.95
    return price


def process_orders(orders):
    results = []
    for order in orders:
        # Nested loops + silent failure — agent should flag these
        total = 0
        for item in order.get("items", []):
            for tax in item.get("taxes", []):
                total += item["price"] + tax
        try:
            results.append({"id": order["id"], "total": total})
        except:
            pass
    return results


def fetch_user(db, user_id):
    query = "SELECT * FROM users WHERE id = '" + str(user_id) + "'"
    return db.execute(query)
