import logging
import streamlit as st
import os
import sys
import base64 # Used to embed images into HTML

# Ensure project root is on sys.path to allow absolute imports
try:
    from app.services.dashboards.insta import InstagramUI
    from app.services.dashboards.AI import OpenAIManagementUI
    from app.services.dashboards.telegram import TelegramUI
    from app.services.dashboards.client_manager import ClientManagerBackend
    from app.models.client import Client
except ModuleNotFoundError:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, "../../.."))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from app.services.dashboards.insta import InstagramUI
    from app.services.dashboards.AI import OpenAIManagementUI
    from app.services.dashboards.telegram import TelegramUI
    from app.services.dashboards.client_manager import ClientManagerBackend
    from app.models.client import Client


logging.basicConfig(
    handlers=[logging.FileHandler('logs.txt', encoding='utf-8'), logging.StreamHandler()],
    level=logging.ERROR,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
#===============================================================================================================================
class AppConstants:
    """Centralized configuration for icons and messages"""
    ICONS = {
        "scraper": ":building_construction:" ,
        "scrape": ":rocket:",
        "update": ":arrows_counterclockwise:" ,
        "ai": ":robot_face:",
        "delete": ":wastebasket:" ,
        "add": ":heavy_plus_sign:" ,
        "success": ":white_check_mark:" ,
        "error": ":x:" ,
        "preview": ":package:" ,
        "brain": ":brain:" ,
        "chat": ":speech_balloon:",
        "connect": ":link:",
        "instagram": ":camera:",
        "post": ":newspaper:",
        "story": ":film_frames:",
        "paper_and_pen": ":memo:",
        "previous": ":arrow_left:",
        "next": ":arrow_right:",
        "label": ":label:",
        "save": ":floppy_disk:",
        "model": ":brain:",
        "folder": ":open_file_folder:",
        "dashboard": ":bar_chart:",
        "data": ":page_facing_up:",
        "login": ":key:",
        "logout": ":door:",
        "user": ":bust_in_silhouette:",
        "magic": ":magic_wand:",
    }


    AVATARS={
        "admin": "assets/icons/admin.png",
        "user": "assets/icons/user.png",
        "assistant": "assets/icons/assistant.png",
        "fixed_response": "assets/icons/fixed_response.png",
        "instagram" : "assets/icons/instagram.png",
        "telegram" : "assets/icons/telegram.png",
        "ai": "assets/icons/assistant.png", # Added avatar for the AI section
    }

    MESSAGES = {
        "scraping_start": "Scraping all products. This may take several minutes...",
        "update_start": "Checking for new products...",
        "processing_start": "Processing products - this may take several minutes..."
    }
def validate_client_access(client_username, required_module=None):
    """
    Validate client access - moved from dashboard.py
    Returns True if access is valid, raises ValueError with message if not
    """
    if not client_username:
        raise ValueError("No client context loaded")
    
    client_data = Client.get_by_username(client_username)
    if not client_data:
        raise ValueError(f"Client '{client_username}' not found")
    
    if client_data.get('status') != 'active':
        raise ValueError(f"Client '{client_username}' is not active")
    
    if required_module:
        if not Client.is_module_enabled(client_username, required_module):
            raise ValueError(f"Module '{required_module}' is not enabled for client '{client_username}'")
    
    return True

class BaseSection:
    """Base class for UI sections (kept for compatibility)"""
    def __init__(self):
        self.const = AppConstants()
#===============================================================================================================================
class AdminUI:
    """Main application container"""
    def __init__(self):
        st.set_page_config(layout="wide", page_title="Admin Dashboard")

        if 'authenticated' not in st.session_state:
            st.session_state['authenticated'] = False
        if 'username' not in st.session_state:
            st.session_state['username'] = None

        try:
            self.admin_backend = ClientManagerBackend()
            self.admin_backend.ensure_default_admin()
            self._check_auth_token()
        except NameError:
            st.error("Backend class definition not found. Please ensure it's defined or imported.")
            class DummyBackend:
                def __getattr__(self, name):
                    def method(*args, **kwargs):
                        print(f"DummyBackend: Method '{name}' called")
                        if name == 'authenticate_admin': return True
                        if name == 'create_auth_token': return "dummy_token"
                        if name == 'verify_auth_token': return "admin"
                        return None
                    return method
            self.backend = DummyBackend()

        # Default page if none is set in session state
        if 'selected_page' not in st.session_state:
            st.session_state.selected_page = "AI"

    def _get_section_mapping(self, client_username):
        """Create section mapping with the authenticated client username"""
        return {
            "AI": OpenAIManagementUI(client_username=client_username),
            "Instagram": InstagramUI(client_username=client_username),
            "Telegram": TelegramUI(client_username=client_username)
        }

    def _check_auth_token(self):
        """Check if an authentication token is present and valid"""
        if 'auth_token' in st.session_state: return

        auth_token = st.query_params.get('auth_token')
        if auth_token and len(auth_token) > 0:
            username = self.admin_backend.verify_auth_token(auth_token)
            if username:
                st.session_state['authenticated'] = True
                st.session_state['username'] = username
                st.session_state['auth_token'] = auth_token

    def render(self):
        """Render all application sections based on authentication status"""
        if not st.session_state['authenticated']:
            self._render_login_page()
        else:
            if 'auth_token' in st.session_state and 'auth_token' not in st.query_params:
                st.query_params['auth_token'] = st.session_state['auth_token']
            self._render_authenticated_ui()

    def _render_login_page(self):
        """Display login page for unauthenticated users"""
        const = AppConstants()
        st.title(f"{const.ICONS['login']} Admin Login")
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            with st.form("login_form"):
                st.subheader("Please sign in")
                username = st.text_input("Username", key="login_username")
                password = st.text_input("Password", type="password", key="login_password")
                if st.form_submit_button("Login", use_container_width=True):
                    if not username or not password:
                        st.error("Please enter both username and password.")
                    elif self.admin_backend.authenticate_admin(username, password):
                        auth_token = self.admin_backend.create_auth_token(username)
                        st.session_state['authenticated'] = True
                        st.session_state['username'] = username
                        st.session_state['auth_token'] = auth_token
                        st.query_params['auth_token'] = auth_token
                        st.rerun()
                    else:
                        st.error("Invalid username or password.")
            st.info("Default credentials: admin / admin123")

    def _render_authenticated_ui(self):
        """Render the main UI for authenticated users"""
        client_username = st.session_state.get('username')
        if not client_username:
            st.error("Authentication error: No username found in session.")
            return

        # --- STATE MANAGEMENT FROM URL ---
        query_params = st.query_params
        if 'page' in query_params:
            st.session_state.selected_page = query_params['page']
        else:
            st.session_state.selected_page = list(self._get_section_mapping(client_username).keys())[0]

        section_mapping = self._get_section_mapping(client_username)
        const = AppConstants()

        def get_image_as_base64(path):
            if not os.path.exists(path): return None
            with open(path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode()

        st.markdown("""
        <style>
            section[data-testid="stSidebar"] div[data-testid="stVerticalBlock"] { padding-top: 1.5rem; }
            .sidebar-header { font-size: 1.3rem; font-weight: 700; margin-bottom: 1rem; color: #4b4b4b; text-align: center; }
            .sidebar-welcome { font-size: 0.9rem; margin-bottom: 0.7rem; color: #5a5a5a; font-weight: 500; text-align: center;}
            .sidebar-divider { margin: 1rem 0; border-top: 1px solid #e0e0e0; }
            
            /* Icon-only Clickable Navigation Link - UPDATED SIZES */
            .nav-link {
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 0.5rem; /* Reduced padding for a tighter fit */
                border-radius: 1rem; /* Increased for a rounder look on the larger button */
                margin: 0.5rem auto; /* Increased vertical margin for more spacing */
                width: 75px;  /* Increased width of the clickable area */
                height: 75px; /* Increased height of the clickable area */
                text-decoration: none;
                transition: background-color 0.2s ease-in-out;
            }
            .nav-link:hover {
                background-color: #F0F2F6;
            }
            .nav-link.selected {
                background-color: #e0e0e0;
            }
            .nav-link img {
                width: 50px;  /* Increased avatar width */
                height: 50px; /* Increased avatar height */
                object-fit: contain;
            }
        </style>
        """, unsafe_allow_html=True)

        # --- SIDEBAR RENDERING ---
        with st.sidebar:
            st.markdown('<div class="sidebar-header">Navigation</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="sidebar-welcome">Welcome, {client_username}!</div>', unsafe_allow_html=True)

            if st.button(f"{const.ICONS['logout']} Logout", key="logout_button", use_container_width=True, type="secondary"):
                st.session_state.clear()
                st.query_params.clear()
                st.rerun()

            st.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)

            # --- CLICKABLE AVATAR-ONLY NAVIGATION MENU ---
            nav_html = ""
            auth_token = st.session_state.get('auth_token', '')
            
            for page_title in section_mapping.keys():
                is_selected = (page_title == st.session_state.selected_page)
                selected_class = "selected" if is_selected else ""
                
                avatar_key = page_title.lower()
                avatar_path = const.AVATARS.get(avatar_key)
                base64_image = get_image_as_base64(avatar_path) if avatar_path else None
                
                img_tag = f'<img src="data:image/png;base64,{base64_image}">' if base64_image else "❓"

                href = f"?auth_token={auth_token}&page={page_title}"
                
                # The 'title' attribute creates the tooltip on hover
                nav_html += f"""
                    <a href="{href}" class="nav-link {selected_class}" target="_self" title="{page_title}">
                        {img_tag}
                    </a>
                """
            st.markdown(nav_html, unsafe_allow_html=True)

        # --- MAIN CONTENT AREA ---
        selected_section_title = st.session_state.selected_page
        section_to_render = section_mapping.get(selected_section_title)

        if section_to_render:
            section_to_render.render()
        else:
            st.error(f"Page '{selected_section_title}' not found. Please select a valid section.")

if __name__ == "__main__":
    app = AdminUI()
    app.render()