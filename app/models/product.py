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
    def get_by_title(title, client_username=None):
        """Get a product by title"""
        query = {"title": title}
        if client_username:
            query["client_username"] = client_username
        return db[PRODUCTS_COLLECTION].find_one(query)

    @staticmethod
    @with_db
    def get_by_id(product_id, client_username=None):
        """Get a product by ID"""
        from bson import ObjectId
        query = {"_id": ObjectId(product_id)}
        if client_username:
            query["client_username"] = client_username
        return db[PRODUCTS_COLLECTION].find_one(query)

    @staticmethod
    @with_db
    def get_by_sku(sku, client_username=None):
        """Get a product by SKU"""
        query = {"sku": sku}
        if client_username:
            query["client_username"] = client_username
        return db[PRODUCTS_COLLECTION].find_one(query)

    @staticmethod
    @with_db
    def get_by_category(category, client_username=None, limit=50):
        """Get products by category"""
        query = {"category": {"$regex": category, "$options": "i"}}
        if client_username:
            query["client_username"] = client_username
        return list(db[PRODUCTS_COLLECTION].find(query).limit(limit))

    @staticmethod
    @with_db
    def get_by_tags(tags, client_username=None, limit=50):
        """Get products by tags"""
        if isinstance(tags, str):
            tags = [tags]
        query = {"tags": {"$in": tags}}
        if client_username:
            query["client_username"] = client_username
        return list(db[PRODUCTS_COLLECTION].find(query).limit(limit))

    @staticmethod
    @with_db
    def get_in_stock(client_username=None, limit=50):
        """Get products that are in stock"""
        query = {"stock_status": {"$ne": "ناموجود"}}
        if client_username:
            query["client_username"] = client_username
        return list(db[PRODUCTS_COLLECTION].find(query).limit(limit))

    @staticmethod
    @with_db
    def get_out_of_stock(client_username=None, limit=50):
        """Get products that are out of stock"""
        query = {"stock_status": "ناموجود"}
        if client_username:
            query["client_username"] = client_username
        return list(db[PRODUCTS_COLLECTION].find(query).limit(limit))

    @staticmethod
    @with_db
    def update_stock_status(title, stock_status, client_username=None):
        """Update stock status for a product"""
        return Product.update(title, {"stock_status": stock_status}, client_username)

    @staticmethod
    @with_db
    def update_price(title, price, client_username=None):
        """Update price for a product"""
        return Product.update(title, {"price": price}, client_username)

    @staticmethod
    @with_db
    def add_tag(title, tag, client_username=None):
        """Add a tag to a product"""
        try:
            query = {"title": title}
            if client_username:
                query["client_username"] = client_username
            
            result = db[PRODUCTS_COLLECTION].update_one(
                query,
                {"$addToSet": {"tags": tag}}
            )
            return result.modified_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to add tag: {str(e)}")
            return False

    @staticmethod
    @with_db
    def remove_tag(title, tag, client_username=None):
        """Remove a tag from a product"""
        try:
            query = {"title": title}
            if client_username:
                query["client_username"] = client_username
            
            result = db[PRODUCTS_COLLECTION].update_one(
                query,
                {"$pull": {"tags": tag}}
            )
            return result.modified_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to remove tag: {str(e)}")
            return False

    @staticmethod
    @with_db
    def exists(title, client_username=None):
        """Check if a product exists"""
        query = {"title": title}
        if client_username:
            query["client_username"] = client_username
        return db[PRODUCTS_COLLECTION].find_one(query) is not None

    @staticmethod
    @with_db
    def count_products(client_username=None):
        """Count total products"""
        query = {}
        if client_username:
            query["client_username"] = client_username
        return db[PRODUCTS_COLLECTION].count_documents(query)

    @staticmethod
    @with_db
    def count_by_category(client_username=None):
        """Get product count by category"""
        pipeline = []
        if client_username:
            pipeline.append({"$match": {"client_username": client_username}})
        
        pipeline.extend([
            {"$group": {"_id": "$category", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ])
        
        return list(db[PRODUCTS_COLLECTION].aggregate(pipeline))

    @staticmethod
    @with_db
    def count_by_stock_status(client_username=None):
        """Get product count by stock status"""
        pipeline = []
        if client_username:
            pipeline.append({"$match": {"client_username": client_username}})
        
        pipeline.extend([
            {"$group": {"_id": "$stock_status", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ])
        
        return list(db[PRODUCTS_COLLECTION].aggregate(pipeline))

    @staticmethod
    @with_db
    def get_categories(client_username=None):
        """Get all unique categories"""
        query = {}
        if client_username:
            query["client_username"] = client_username
        return db[PRODUCTS_COLLECTION].distinct("category", query)

    @staticmethod
    @with_db
    def get_tags(client_username=None):
        """Get all unique tags"""
        query = {}
        if client_username:
            query["client_username"] = client_username
        return db[PRODUCTS_COLLECTION].distinct("tags", query)

    @staticmethod
    @with_db
    def bulk_update_stock_status(titles, stock_status, client_username=None):
        """Update stock status for multiple products"""
        try:
            query = {"title": {"$in": titles}}
            if client_username:
                query["client_username"] = client_username
            
            result = db[PRODUCTS_COLLECTION].update_many(
                query,
                {"$set": {"stock_status": stock_status}}
            )
            return result.modified_count
        except PyMongoError as e:
            logger.error(f"Failed to bulk update stock status: {str(e)}")
            return 0

    @staticmethod
    @with_db
    def get_product_statistics(client_username=None):
        """Get comprehensive product statistics"""
        query = {}
        if client_username:
            query["client_username"] = client_username
        
        total_products = db[PRODUCTS_COLLECTION].count_documents(query)
        categories = Product.count_by_category(client_username)
        stock_status = Product.count_by_stock_status(client_username)
        
        return {
            "total_products": total_products,
            "categories": categories,
            "stock_status": stock_status
        }

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


