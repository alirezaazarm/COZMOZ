#!/usr/bin/env python
"""
Script to create an admin user for the Streamlit UI.
Run this script from the command line to create a new admin user.

Usage:
    python create_admin.py <username> <password>
"""
import sys
import logging
from app.services.backend import Backend

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger("create_admin")

def create_admin_user(username, password):
    """Create a new admin user with the given username and password."""
    try:
        # Initialize the backend
        backend = Backend()
        
        # Check if user already exists (by trying to authenticate)
        if backend.authenticate_admin(username, password):
            logger.error(f"User '{username}' already exists!")
            return False
            
        # Create the user
        result = backend.create_admin_user(username, password, True)
        if result:
            logger.info(f"Admin user '{username}' created successfully!")
            return True
        else:
            logger.error(f"Failed to create admin user '{username}'.")
            return False
    except Exception as e:
        logger.error(f"Error creating admin user: {str(e)}")
        return False

def main():
    """Main function to process command line arguments."""
    # Check command line arguments
    if len(sys.argv) != 3:
        print("Usage: python create_admin.py <username> <password>")
        return
        
    username = sys.argv[1]
    password = sys.argv[2]
    
    if not username or not password:
        logger.error("Username and password cannot be empty!")
        return
        
    create_admin_user(username, password)

if __name__ == "__main__":
    main() 