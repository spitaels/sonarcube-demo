"""
test_inventory.py

A comprehensive test suite for inventory.py, designed to teach unit testing
concepts step by step.

Concepts demonstrated:
1. pytest fixtures for shared setup
2. Arrange-Act-Assert structure
3. Testing happy paths
4. Testing edge cases and boundary conditions
5. Testing exceptions with pytest.raises
6. Testing state changes across multiple calls
7. Using unittest.mock to fake dependencies (notifier, clock)
8. Organizing related tests into classes (no inheritance needed)
9. Parameterizing similar tests with @pytest.mark.parametrize
"""

import pytest
from unittest.mock import Mock
from datetime import datetime

from inventory import (
    Inventory,
    InventoryItem,
    OutOfStockError,
    ItemNotFoundError,
)


# ----------------------------------------------------------------------
# Shared fixtures
# ----------------------------------------------------------------------

@pytest.fixture
def inventory():
    """A fresh, empty Inventory instance for each test."""
    return Inventory()


@pytest.fixture
def widget():
    """A standard InventoryItem used across multiple test classes."""
    return InventoryItem(sku="WIDGET1", name="Widget", quantity=10, price=2.5, low_stock_threshold=3)


@pytest.fixture
def stocked_inventory(inventory, widget):
    """An Inventory that already contains the widget item."""
    inventory.add_item(widget)
    return inventory


# ----------------------------------------------------------------------
# 1. Tests for the InventoryItem class itself
# ----------------------------------------------------------------------

class TestInventoryItem:
    """Tests for the InventoryItem data class and its simple methods."""

    def test_create_item_with_defaults(self):
        # Arrange & Act
        item = InventoryItem(sku="SKU1", name="Widget")

        # Assert
        assert item.sku == "SKU1"
        assert item.name == "Widget"
        assert item.quantity == 0
        assert item.price == 0.0

    def test_empty_sku_raises_value_error(self):
        with pytest.raises(ValueError):
            InventoryItem(sku="", name="Widget")

    def test_negative_quantity_raises_value_error(self):
        with pytest.raises(ValueError):
            InventoryItem(sku="SKU1", name="Widget", quantity=-1)

    def test_negative_price_raises_value_error(self):
        with pytest.raises(ValueError):
            InventoryItem(sku="SKU1", name="Widget", price=-5.0)

    def test_total_value_calculation(self):
        item = InventoryItem(sku="SKU1", name="Widget", quantity=4, price=2.5)
        assert item.total_value() == 10.0

    def test_total_value_rounds_to_two_decimals(self):
        # 3 * 0.1 = 0.30000000000000004 due to floating point;
        # total_value() should round this cleanly
        item = InventoryItem(sku="SKU1", name="Widget", quantity=3, price=0.1)
        assert item.total_value() == 0.3

    def test_is_low_stock_true_when_at_threshold(self):
        item = InventoryItem(sku="SKU1", name="Widget", quantity=5, low_stock_threshold=5)
        assert item.is_low_stock() is True

    def test_is_low_stock_false_when_above_threshold(self):
        item = InventoryItem(sku="SKU1", name="Widget", quantity=6, low_stock_threshold=5)
        assert item.is_low_stock() is False


# ----------------------------------------------------------------------
# 2. Tests for adding, retrieving, and removing items
# ----------------------------------------------------------------------

class TestInventoryItemManagement:
    """Tests focused on managing which items exist in the inventory."""

    def test_add_item_increases_item_count(self, inventory, widget):
        inventory.add_item(widget)
        assert inventory.item_count() == 1

    def test_add_duplicate_sku_raises_value_error(self, inventory, widget):
        inventory.add_item(widget)
        duplicate = InventoryItem(sku="WIDGET1", name="Widget Copy", quantity=5)

        with pytest.raises(ValueError):
            inventory.add_item(duplicate)

    def test_add_item_with_wrong_type_raises_type_error(self, inventory):
        with pytest.raises(TypeError):
            inventory.add_item("not an item")

    def test_get_item_returns_correct_item(self, stocked_inventory, widget):
        retrieved = stocked_inventory.get_item("WIDGET1")

        assert retrieved is widget
        assert retrieved.name == "Widget"

    def test_get_item_missing_sku_raises_item_not_found(self, inventory):
        with pytest.raises(ItemNotFoundError):
            inventory.get_item("DOES_NOT_EXIST")

    def test_remove_item_decreases_item_count(self, stocked_inventory):
        stocked_inventory.remove_item("WIDGET1")
        assert stocked_inventory.item_count() == 0

    def test_remove_missing_item_raises_item_not_found(self, inventory):
        with pytest.raises(ItemNotFoundError):
            inventory.remove_item("DOES_NOT_EXIST")


# ----------------------------------------------------------------------
# 3. Tests for stock operations: restock and sell
# ----------------------------------------------------------------------

