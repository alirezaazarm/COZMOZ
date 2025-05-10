# Instagram Bot & Assistant

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A Flask-based application that interacts with the Instagram Graph API, acting as an intelligent assistant to process messages, comments, and reactions. It can automate responses and actions using integrations like OpenAI.

## ✨ Features

* **Real-time Instagram Integration:** Processes messages, comments, and reactions via webhooks.
* **Comprehensive Handling:** Manages text, media (images, reels, posts), and shared content in DMs, comments on posts, and message reactions.
* **AI-Powered Assistant:** Optionally uses services like OpenAI to generate automated replies.
* **Image Analysis:** Can analyze images shared in messages (e.g., using a vision model).
* **Scheduled Tasks:** Employs APScheduler for background jobs like:
    * Processing queued incoming messages.
    * Cleaning up old messages.
    * Fetching recent posts and stories.
* **Data Persistence:** Uses MongoDB for storing messages, users, posts, stories, and settings.
* **Modular Architecture:** Organized into Flask blueprints, services, repositories, models, and jobs.

## 🚀 Getting Started

### Prerequisites

* Python 3.x
* MongoDB instance
* Instagram Business Account & Facebook Developer App

### Installation

1.  **Clone the repository:**
    ```bash
    git clone <your_repository_url>
    cd <repository_folder>
    ```
2.  **Set up a virtual environment (recommended):**
    ```bash
    python -m venv venv
    # On macOS/Linux:
    source venv/bin/activate
    # On Windows:
    # venv\Scripts\activate
    ```
3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Configure Environment Variables:**
    Create a `.env` file in the root directory with your credentials:
    ```env
    MONGO_URI=mongodb://localhost:27017/instagram_bot
    PAGE_ID=YOUR_INSTAGRAM_PAGE_ID
    ACCESS_TOKEN=YOUR_INSTAGRAM_GRAPH_API_ACCESS_TOKEN
    VERIFY_TOKEN=YOUR_CUSTOM_WEBHOOK_VERIFY_TOKEN
    APP_ID=YOUR_FACEBOOK_APP_ID
    APP_SECRET=YOUR_FACEBOOK_APP_SECRET
    OPENAI_API_KEY=YOUR_OPENAI_API_KEY # Optional
    ```
5.  **Set up Instagram Webhooks:**
    Configure webhooks in your Facebook App to point to `/webhook` on your server (e.g., `https://your-domain.com/webhook`). Subscribe to `messages`, `comments`, and `message_reactions`.

### Running the Application

1.  **Activate your virtual environment.**
2.  **Start the Flask app:**
    ```bash
    python main.py
    ```

## 🔧 Key Components

* **`main.py`**: Application entry point.
* **`app/config.py`**: Configuration settings.
* **`app/routes/webhook.py`**: Handles Instagram webhook events.
* **`app/services/`**: Contains business logic (Instagram API, OpenAI, message processing).
* **`app/jobs/`**: Manages scheduled tasks via APScheduler.
* **`app/models/`**: Defines MongoDB data schemas.
* **`app/repositories/`**: Handles database interactions.

## 🛠️ Technologies

* Python | Flask
* APScheduler
* PyMongo | MongoDB
* Requests
* OpenAI API (optional)

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.