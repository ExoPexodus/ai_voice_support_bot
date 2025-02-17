# src/data/data_fetcher.py

def fetch_customer_data(query_param):
    # Simulate a data fetch from a database or an external API
    dummy_data = {
        "order_12345": "Your order 12345 is out for delivery.",
        "order_67890": "Your order 67890 has been delivered."
    }
    return dummy_data.get(query_param, "No data found for the given query.")

if __name__ == "__main__":
    print(fetch_customer_data("order_12345"))
