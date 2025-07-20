from ..models.orderbook import Orderbook
from ..models.database import db

class OrderbookRepository:
    def __init__(self, db_instance=None):
        self.db = db_instance or db

    def create_order(self, tx_id, status, first_name, last_name, address, phone, product, price, date, count, client_username):
        """Create a new orderbook entry."""
        return Orderbook.create(tx_id, status, first_name, last_name, address, phone, product, price, date, count, client_username)

    def get_order_by_id(self, order_id):
        """Get an orderbook entry by its MongoDB _id."""
        return Orderbook.get_by_id(order_id)

    def update_order(self, order_id, update_data):
        """Update an orderbook entry by its MongoDB _id."""
        return Orderbook.update(order_id, update_data)

    def delete_order(self, order_id):
        """Delete an orderbook entry by its MongoDB _id."""
        return Orderbook.delete(order_id)

    def get_all_orders(self):
        """Get all orderbook entries."""
        return Orderbook.get_all()

    def get_order_by_tx_id(self, tx_id, client_username):
        """Get an orderbook entry by its tx_id and client_username."""
        return Orderbook.get_by_tx_id(tx_id, client_username) 