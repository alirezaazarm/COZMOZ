import streamlit as st
import pandas as pd
import logging
from datetime import datetime, timezone
import os
import sys
import requests
import json

# Ensure project root (parent of `app`) is on sys.path when running via Streamlit
try:
    from app.models.client import Client
    from app.models.enums import ClientStatus, ModuleType, Platform
    from app.config import Config
except ModuleNotFoundError:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, "../../.."))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from app.models.client import Client
    from app.models.enums import ClientStatus, ModuleType, Platform
    from app.config import Config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger("client_admin_ui")

# Backend for client/admin management
class ClientManagerBackend:
    def __init__(self, client_username=None):
        self.client_username = client_username

    def authenticate_admin(self, username, password):
        try:
            user = Client.authenticate_admin(username, password)
            return bool(user)
        except Exception:
            return False

    def create_auth_token(self, username):
        try:
            import json, hmac, hashlib, base64, time
            secret = Config.VERIFY_TOKEN or "streamlit_admin_secret_key"
            expire_time = int(time.time()) + (7 * 24 * 60 * 60)
            token_data = {"username": username, "exp": expire_time}
            token_bytes = json.dumps(token_data).encode("utf-8")
            token_b64 = base64.b64encode(token_bytes).decode("utf-8")
            signature = hmac.new(secret.encode("utf-8"), token_b64.encode("utf-8"), hashlib.sha256).hexdigest()
            return f"{token_b64}.{signature}"
        except Exception:
            return None

    def verify_auth_token(self, token):
        try:
            import json, hmac, hashlib, base64, time
            secret = Config.VERIFY_TOKEN or "streamlit_admin_secret_key"
            token_b64, signature = token.split(".")
            expected = hmac.new(secret.encode("utf-8"), token_b64.encode("utf-8"), hashlib.sha256).hexdigest()
            if signature != expected:
                return None
            payload = json.loads(base64.b64decode(token_b64).decode("utf-8"))
            if payload.get("exp", 0) < int(time.time()):
                return None
            username = payload.get("username")
            user = Client.get_by_username(username)
            if not user or not user.get("is_admin", False) or user.get("status") != "active":
                return None
            return username
        except Exception:
            return None

    def get_admin_users(self):
        try:
            users = Client.get_all_admins()
            result = []
            for user in users:
                username = user.get("username", "Unknown")
                is_active = user.get("status") == "active"
                created_at = user.get("created_at", "Unknown")
                last_login = user.get("last_login", "Never")
                if hasattr(created_at, "strftime"):
                    created_at = created_at.strftime("%Y-%m-%d %H:%M")
                if hasattr(last_login, "strftime"):
                    last_login = last_login.strftime("%Y-%m-%d %H:%M")
                result.append({
                    "Username": username,
                    "Status": "Active" if is_active else "Inactive",
                    "Created": created_at,
                    "Last Login": last_login,
                })
            return result
        except Exception:
            return []

    def create_admin_user(self, username, password, is_active=True):
        try:
            return bool(Client.create_admin(username, password, is_active=is_active))
        except Exception:
            return False

    def update_admin_password(self, username, current_password, new_password):
        try:
            user = Client.authenticate_admin(username, current_password)
            if not user:
                return False
            return bool(Client.update_admin_password(username, new_password))
        except Exception:
            return False

    def update_admin_status(self, username, is_active):
        try:
            return bool(Client.update_admin_status(username, is_active))
        except Exception:
            return False

    def delete_admin_user(self, username):
        try:
            return bool(Client.delete_admin(username))
        except Exception:
            return False

    def ensure_default_admin(self):
        try:
            return bool(Client.ensure_default_admin())
        except Exception:
            return False