class TestStockOperations:
    """Tests for restocking and selling items, including edge cases."""

    # --- restock ---

    def test_restock_increases_quantity(self, stocked_inventory, widget):
        new_quantity = stocked_inventory.restock("WIDGET1", 5)

        assert new_quantity == 15
        assert widget.quantity == 15

    @pytest.mark.parametrize("bad_amount", [0, -1, -100])
    def test_restock_zero_or_negative_raises_value_error(self, stocked_inventory, bad_amount):
        with pytest.raises(ValueError):
            stocked_inventory.restock("WIDGET1", bad_amount)

    def test_restock_missing_item_raises_item_not_found(self, inventory):
        with pytest.raises(ItemNotFoundError):
            inventory.restock("NOPE", 5)

    # --- sell ---

    def test_sell_decreases_quantity(self, stocked_inventory, widget):
        new_quantity = stocked_inventory.sell("WIDGET1", 4)

        assert new_quantity == 6
        assert widget.quantity == 6

    def test_sell_exact_remaining_quantity_results_in_zero(self, stocked_inventory):
        new_quantity = stocked_inventory.sell("WIDGET1", 10)
        assert new_quantity == 0

    def test_sell_more_than_available_raises_out_of_stock(self, stocked_inventory):
        with pytest.raises(OutOfStockError):
            stocked_inventory.sell("WIDGET1", 11)

    @pytest.mark.parametrize("bad_amount", [0, -5])
    def test_sell_zero_or_negative_raises_value_error(self, stocked_inventory, bad_amount):
        with pytest.raises(ValueError):
            stocked_inventory.sell("WIDGET1", bad_amount)

    def test_sell_does_not_change_quantity_when_it_fails(self, stocked_inventory, widget):
        # Arrange: capture quantity before the failed operation
        original_quantity = widget.quantity

        # Act & Assert: selling too much should raise...
        with pytest.raises(OutOfStockError):
            stocked_inventory.sell("WIDGET1", 999)

        # ...and the quantity should remain unchanged
        assert widget.quantity == original_quantity


# ----------------------------------------------------------------------
# 4. Tests for reporting methods (aggregations across items)
# ----------------------------------------------------------------------

class TestReporting:
    """Tests for inventory-wide reporting like totals and low-stock lists."""

    @pytest.fixture(autouse=True)
    def setup_inventory(self, inventory):
        """Populate inventory with three items before each test in this class."""
        self.inventory = inventory
        inventory.add_item(InventoryItem(sku="A", name="Item A", quantity=10, price=1.0,  low_stock_threshold=5))
        inventory.add_item(InventoryItem(sku="B", name="Item B", quantity=2,  price=5.0,  low_stock_threshold=5))
        inventory.add_item(InventoryItem(sku="C", name="Item C", quantity=0,  price=20.0, low_stock_threshold=1))

    def test_total_inventory_value(self):
        # A: 10 * 1.0 = 10
        # B: 2 * 5.0  = 10
        # C: 0 * 20.0 = 0
        # total = 20
        assert self.inventory.total_inventory_value() == 20.0

    def test_total_inventory_value_with_empty_inventory(self):
        assert Inventory().total_inventory_value() == 0.0

    def test_low_stock_items_returns_only_low_stock(self):
        low_stock_skus = {item.sku for item in self.inventory.low_stock_items()}
        assert low_stock_skus == {"B", "C"}

    def test_low_stock_items_empty_when_all_well_stocked(self):
        inv = Inventory()
        inv.add_item(InventoryItem(sku="A", name="Item A", quantity=100, low_stock_threshold=5))
        assert inv.low_stock_items() == []


# ----------------------------------------------------------------------
# 5. Tests demonstrating mocking external dependencies
# ----------------------------------------------------------------------

@pytest.fixture
def mock_notifier():
    return Mock()


@pytest.fixture
def notified_inventory(mock_notifier):
    """An Inventory wired with a mock notifier, containing one widget at threshold."""
    inv = Inventory(notifier=mock_notifier)
    inv.add_item(
        InventoryItem(sku="WIDGET1", name="Widget", quantity=5, price=2.5, low_stock_threshold=5)
    )
    return inv


class TestNotificationsAndClock:
    """
    Tests for behavior that depends on external collaborators.

    unittest.mock.Mock replaces a notification service and a clock function
    so tests don't depend on real time or real notification delivery.
    """

    def test_selling_triggers_low_stock_alert_when_threshold_reached(
        self, notified_inventory, mock_notifier
    ):
        widget = notified_inventory.get_item("WIDGET1")
        # Selling 1 unit brings quantity to 4, which is <= threshold (5)
        notified_inventory.sell("WIDGET1", 1)

        mock_notifier.send_low_stock_alert.assert_called_once_with(widget)

    def test_selling_does_not_trigger_alert_when_above_threshold(
        self, notified_inventory, mock_notifier
    ):
        # Restock well above threshold, then sell a small amount
        notified_inventory.restock("WIDGET1", 20)  # quantity now 25
        notified_inventory.sell("WIDGET1", 1)       # quantity now 24, still > 5

        mock_notifier.send_low_stock_alert.assert_not_called()

    def test_transaction_log_uses_injected_clock(self):
        fixed_time = datetime(2024, 1, 1, 12, 0, 0)
        mock_clock = Mock(return_value=fixed_time)

        inv = Inventory(clock=mock_clock)
        inv.add_item(InventoryItem(sku="X", name="Thing", quantity=1))

        log = inv.get_transaction_log()

        assert len(log) == 1
        assert log[0]["timestamp"] == fixed_time
        assert log[0]["action"] == "ADD_ITEM"

    def test_transaction_log_records_multiple_operations(self, notified_inventory):
        notified_inventory.restock("WIDGET1", 5)
        notified_inventory.sell("WIDGET1", 2)

        actions = [entry["action"] for entry in notified_inventory.get_transaction_log()]

        # ADD_ITEM happened in the fixture, then RESTOCK, then SELL
        assert actions == ["ADD_ITEM", "RESTOCK", "SELL"]
