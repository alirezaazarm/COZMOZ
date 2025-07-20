from .database import db, PRODUCTS_COLLECTION, with_db
import logging
from pymongo.errors import PyMongoError

logger = logging.getLogger(__name__)

class Product:
    """Product model for MongoDB"""

    @staticmethod
    def create_product_document(
        title,
        category,
        link,
        client_username,
        translated_title=None,
        tags=None,
        price=None,
        excerpt=None,
        sku=None,
        description=None,
        stock_status="موجود",
        additional_info=None
    ):
        """Create a new product document structure"""
        return {
            "title": title,
            "translated_title": translated_title,
            "category": category,
            "tags": tags,
            "price": price or {},
            "excerpt": excerpt,
            "sku": sku,
            "description": description,
            "stock_status": stock_status,
            "additional_info": additional_info or {},
            "link": link,
            "client_username": client_username  # Links product to specific client
        }


    @staticmethod
    @with_db
    def create(
        title,
        category,
        link,
        client_username,
        translated_title=None,
        tags=None,
        price=None,
        excerpt=None,
        sku=None,
        description=None,
        stock_status="موجود",
        additional_info=None
    ):
        """Create a new product"""
        product_doc = Product.create_product_document(
            title, category, link, client_username, translated_title, tags,
            price, excerpt, sku, description, stock_status, additional_info
        )

        try:
            result = db[PRODUCTS_COLLECTION].insert_one(product_doc)
            if result.acknowledged:
                return product_doc
            return None
        except PyMongoError as e:
            logger.error(f"Failed to create product: {str(e)}")
            return None

    @staticmethod
    @with_db
    def update(title, update_data, client_username=None):
        """Update a product"""
        try:
            query = {"title": title}
            if client_username:
                query["client_username"] = client_username

            result = db[PRODUCTS_COLLECTION].update_one(
                query,
                {"$set": update_data}
            )
            return result.modified_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to update product: {str(e)}")
            return False

    @staticmethod
    @with_db
    def update_many(filter_criteria, update_data):
        try:
            result = db[PRODUCTS_COLLECTION].update_many(
                filter_criteria,
                update_data
            )
            return result.modified_count
        except PyMongoError as e:
            logger.error(f"Failed to update multiple products: {str(e)}")
            return 0

    @staticmethod
    @with_db
    def delete(title, client_username=None):
        """Delete a product"""
        try:
            query = {"title": title}
            if client_username:
                query["client_username"] = client_username

            result = db[PRODUCTS_COLLECTION].delete_one(query)
            return result.deleted_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to delete product: {str(e)}")
            return False

    @staticmethod
    @with_db
    def get_all(client_username=None):
        """Get all products"""
        query = {}
        if client_username:
            query["client_username"] = client_username
        return list(db[PRODUCTS_COLLECTION].find(query))

    @staticmethod
    @with_db
    def search(query, client_username=None, limit=10):
        """Search for products by title or description"""
        search_criteria = {
            "$or": [
                {"title": {"$regex": query, "$options": "i"}},
                {"description": {"$regex": query, "$options": "i"}},
                {"translated_title": {"$regex": query, "$options": "i"}}
            ]
        }
        
        if client_username:
            search_criteria["client_username"] = client_username

        return list(db[PRODUCTS_COLLECTION].find(
            search_criteria,
            limit=limit
        ))
    
    @staticmethod
    @with_db
    def get_file_id(title, client_username=None):
        """Get the file ID for a product"""
        query = {"title": title}
        if client_username:
            query["client_username"] = client_username
        
        product = db[PRODUCTS_COLLECTION].find_one(query)
        return product["file_id"] if product else None

    @staticmethod
    @with_db
    def deduplicate_for_client(client_username):
        """Remove duplicate products for a client, keeping only the first occurrence of each unique link."""
        products = list(db[PRODUCTS_COLLECTION].find({"client_username": client_username}))
        seen_links = set()
        for product in products:
            link = product.get("link")
            _id = product.get("_id")
            if link in seen_links:
                db[PRODUCTS_COLLECTION].delete_one({"_id": _id})
                logger.info(f"Removed duplicate product with link '{link}' for client '{client_username}' (_id={_id})")
            else:
                seen_links.add(link)


