from ..models.product import Product
from ..models.database import db

class ProductRepository:
    def __init__(self, db_instance=None, client_username=None):
        self.db = db_instance or db
        self.client_username = client_username

    def create_product(self, title, category, link, **kwargs):
        """Create a new product for the current client."""
        if not self.client_username:
            raise ValueError("Client username is required for product creation")
        return Product.create(title, category, link, self.client_username, **kwargs)

    def get_product_by_title(self, title):
        """Get a product by title for the current client."""
        return Product.get_by_title(title, self.client_username)

    def get_product_by_id(self, product_id):
        """Get a product by ID for the current client."""
        return Product.get_by_id(product_id, self.client_username)

    def get_product_by_sku(self, sku):
        """Get a product by SKU for the current client."""
        return Product.get_by_sku(sku, self.client_username)

    def get_all_products(self):
        """Get all products for the current client."""
        return Product.get_all(self.client_username)

    def get_products_by_category(self, category, limit=50):
        """Get products by category for the current client."""
        return Product.get_by_category(category, self.client_username, limit)

    def get_products_by_tags(self, tags, limit=50):
        """Get products by tags for the current client."""
        return Product.get_by_tags(tags, self.client_username, limit)

    def get_in_stock_products(self, limit=50):
        """Get products that are in stock for the current client."""
        return Product.get_in_stock(self.client_username, limit)

    def get_out_of_stock_products(self, limit=50):
        """Get products that are out of stock for the current client."""
        return Product.get_out_of_stock(self.client_username, limit)

    def search_products(self, query, limit=10):
        """Search for products by title or description for the current client."""
        return Product.search(query, self.client_username, limit)

    def update_product(self, title, update_data):
        """Update a product for the current client."""
        return Product.update(title, update_data, self.client_username)

    def update_stock_status(self, title, stock_status):
        """Update stock status for a product for the current client."""
        return Product.update_stock_status(title, stock_status, self.client_username)

    def update_price(self, title, price):
        """Update price for a product for the current client."""
        return Product.update_price(title, price, self.client_username)

    def add_tag(self, title, tag):
        """Add a tag to a product for the current client."""
        return Product.add_tag(title, tag, self.client_username)

    def remove_tag(self, title, tag):
        """Remove a tag from a product for the current client."""
        return Product.remove_tag(title, tag, self.client_username)

    def delete_product(self, title):
        """Delete a product for the current client."""
        return Product.delete(title, self.client_username)

    def product_exists(self, title):
        """Check if a product exists for the current client."""
        return Product.exists(title, self.client_username)

    def count_products(self):
        """Count total products for the current client."""
        return Product.count_products(self.client_username)

    def count_by_category(self):
        """Get product count by category for the current client."""
        return Product.count_by_category(self.client_username)

    def count_by_stock_status(self):
        """Get product count by stock status for the current client."""
        return Product.count_by_stock_status(self.client_username)

    def get_categories(self):
        """Get all unique categories for the current client."""
        return Product.get_categories(self.client_username)

    def get_tags(self):
        """Get all unique tags for the current client."""
        return Product.get_tags(self.client_username)

    def bulk_update_stock_status(self, titles, stock_status):
        """Update stock status for multiple products for the current client."""
        return Product.bulk_update_stock_status(titles, stock_status, self.client_username)

    def get_file_id(self, title):
        """Get the file ID for a product for the current client."""
        return Product.get_file_id(title, self.client_username)

    def get_product_statistics(self):
        """Get comprehensive product statistics for the current client."""
        return Product.get_product_statistics(self.client_username)