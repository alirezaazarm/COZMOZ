from ..models.client import Client
from ..models.database import db

class ClientRepository:
    def __init__(self, db_instance=None):
        self.db = db_instance or db

    def get_client_by_username(self, username):
        """Get a client by username."""
        return Client.get_by_username(username)

    def get_client_by_id(self, client_id):
        """Get a client by ID."""
        return Client.get_by_id(client_id)

    def get_client_by_email(self, email):
        """Get a client by email."""
        return Client.get_by_email(email)

    def create_client(self, username, business_name, email, **kwargs):
        """Create a new client."""
        return Client.create(username, business_name, email, **kwargs)

    def create_client_with_credentials(self, username, business_name, email, facebook_creds=None, openai_creds=None, **kwargs):
        """Create a new client with credentials."""
        return Client.create_with_credentials(username, business_name, email, facebook_creds, openai_creds, **kwargs)

    def update_client(self, username, update_data):
        """Update a client's data."""
        return Client.update(username, update_data)

    def update_client_credentials(self, username, credential_type, credentials):
        """Update client credentials."""
        return Client.update_credentials(username, credential_type, credentials)

    def get_client_credentials(self, username, credential_type=None):
        """Get client credentials."""
        return Client.get_client_credentials(username, credential_type)

    def enable_module(self, username, module_name):
        """Enable a module for a client."""
        return Client.enable_module(username, module_name)

    def disable_module(self, username, module_name):
        """Disable a module for a client."""
        return Client.disable_module(username, module_name)

    def is_module_enabled(self, username, module_name):
        """Check if a module is enabled for a client."""
        return Client.is_module_enabled(username, module_name)

    def get_module_settings(self, username, module_name):
        """Get settings for a specific module."""
        return Client.get_module_settings(username, module_name)

    def update_module_settings(self, username, module_name, settings):
        """Update settings for a specific module."""
        return Client.update_module_settings(username, module_name, settings)

    def update_usage_stats(self, username, stats_update):
        """Update usage statistics for a client."""
        return Client.update_usage_stats(username, stats_update)

    def increment_usage_stats(self, username, **increments):
        """Increment usage statistics for a client."""
        return Client.increment_usage_stats(username, **increments)

    def get_all_active_clients(self):
        """Get all active clients."""
        return Client.get_all_active()

    def get_clients_with_module_enabled(self, module_name):
        """Get all clients with a specific module enabled."""
        return Client.get_clients_with_module_enabled(module_name)

    def get_client_statistics(self, username):
        """Get comprehensive statistics for a client."""
        return Client.get_statistics(username)

    def validate_client_access(self, username, required_module=None):
        """Validate if a client exists and has access to a specific module."""
        return Client.validate_access(username, required_module)

    def list_all_clients(self):
        """Get a list of all clients with basic information."""
        return Client.list_all()

    def delete_client(self, username):
        """Delete a client (soft delete)."""
        return Client.delete(username)