class ClientAdminUI:
    """Main UI class for combined client and admin management"""
    
    def __init__(self):
        self.backend = ClientManagerBackend()
        self.icon_shortcodes = {
            "admin": ":bust_in_silhouette:",
            "client": ":office:", 
            "add": ":heavy_plus_sign:",
            "edit": ":pencil2:",
            "delete": ":wastebasket:",
            "save": ":floppy_disk:",
            "success": ":white_check_mark:",
            "error": ":x:",
            "warning": ":warning:",
            "info": ":information_source:",
            "refresh": ":arrows_counterclockwise:",
            "search": ":mag:",
            "stats": ":bar_chart:",
            "settings": ":gear:",
            "key": ":key:",
            "active": ":large_green_circle:",
            "inactive": ":red_circle:",
            "suspended": ":large_yellow_circle:",
            "trial": ":large_blue_circle:"
        }
    
    def get_icon(self, shortcode_key):
        """Convert shortcode to emoji for display"""
        shortcode = self.icon_shortcodes.get(shortcode_key, ":question:")
        return shortcode

    def render_json_safe(self, payload):
        """Render JSON safely in Streamlit, falling back to code if not a dict/list."""
        try:
            if isinstance(payload, (dict, list)):
                st.json(payload)
            else:
                st.code(json.dumps(payload, ensure_ascii=False, default=str))
        except Exception:
            try:
                st.code(json.dumps(payload, ensure_ascii=False, default=str))
            except Exception:
                st.code(str(payload))
    
    def render(self):
        """Main render method"""
        st.title(f"{self.get_icon('admin')} Client Management System")
        
        # Sidebar navigation
        with st.sidebar:
            st.header("Navigation")
            page = st.radio(
                "Select Page",
                ["Client Management", "System Statistics"],
                key="main_navigation"
            )
        
        # Render selected page
        if page == "Client Management":
            self.render_client_management()
        elif page == "System Statistics":
            self.render_system_statistics()
    
    def render_client_management(self):
        """Render client management interface"""
        st.header(f"{self.get_icon('client')} Client Management")
        
        # Show credentials warning banner
        self.show_credentials_warning()
        
        # Tabs for different client operations
        manage_tab , create_tab = st.tabs(["Manage Clients","Create Client"])
        
        with create_tab:
            self.render_create_client_form()
        
        with manage_tab:
            self.render_client_list()
    
    def render_create_client_form(self):
        """Render form to create new clients with updated structure"""
        st.subheader(f"{self.get_icon('add')} Create New Client")
        
        with st.form("create_client_form", clear_on_submit=True):
            st.subheader("Basic Information")
            col1, col2 = st.columns(2)
            
            with col1:
                username = st.text_input(
                    "Username",
                    placeholder="Enter unique username",
                    help="Unique identifier for the client"
                )
                
                business_name = st.text_input(
                    "Business Name",
                    placeholder="Enter business/company name",
                    help="Business name for the client"
                )
                
                phone_number = st.text_input(
                    "Phone Number",
                    placeholder="+1234567890",
                    help="Contact phone number"
                )
            
            with col2:
                first_name = st.text_input(
                    "First Name",
                    placeholder="Enter first name",
                    help="Client's first name"
                )
                
                last_name = st.text_input(
                    "Last Name",
                    placeholder="Enter last name",
                    help="Client's last name"
                )
                
                email = st.text_input(
                    "Email",
                    placeholder="Enter email address",
                    help="Client's email address"
                )
            
            # Keys Section
            st.subheader("Keys")
            st.info("All client keys and credentials are configured here.")
            
            col1, col2 = st.columns(2)
            with col1:
                page_access_token = st.text_input(
                    "Page Access Token",
                    placeholder="Enter Facebook Page Access Token",
                    help="Facebook Page Access Token for API access",
                    type="password"
                )
                
                facebook_access_token = st.text_input(
                    "Facebook Access Token",
                    placeholder="Enter Facebook Access Token",
                    help="Facebook User Access Token",
                    type="password"
                )
                
                facebook_id = st.text_input(
                    "Instagram ID",
                    placeholder="Enter Instagram ID",
                    help="Instagram ID for the client's account"
                )
            
            with col2:
                telegram_access_token = st.text_input(
                    "Telegram Access Token",
                    placeholder="Enter Telegram Bot Token",
                    help="Telegram Bot API token",
                    type="password"
                )
                assistant_id = st.text_input(
                    "Assistant ID",
                    placeholder="Enter OpenAI Assistant ID",
                    help="OpenAI Assistant ID"
                )
                
                vector_store_id = st.text_input(
                    "Vector Store ID",
                    placeholder="Enter Vector Store ID",
                    help="OpenAI Vector Store ID"
                )
                
                password = st.text_input(
                    "Password",
                    type="password",
                    placeholder="Enter admin password",
                    help="Admin password for client access"
                )
            
            # Platforms Section
            st.subheader("Platforms")
            plat_col1, plat_col2 = st.columns(2)
            with plat_col1:
                instagram_enabled = st.checkbox("Enable Instagram", value=False)
                st.caption("Per-platform modules for Instagram")
                ig_col1, ig_col2, ig_col3, ig_col4, ig_col5 = st.columns(5)
                with ig_col1:
                    ig_fixed = st.checkbox("Fixed Response", value=True, key="create_ig_fixed")
                with ig_col2:
                    ig_dm = st.checkbox("DM Assist", value=True, key="create_ig_dm")
                with ig_col3:
                    ig_comment = st.checkbox("Comment Assist", value=True, key="create_ig_comment")
                with ig_col4:
                    ig_vision = st.checkbox("Vision", value=True, key="create_ig_vision")
                with ig_col5:
                    ig_orderbook = st.checkbox("Orderbook", value=True, key="create_ig_orderbook")
            with plat_col2:
                telegram_enabled = st.checkbox("Enable Telegram", value=False)
                st.caption("Per-platform modules for Telegram")
                tg_col1, tg_col2, tg_col3, tg_col4, tg_col5 = st.columns(5)
                with tg_col1:
                    tg_fixed = st.checkbox("Fixed Response", value=True, key="create_tg_fixed")
                with tg_col2:
                    tg_dm = st.checkbox("DM Assist", value=True, key="create_tg_dm")
                with tg_col3:
                    tg_comment = st.checkbox("Comment Assist", value=True, key="create_tg_comment")
                with tg_col4:
                    tg_vision = st.checkbox("Vision", value=True, key="create_tg_vision")
                with tg_col5:
                    tg_orderbook = st.checkbox("Orderbook", value=True, key="create_tg_orderbook")


            
            # Notes
            notes = st.text_area(
                "Notes",
                placeholder="Additional notes about the client...",
                help="Internal notes about the client"
            )
            
            submit_button = st.form_submit_button(
                f"{self.get_icon('add')} Create Client",
                width='stretch',
                type="primary"
            )
            
            if submit_button:
                # Validate required fields
                if not all([username, business_name]):
                    st.error(f"{self.get_icon('error')} Username and business name are required!")
                else:
                    # Platform-specific key validations
                    errors = []
                    if instagram_enabled:
                        if not all([page_access_token, facebook_access_token, facebook_id]):
                            errors.append("Instagram requires Page Access Token, Facebook Access Token, and Instagram ID")
                    if telegram_enabled:
                        if not telegram_access_token:
                            errors.append("Telegram requires Telegram Access Token")
                    if not password:
                        errors.append("Password is required")
                    if errors:
                        st.error(f"{self.get_icon('error')} " + "; ".join(errors))
                        return
                    try:
                        with st.spinner("Creating client..."):
                            # Prepare platforms structure
                            platforms = {
                                Platform.INSTAGRAM.value: {
                                    "enabled": instagram_enabled,
                                    "modules": {
                                        ModuleType.FIXED_RESPONSE.value: {"enabled": ig_fixed},
                                        ModuleType.DM_ASSIST.value: {"enabled": ig_dm},
                                        ModuleType.COMMENT_ASSIST.value: {"enabled": ig_comment},
                                        ModuleType.VISION.value: {"enabled": ig_vision},
                                        ModuleType.ORDERBOOK.value: {"enabled": ig_orderbook},
                                    },
                                },
                                Platform.TELEGRAM.value: {
                                    "enabled": telegram_enabled,
                                    "modules": {
                                        ModuleType.FIXED_RESPONSE.value: {"enabled": tg_fixed},
                                        ModuleType.DM_ASSIST.value: {"enabled": tg_dm},
                                        ModuleType.COMMENT_ASSIST.value: {"enabled": tg_comment},
                                        ModuleType.VISION.value: {"enabled": tg_vision},
                                        ModuleType.ORDERBOOK.value: {"enabled": tg_orderbook},
                                    },
                                },
                            }
                            
                            # Create client with new structure (default status: inactive)
                            result = Client.create_with_credentials(
                                username=username,
                                business_name=business_name,
                                phone_number=phone_number,
                                first_name=first_name,
                                last_name=last_name,
                                email=email,
                                page_access_token=page_access_token,
                                facebook_id=facebook_id,
                                facebook_access_token=facebook_access_token,
                                telegram_access_token=telegram_access_token,
                                assistant_id=assistant_id,
                                vector_store_id=vector_store_id,
                                password=password,
                                platforms=platforms,
                                notes=notes,
                                status="inactive"  # Default to inactive
                            )
                            
                            if result:
                                st.success(f"{self.get_icon('success')} Client '{username}' created successfully with status 'inactive'. You can activate them in the Manage Clients section.")
                                # Clear any cached data and force refresh
                                if 'client_list_cache' in st.session_state:
                                    del st.session_state['client_list_cache']
                                st.rerun()
                            else:
                                st.error(f"{self.get_icon('error')} Failed to create client. Username may already exist.")
                    except Exception as e:
                        st.error(f"{self.get_icon('error')} Error creating client: {str(e)}")
    
        
    def render_client_list(self):
        """Render list of existing clients with management options"""
        st.subheader(f"{self.get_icon('settings')} Manage Clients")
        
        # Refresh button and filters
        col1, col2, col3, col4 = st.columns([1, 1, 2, 2])
        with col1:
            if st.button(f"{self.get_icon('refresh')} Refresh", width='stretch'):
                st.rerun()
        
        with col2:
            status_filter = st.selectbox(
                "Filter by Status",
                options=["All"] + [status.value for status in ClientStatus],
                key="client_status_filter"
            )
        
        try:
            # Get all clients (including admins) - get raw data for proper editing
            from app.models.client import db, CLIENTS_COLLECTION
            all_clients = list(db[CLIENTS_COLLECTION].find({}))
            
            if not all_clients:
                st.info(f"{self.get_icon('info')} No clients found.")
                return
            
            # Apply status filter
            if status_filter != "All":
                clients = [c for c in all_clients if c.get("status") == status_filter]
            else:
                clients = all_clients
            
            if not clients:
                st.info(f"{self.get_icon('info')} No clients found with status '{status_filter}'.")
                return
            
            # Display clients in a more detailed format
            for client in clients:
                info = client.get("info", {})
                keys = client.get("keys", {})
                
                business_name = info.get("business") or client.get("business_name", "Unknown")
                first_name = info.get("first_name", "")
                last_name = info.get("last_name", "")
                phone_number = info.get("phone_number", "")
                
                # Debug: Show what data we're getting
                # st.write(f"DEBUG - Client: {client.get('username')}, Info section: {info}")
                
                # Simple title showing only username
                expander_title = f"{self.get_status_icon(client.get('status', 'active'))} {client.get('username', 'Unknown')}"
                
                with st.expander(expander_title):
                    # Make all fields editable inline
                    with st.form(f"inline_edit_{client['username']}"):
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            st.write("**Basic Info (Editable):**")
                            edit_business_name = st.text_input(
                                "Business Name",
                                value=business_name,
                                key=f"edit_business_{client['username']}"
                            )
                            edit_phone = st.text_input(
                                "Phone",
                                value=info.get('phone_number', ''),
                                key=f"edit_phone_{client['username']}"
                            )
                            edit_first_name = st.text_input(
                                "First Name",
                                value=info.get('first_name', ''),
                                key=f"edit_first_name_{client['username']}"
                            )
                            edit_last_name = st.text_input(
                                "Last Name",
                                value=info.get('last_name', ''),
                                key=f"edit_last_name_{client['username']}"
                            )
                            edit_email = st.text_input(
                                "Email",
                                value=info.get('email') or client.get('email', ''),
                                key=f"edit_email_{client['username']}"
                            )
                            
                            # Status management
                            current_status = client.get('status', 'inactive')
                            status_options = [status.value for status in ClientStatus]
                            current_index = status_options.index(current_status) if current_status in status_options else 0
                            
                            edit_status = st.selectbox(
                                "Status",
                                options=status_options,
                                index=current_index,
                                key=f"edit_status_{client['username']}"
                            )
                        
                        with col2:
                            st.write("**Keys (Editable):**")
                            edit_page_token = st.text_input(
                                "Page Access Token",
                                value=keys.get('page_access_token', ''),
                                type="password",
                                key=f"edit_page_token_{client['username']}"
                            )
                            edit_fb_token = st.text_input(
                                "FB Access Token",
                                value=keys.get('facebook_access_token', ''),
                                type="password",
                                key=f"edit_fb_token_{client['username']}"
                            )
                            edit_ig_id = st.text_input(
                                "Instagram ID",
                                value=keys.get('ig_id', ''),
                                key=f"edit_ig_id_{client['username']}"
                            )
                            edit_tg_token = st.text_input(
                                "Telegram Access Token",
                                value=keys.get('telegram_access_token', ''),
                                type="password",
                                key=f"edit_tg_token_{client['username']}"
                            )
                            edit_assistant_id = st.text_input(
                                "Assistant ID",
                                value=keys.get('assistant_id', ''),
                                key=f"edit_assistant_id_{client['username']}"
                            )
                            edit_vector_store_id = st.text_input(
                                "Vector Store ID",
                                value=keys.get('vector_store_id', ''),
                                key=f"edit_vector_store_id_{client['username']}"
                            )
                            edit_password = st.text_input(
                                "Password",
                                value=keys.get('password', ''),  # Show current password
                                type="password",
                                key=f"edit_password_{client['username']}"
                            )
                        
                        with col3:
                            st.write("**Platforms (Editable):**")

                            # Platforms configuration
                            st.write("**Platforms (Editable):**")
                            platforms = client.get('platforms', {})
                            ig_cfg = platforms.get(Platform.INSTAGRAM.value, {"enabled": False, "modules": {}})
                            tg_cfg = platforms.get(Platform.TELEGRAM.value, {"enabled": False, "modules": {}})

                            ig_enabled = st.checkbox(
                                "Instagram Enabled",
                                value=ig_cfg.get('enabled', False),
                                key=f"edit_plat_ig_enabled_{client['username']}"
                            )
                            ig_m = ig_cfg.get('modules', {})
                            ig_fixed = st.checkbox(
                                "IG Fixed Response",
                                value=ig_m.get(ModuleType.FIXED_RESPONSE.value, {}).get('enabled', True),
                                key=f"edit_plat_ig_fixed_{client['username']}"
                            )
                            ig_dm = st.checkbox(
                                "IG DM Assist",
                                value=ig_m.get(ModuleType.DM_ASSIST.value, {}).get('enabled', True),
                                key=f"edit_plat_ig_dm_{client['username']}"
                            )
                            ig_comment = st.checkbox(
                                "IG Comment Assist",
                                value=ig_m.get(ModuleType.COMMENT_ASSIST.value, {}).get('enabled', True),
                                key=f"edit_plat_ig_comment_{client['username']}"
                            )
                            ig_vision = st.checkbox(
                                "IG Vision",
                                value=ig_m.get(ModuleType.VISION.value, {}).get('enabled', True),
                                key=f"edit_plat_ig_vision_{client['username']}"
                            )
                            ig_orderbook = st.checkbox(
                                "IG Orderbook",
                                value=ig_m.get(ModuleType.ORDERBOOK.value, {}).get('enabled', True),
                                key=f"edit_plat_ig_orderbook_{client['username']}"
                            )

                            tg_enabled = st.checkbox(
                                "Telegram Enabled",
                                value=tg_cfg.get('enabled', False),
                                key=f"edit_plat_tg_enabled_{client['username']}"
                            )
                            tg_m = tg_cfg.get('modules', {})
                            tg_fixed = st.checkbox(
                                "TG Fixed Response",
                                value=tg_m.get(ModuleType.FIXED_RESPONSE.value, {}).get('enabled', True),
                                key=f"edit_plat_tg_fixed_{client['username']}"
                            )
                            tg_dm = st.checkbox(
                                "TG DM Assist",
                                value=tg_m.get(ModuleType.DM_ASSIST.value, {}).get('enabled', True),
                                key=f"edit_plat_tg_dm_{client['username']}"
                            )
                            tg_comment = st.checkbox(
                                "TG Comment Assist",
                                value=tg_m.get(ModuleType.COMMENT_ASSIST.value, {}).get('enabled', True),
                                key=f"edit_plat_tg_comment_{client['username']}"
                            )
                            tg_vision = st.checkbox(
                                "TG Vision",
                                value=tg_m.get(ModuleType.VISION.value, {}).get('enabled', True),
                                key=f"edit_plat_tg_vision_{client['username']}"
                            )
                            tg_orderbook = st.checkbox(
                                "TG Orderbook",
                                value=tg_m.get(ModuleType.ORDERBOOK.value, {}).get('enabled', True),
                                key=f"edit_plat_tg_orderbook_{client['username']}"
                            )
                            
                            st.write("**Notes:**")
                            edit_notes = st.text_area(
                                "Notes",
                                value=client.get('notes', ''),
                                key=f"edit_notes_{client['username']}"
                            )
                        
                        # Save changes button
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            save_changes = st.form_submit_button(
                                f"{self.get_icon('save')} Save Changes",
                                width='stretch',
                                type="primary"
                            )
                        with col2:
                            # Delete button
                            delete_client = st.form_submit_button(
                                f"{self.get_icon('delete')} Delete",
                                width='stretch',
                                type="secondary"
                            )
                        
                        if save_changes:
                            # Validate required fields
                            if not edit_business_name:
                                st.error("Business name is required!")
                            else:
                                # Platform-specific key validations
                                errors = []
                                if ig_enabled:
                                    if not all([edit_page_token, edit_fb_token, edit_ig_id]):
                                        errors.append("Instagram requires Page Access Token, Facebook Access Token, and Instagram ID")
                                if tg_enabled:
                                    if not edit_tg_token:
                                        errors.append("Telegram requires Telegram Access Token")
                                if errors:
                                    st.error("; ".join(errors))
                                    return
                                try:
                                    # Prepare update data
                                    keys_data = {
                                        "page_access_token": edit_page_token,
                                        "username": client['username'],
                                        "ig_id": edit_ig_id,
                                        "facebook_access_token": edit_fb_token,
                                        "telegram_access_token": edit_tg_token,
                                        "assistant_id": edit_assistant_id,
                                        "vector_store_id": edit_vector_store_id
                                    }
                                    
                                    # Always update password with the current value
                                    keys_data["password"] = edit_password
                                    
                                    platforms_update = {
                                        Platform.INSTAGRAM.value: {
                                            "enabled": ig_enabled,
                                            "modules": {
                                                ModuleType.FIXED_RESPONSE.value: {"enabled": ig_fixed},
                                                ModuleType.DM_ASSIST.value: {"enabled": ig_dm},
                                                ModuleType.COMMENT_ASSIST.value: {"enabled": ig_comment},
                                                ModuleType.VISION.value: {"enabled": ig_vision},
                                                ModuleType.ORDERBOOK.value: {"enabled": ig_orderbook},
                                            },
                                        },
                                        Platform.TELEGRAM.value: {
                                            "enabled": tg_enabled,
                                            "modules": {
                                                ModuleType.FIXED_RESPONSE.value: {"enabled": tg_fixed},
                                                ModuleType.DM_ASSIST.value: {"enabled": tg_dm},
                                                ModuleType.COMMENT_ASSIST.value: {"enabled": tg_comment},
                                                ModuleType.VISION.value: {"enabled": tg_vision},
                                                ModuleType.ORDERBOOK.value: {"enabled": tg_orderbook},
                                            },
                                        },
                                    }

                                    update_data = {
                                        "info": {
                                            "business": edit_business_name,
                                            "phone_number": edit_phone,
                                            "first_name": edit_first_name,
                                            "last_name": edit_last_name,
                                            "email": edit_email
                                        },
                                        "keys": keys_data,
                                        "platforms": platforms_update,
                                        "status": edit_status,
                                        "notes": edit_notes,
                                        # Keep legacy fields for backward compatibility
                                        "business_name": edit_business_name,
                                        "updated_at": datetime.now(timezone.utc)
                                    }
                                    
                                    # Update client data
                                    client_updated = Client.update(client['username'], update_data)
                                    
                                    if client_updated:
                                        st.success(f"{self.get_icon('success')} Client updated successfully!")
                                        st.rerun()
                                    else:
                                        st.error("Failed to update client.")
                                except Exception as e:
                                    st.error(f"Error updating client: {str(e)}")
                        
                        if delete_client:
                            if st.session_state.get(f"confirm_delete_client_{client['username']}", False):
                                try:
                                    Client.delete(client['username'])
                                    st.success("Client deleted!")
                                    st.session_state[f"confirm_delete_client_{client['username']}"] = False
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error: {str(e)}")
                            else:
                                st.session_state[f"confirm_delete_client_{client['username']}"] = True
                                st.warning("Click again to confirm deletion!")
                    
                    # End of form

                    # Telegram Webhook Controls (outside the form for immediate action)
                    st.divider()
                    st.write("**Telegram Webhook**")
                    wh_col1, wh_col2, wh_col3, wh_col4 = st.columns([3, 1, 1, 1])
                    default_wh_url = f"{Config.BASE_URL}/telegram/{client['username']}"
                    with wh_col1:
                        webhook_url = st.text_input(
                            "Webhook URL",
                            value=default_wh_url,
                            key=f"tg_wh_url_{client['username']}"
                        )
                    with wh_col2:
                        if st.button("Set", key=f"tg_wh_set_{client['username']}"):
                            try:
                                with st.spinner("Setting Telegram webhook..."):
                                    # Prefer direct Telegram API if token is available
                                    if edit_tg_token:
                                        resp = requests.post(
                                            f"https://api.telegram.org/bot{edit_tg_token}/setWebhook",
                                            json={"url": webhook_url},
                                            timeout=20
                                        )
                                    else:
                                        resp = requests.post(
                                            f"{Config.BASE_URL}/hooshang_webhook/{client['username']}/set",
                                            json={"url": webhook_url},
                                            timeout=20
                                        )
                                    try:
                                        data = resp.json()
                                    except Exception:
                                        data = None
                                    if isinstance(data, dict) and data.get("ok"):
                                        st.success("Webhook set successfully.")
                                        result_payload = data.get("result", data)
                                        self.render_json_safe(result_payload)
                                    else:
                                        st.error(f"Failed to set webhook (status {resp.status_code}).")
                                        self.render_json_safe(data if data is not None else (resp.text or "<no response body>"))
                            except Exception as e:
                                st.error(f"Error setting webhook: {str(e)}")
                    with wh_col3:
                        if st.button("Info", key=f"tg_wh_info_{client['username']}"):
                            try:
                                with st.spinner("Fetching webhook info..."):
                                    if edit_tg_token:
                                        resp = requests.get(
                                            f"https://api.telegram.org/bot{edit_tg_token}/getWebhookInfo",
                                            timeout=20
                                        )
                                    else:
                                        resp = requests.get(
                                            f"{Config.BASE_URL}/hooshang_webhook/{client['username']}/info",
                                            timeout=20
                                        )
                                    try:
                                        data = resp.json()
                                    except Exception:
                                        data = None
                                    if isinstance(data, dict) and data.get("ok"):
                                        result_payload = data.get("result", data)
                                        self.render_json_safe(result_payload)
                                    else:
                                        st.error(f"Failed to get webhook info (status {resp.status_code}).")
                                        self.render_json_safe(data if data is not None else (resp.text or "<no response body>"))
                            except Exception as e:
                                st.error(f"Error getting webhook info: {str(e)}")
                    with wh_col4:
                        if st.button("Delete", key=f"tg_wh_del_{client['username']}"):
                            try:
                                with st.spinner("Deleting webhook..."):
                                    if edit_tg_token:
                                        resp = requests.post(
                                            f"https://api.telegram.org/bot{edit_tg_token}/deleteWebhook",
                                            data={"drop_pending_updates": True},
                                            timeout=20
                                        )
                                    else:
                                        resp = requests.post(
                                            f"{Config.BASE_URL}/hooshang_webhook/{client['username']}/delete",
                                            json={"drop_pending_updates": True},
                                            timeout=20
                                        )
                                    try:
                                        data = resp.json()
                                    except Exception:
                                        data = None
                                    if isinstance(data, dict) and data.get("ok"):
                                        st.success("Webhook deleted.")
                                        result_payload = data.get("result", data)
                                        self.render_json_safe(result_payload)
                                    else:
                                        st.error(f"Failed to delete webhook (status {resp.status_code}).")
                                        self.render_json_safe(data if data is not None else (resp.text or "<no response body>"))
                            except Exception as e:
                                st.error(f"Error deleting webhook: {str(e)}")
            
            # Client editing is now handled inline in the expandable sections above
        
        except Exception as e:
            st.error(f"{self.get_icon('error')} Error loading clients: {str(e)}")
    
    # render_edit_client_form method removed - editing is now handled inline in render_client_list
    
    # render_client_details and render_credentials_check methods removed as per requirements
    
    def render_system_statistics(self):
        """Render system-wide statistics"""
        st.header(f"{self.get_icon('stats')} System Statistics")
        
        try:
            # Get all clients
            all_clients = Client.list_all()
            
            # Basic statistics
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Total Clients", len(all_clients))
            
            with col2:
                active_clients = len([c for c in all_clients if c.get('status') == 'active'])
                st.metric("Active Clients", active_clients)
            
            with col3:
                inactive_clients = len([c for c in all_clients if c.get('status') != 'active'])
                st.metric("Inactive Clients", inactive_clients)
            
            # Client status distribution
            if all_clients:
                st.subheader("Client Status Distribution")
                
                status_counts = {}
                for client in all_clients:
                    status = client.get('status', 'unknown')
                    status_counts[status] = status_counts.get(status, 0) + 1
                
                # Create a simple bar chart using Streamlit
                status_df = pd.DataFrame(list(status_counts.items()), columns=['Status', 'Count'])
                st.bar_chart(status_df.set_index('Status'))
            
            # Module usage statistics
            st.subheader("Module Usage Across Clients")
            
            if all_clients:
                module_usage = {}
                for client in all_clients:
                    modules = client.get('modules', {})
                    for module_name, module_data in modules.items():
                        if module_data.get('enabled', False):
                            module_usage[module_name] = module_usage.get(module_name, 0) + 1
                
                if module_usage:
                    module_df = pd.DataFrame(list(module_usage.items()), columns=['Module', 'Enabled Count'])
                    st.bar_chart(module_df.set_index('Module'))
                else:
                    st.info("No module usage data available.")
        
        except Exception as e:
            st.error(f"Error loading system statistics: {str(e)}")
    
    def get_status_icon(self, status):
        """Get icon for client status"""
        status_icons = {
            'active': self.get_icon('active'),
            'inactive': self.get_icon('inactive'),
            'suspended': self.get_icon('suspended'),
            'trial': self.get_icon('trial'),
            'deleted': self.get_icon('error'),
            'expired': self.get_icon('warning')
        }
        return status_icons.get(status, self.get_icon('info'))
    
    def show_credentials_warning(self):
        """Show warning banner for clients with missing keys per enabled platform"""
        try:
            all_clients = Client.list_all()
            if not all_clients:
                return
            
            clients_with_issues = 0
            for client in all_clients:
                keys = client.get("keys", {})
                platforms = client.get("platforms", {})
                ig = platforms.get(Platform.INSTAGRAM.value, {})
                tg = platforms.get(Platform.TELEGRAM.value, {})
                missing = False
                if ig.get("enabled"):
                    if not all([
                        keys.get('page_access_token'),
                        keys.get('facebook_access_token'),
                        keys.get('ig_id')
                    ]):
                        missing = True
                if tg.get("enabled"):
                    if not keys.get('telegram_access_token'):
                        missing = True
                if missing:
                    clients_with_issues += 1
            
            if clients_with_issues > 0:
                st.warning(f"**Keys Alert:** {clients_with_issues} out of {len(all_clients)} clients have missing keys for at least one enabled platform.")
        
        except Exception as e:
            st.error(f"Error checking keys status: {str(e)}")

def main():
    """Main function to run the Streamlit app"""
    try:
        # Page configuration
        st.set_page_config(
            page_title="Client & Admin Management",
            page_icon="👥",
            layout="wide",
            initial_sidebar_state="expanded"
        )
        ui = ClientAdminUI()
        ui.render()
    except Exception as e:
        st.error(f"Application error: {str(e)}")
        logger.error(f"Application error: {str(e)}", exc_info=True)

if __name__ == "__main__":
    main()