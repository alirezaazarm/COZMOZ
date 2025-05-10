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
            "link": link
        }


    @staticmethod
    @with_db
    def create(
        title,
        category,
        link,
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
            title, category, link, translated_title, tags,
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
    def update(title, update_data):
        """Update a product"""
        try:
            result = db[PRODUCTS_COLLECTION].update_one(
                {"title": title},
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
    def delete(title):
        """Delete a product"""
        try:
            result = db[PRODUCTS_COLLECTION].delete_one({"title": title})
            return result.deleted_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to delete product: {str(e)}")
            return False

    @staticmethod
    @with_db
    def get_all():
        """Get all products"""
        return list(db[PRODUCTS_COLLECTION].find())

    @staticmethod
    @with_db
    def search(query, limit=10):
        """Search for products by title or description"""
        return list(db[PRODUCTS_COLLECTION].find(
            {
                "$or": [
                    {"title": {"$regex": query, "$options": "i"}},
                    {"description": {"$regex": query, "$options": "i"}},
                    {"translated_title": {"$regex": query, "$options": "i"}}
                ]
            },
            limit=limit
        ))
    
    @staticmethod
    @with_db
    def get_file_id(title):
        """Get the file ID for a product"""
        return db[PRODUCTS_COLLECTION].find_one({"title": title})["file_id"]


