# src/data/data_fetcher.py

import os
import csv
import requests

# Configurable CSV file path and API endpoint (set these in your .env file)
CSV_FILE_PATH = os.getenv("ORDER_DATA_CSV", "src/data/data.csv")
ORDER_API_ENDPOINT = os.getenv("ORDER_API_ENDPOINT", "https://api.example.com/order")

def fetch_order_data(order_id, source="csv"):
    """
    Fetch order data either from a CSV file (for testing) or from an API.
    :param order_id: The order number as a string.
    :param source: "csv" to read from a file, "api" to call an external API.
    :return: Order data as a dictionary or an error message.
    """
    if source == "csv":
        return fetch_from_csv(order_id)
    elif source == "api":
        return fetch_from_api(order_id)
    else:
        return {"error": "Invalid data source specified"}

def fetch_from_csv(order_id):
    """Reads order data from a CSV file based on order_id."""
    try:
        with open(CSV_FILE_PATH, mode="r", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            for row in reader:
                if row.get("order_id") == order_id:
                    return row  # Return the matched order data
        return {"error": "Order not found"}
    except Exception as e:
        return {"error": f"Error reading CSV: {str(e)}"}

def fetch_from_api(order_id):
    """Calls an external API to fetch order data."""
    try:
        response = requests.get(f"{ORDER_API_ENDPOINT}/{order_id}")
        if response.status_code == 200:
            return response.json()
        return {"error": f"API request failed with status code {response.status_code}"}
    except Exception as e:
        return {"error": f"API request error: {str(e)}"}

if __name__ == "__main__":
    print(fetch_order_data("1113", source="csv"))
    print(fetch_order_data("12345", source="api"))
