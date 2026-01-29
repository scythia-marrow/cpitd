def calculate_total(items):
    total = 0
    for item in items:
        price = item["price"]
        quantity = item["quantity"]
        subtotal = price * quantity
        if subtotal > 100:
            discount = subtotal * 0.1
            subtotal = subtotal - discount
        total = total + subtotal
    return total


def format_report(title, data):
    header = "=" * len(title)
    result = header + "\n" + title + "\n" + header + "\n"
    for key, value in data.items():
        result = result + f"  {key}: {value}\n"
    return result
