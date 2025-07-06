import streamlit as st
import pandas as pd
import logging
from datetime import datetime, timezone
from app.services.backend import Backend
from app.models.client import Client
from app.models.enums import ClientStatus, ModuleType

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger("client_admin_ui")

# Page configuration
st.set_page_config(
    page_title="Client & Admin Management",
    page_icon="👥",
    layout="wide",
    initial_sidebar_state="expanded"
)

class ClientAdminUI:
    """Main UI class for combined client and admin management"""
    
    def __init__(self):
        self.backend = Backend()
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
            
            # Modules Section
            st.subheader("Modules")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                fixed_response_enabled = st.checkbox("Fixed Response", value=True)
                dm_assist_enabled = st.checkbox("DM Assist", value=True)
            
            with col2:
                comment_assist_enabled = st.checkbox("Comment Assist", value=True)
                vision_enabled = st.checkbox("Vision", value=True)
            
            with col3:
                scraper_enabled = st.checkbox("Scraper", value=True)
            
            # Notes
            notes = st.text_area(
                "Notes",
                placeholder="Additional notes about the client...",
                help="Internal notes about the client"
            )
            
            submit_button = st.form_submit_button(
                f"{self.get_icon('add')} Create Client",
                use_container_width=True,
                type="primary"
            )
            
            if submit_button:
                # Validate required fields
                if not all([username, business_name]):
                    st.error(f"{self.get_icon('error')} Username and business name are required!")
                elif not all([page_access_token, facebook_access_token, facebook_id, password]):
                    st.error(f"{self.get_icon('error')} All required keys (Page Access Token, Facebook Access Token, Instagram ID, and Password) are required!")
                else:
                    try:
                        with st.spinner("Creating client..."):
                            # Prepare modules (these modules don't have settings, only enabled status)
                            modules = {
                                "fixed_response": {
                                    "enabled": fixed_response_enabled
                                },
                                "dm_assist": {
                                    "enabled": dm_assist_enabled
                                },
                                "comment_assist": {
                                    "enabled": comment_assist_enabled
                                },
                                "vision": {
                                    "enabled": vision_enabled
                                },
                                "scraper": {
                                    "enabled": scraper_enabled
                                }
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
                                assistant_id=assistant_id,
                                vector_store_id=vector_store_id,
                                password=password,
                                modules=modules,
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
            if st.button(f"{self.get_icon('refresh')} Refresh", use_container_width=True):
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
                            st.write("**Modules (Editable):**")
                            modules = client.get('modules', {})
                            
                            # These modules don't have settings, only enabled status
                            edit_fixed_response = st.checkbox(
                                "Fixed Response",
                                value=modules.get('fixed_response', {}).get('enabled', False),
                                key=f"edit_fixed_response_{client['username']}"
                            )
                            edit_dm_assist = st.checkbox(
                                "DM Assist",
                                value=modules.get('dm_assist', {}).get('enabled', False),
                                key=f"edit_dm_assist_{client['username']}"
                            )
                            edit_comment_assist = st.checkbox(
                                "Comment Assist",
                                value=modules.get('comment_assist', {}).get('enabled', False),
                                key=f"edit_comment_assist_{client['username']}"
                            )
                            edit_vision = st.checkbox(
                                "Vision",
                                value=modules.get('vision', {}).get('enabled', False),
                                key=f"edit_vision_{client['username']}"
                            )
                            edit_scraper = st.checkbox(
                                "Scraper",
                                value=modules.get('scraper', {}).get('enabled', False),
                                key=f"edit_scraper_{client['username']}"
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
                                use_container_width=True,
                                type="primary"
                            )
                        with col2:
                            # Delete button
                            delete_client = st.form_submit_button(
                                f"{self.get_icon('delete')} Delete",
                                use_container_width=True,
                                type="secondary"
                            )
                        
                        if save_changes:
                            # Validate required fields
                            if not edit_business_name:
                                st.error("Business name is required!")
                            elif not all([edit_page_token, edit_fb_token, edit_ig_id]):
                                st.error("All required keys (Page Access Token, Facebook Access Token, and Instagram ID) are required!")
                            else:
                                try:
                                    # Prepare update data
                                    keys_data = {
                                        "page_access_token": edit_page_token,
                                        "username": client['username'],
                                        "ig_id": edit_ig_id,
                                        "facebook_access_token": edit_fb_token,
                                        "assistant_id": edit_assistant_id,
                                        "vector_store_id": edit_vector_store_id
                                    }
                                    
                                    # Always update password with the current value
                                    keys_data["password"] = edit_password
                                    
                                    update_data = {
                                        "info": {
                                            "business": edit_business_name,
                                            "phone_number": edit_phone,
                                            "first_name": edit_first_name,
                                            "last_name": edit_last_name,
                                            "email": edit_email
                                        },
                                        "keys": keys_data,
                                        "modules": {
                                            "fixed_response": {
                                                "enabled": edit_fixed_response
                                            },
                                            "dm_assist": {
                                                "enabled": edit_dm_assist
                                            },
                                            "comment_assist": {
                                                "enabled": edit_comment_assist
                                            },
                                            "vision": {
                                                "enabled": edit_vision
                                            },
                                            "scraper": {
                                                "enabled": edit_scraper
                                            }
                                        },
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
        """Show warning banner for clients with missing keys"""
        try:
            all_clients = Client.list_all()
            if not all_clients:
                return
            
            clients_with_issues = 0
            for client in all_clients:
                keys = client.get("keys", {})
                if not all([
                    keys.get('page_access_token'),
                    keys.get('facebook_access_token'),
                    keys.get('ig_id')
                ]):
                    clients_with_issues += 1
            
            if clients_with_issues > 0:
                st.warning(f"⚠️ **Keys Alert:** {clients_with_issues} out of {len(all_clients)} clients are missing required keys. All keys are now consolidated in a single Keys section. Check the 'Credentials Check' tab for details.")
        
        except Exception as e:
            st.error(f"Error checking keys status: {str(e)}")

def main():
    """Main function to run the Streamlit app"""
    try:
        ui = ClientAdminUI()
        ui.render()
    except Exception as e:
        st.error(f"Application error: {str(e)}")
        logger.error(f"Application error: {str(e)}", exc_info=True)

if __name__ == "__main__":
    main()