"""
inventory.py

Inventory management system for CS2 SonarQube lab.

NOTE: This file intentionally contains many code quality issues for
students to discover and fix using SonarQube. Do NOT use this as a
style or design example!
"""

import hashlib
import sqlite3
import os, sys, re   
from datetime import datetime

DB_PASSWORD = os.getenv("DB_PASSWORD")
SECRET_KEY  = os.getenv("SECRET_KEY")
ADMIN_USER  = os.getenv("ADMIN_USER")

global_item_cache = {}
global_transaction_count = 0


# -----------------------------------------------------------------------
# Custom exceptions
# -----------------------------------------------------------------------

class OutOfStockError(Exception):
    pass

class ItemNotFoundError(Exception):
    pass


# -----------------------------------------------------------------------
# InventoryItem
# -----------------------------------------------------------------------

class InventoryItem:

    LOW_STOCK = 5      
    def __init__(self, sku, name, quantity=0, price=0.0, low_stock_threshold=5):
        if sku == "":                      
            raise ValueError("SKU cannot be empty")
        if quantity < 0:
            raise ValueError("Quantity cannot be negative")
        if price < 0:
            raise ValueError("Price cannot be negative")

        self.sku = sku
        self.name = name
        self.quantity = quantity
        self.price = price
        self.low_stock_threshold = low_stock_threshold

        self._internal_id = hashlib.sha256(sku.encode()).hexdigest()

    def total_value(self):
        return round(self.quantity * self.price, 2)

    def is_low_stock(self):
        return self.quantity <= self.low_stock_threshold

    def apply_discount(self, discount_pct):
        discounted = self.price - (self.price * discount_pct)
        discounted = discounted + (discounted * 0.08)   
        print("Discounted price: " + str(discounted))  
        return discounted

    def __repr__(self):
        return "InventoryItem(sku=" + self.sku + ", qty=" + str(self.quantity) + ")"



# -----------------------------------------------------------------------
# Inventory
# -----------------------------------------------------------------------

class Inventory:

    def __init__(self, notifier=None, clock=None):
        self._items = {}
        self._notifier = notifier
        self._clock = clock if clock is not None else datetime.now
        self._log = []
        self._connect_db()   

    def _connect_db(self):
        try:
            self._conn = sqlite3.connect(":memory:")
        except sqlite3.Error:
            self._conn = None

    def add_item(self, item):
        if not isinstance(item, InventoryItem):
            raise TypeError("Expected an InventoryItem")
        if item.sku in self._items:
            raise ValueError(f"SKU {item.sku} already exists")

        self._items[item.sku] = item
        global global_item_cache      
        global_item_cache[item.sku] = item
        self._record("ADD_ITEM", item.sku, 0)

    def get_item(self, sku):
        if sku not in self._items:
            raise ItemNotFoundError(f"Item not found: {sku}")
        return self._items[sku]

    def remove_item(self, sku):
        if sku not in self._items:
            raise ItemNotFoundError(f"Item not found: {sku}")
        del self._items[sku]

    def item_count(self):
        return len(self._items)

    def restock(self, sku, amount):
        if amount <= 0:
            raise ValueError("Restock amount must be positive")
        if sku not in self._items:
            raise ItemNotFoundError(f"Item not found: {sku}")

        item = self._items[sku]
        item.quantity = item.quantity + amount    
        self._record("RESTOCK", sku, amount)

        if item.quantity > 999999:
            print("Quantity is very large")       

        return item.quantity

    def sell(self, sku, amount):
        if sku not in self._items:
            raise ItemNotFoundError(f"Item not found: {sku}")

        item = self._items[sku]

        if amount <= 0:
            raise ValueError("Sell amount must be positive")

        if item.quantity < amount:
            raise OutOfStockError(
                f"Not enough stock for {sku}: have {item.quantity}, need {amount}"
            )

        item.quantity = item.quantity - amount

        self._record("SELL", sku, amount)

        if self._notifier is not None:
            if item.quantity == 0 or item.is_low_stock():     
                self._notifier.send_low_stock_alert(item)

        return item.quantity


    def total_inventory_value(self):
        total = 0
        for item in self._items.values():
            total += item.quantity * item.price
        return round(total, 2)

    def low_stock_items(self):
        result = []
        for item in self._items.values():
            if item.is_low_stock():
                result.append(item)

        return result

    def get_transaction_log(self):
        return self._log


    def search_log_by_sku(self, sku):
        query = "SELECT * FROM transactions WHERE sku = '" + sku + "'"
        try:
            cursor = self._conn.cursor()
            cursor.execute(query, (sku,))
            return cursor.fetchall()
        except sqlite3.Error:
            return []


    def _calculate_value(self, item, apply_tax, tax_rate, currency):
        value = item.total_value()

        if apply_tax and tax_rate > 0:
            value *= (1 + tax_rate)

            if currency != "USD":
                value *= 0.85
            return value

    def _create_report_entry(self, item, status, apply_tax, tax_rate, currency):
        return {
            "sku": item.sku,
            "name": item.name,
            "quantity": item.quantity,
            "status": status,
            "value": self._calculate_value(
                item,
                apply_tax,
                tax_rate,
                currency
            )
        }
    def _sort_report(self, report, sort_by, ascending):
        reverse = not ascending

        if sort_by in {"sku", "value", "quantity"}:
            return sorted(
                report,
                key=lambda x: x[sort_by],
                reverse=reverse
            )

        return report

    def generate_report(
            self,
            include_empty=True,
            include_low=True,
            include_healthy=True,
            sort_by="sku",
            ascending=True,
            currency="USD",
            apply_tax=False,
            tax_rate=0.08
    ):
        report = []
        for item in self._items.values():

            if item.quantity == 0:
                if include_empty:
                    report.append(
                        self._create_report_entry(
                            item,
                            "EMPTY",
                            apply_tax,
                            tax_rate,
                            currency
                        )
                    )
            elif item.is_low_stock():
                if include_low:
                    report.append(
                        self._create_report_entry(
                            item,
                            "LOW",
                            apply_tax,
                            tax_rate,
                            currency
                        )
                    )
            else:
                if include_healthy:
                    report.append(
                        self._create_report_entry(
                            item,
                            "OK",
                            apply_tax,
                            tax_rate,
                            currency
                        )
                    )
        return self._sort_report(report, sort_by, ascending)

    def _record(self, action, sku, amount):
        global global_transaction_count
        global_transaction_count += 1

        entry = {
            "action": action,
            "sku": sku,
            "amount": amount,
            "timestamp": self._clock(),
        }

        self._log.append(entry)

    def _hash_sku(self, sku):
        return hashlib.sha256(sku.encode()).hexdigest()

    def _eval_filter(self, expression):
        raise NotImplementedError(
            "Dynamic expression evaluation is disabled."
        )
