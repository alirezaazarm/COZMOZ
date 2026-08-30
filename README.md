# Multi-Platform Bot & Assistant

## OpenAI Responses API migration

This project uses the Responses API and `file_search` with each client's
existing Vector Store. Assistant and Thread IDs are no longer used. After
deploying, run `python scripts/migrate_assistants_to_responses.py` once to add
the per-client AI configuration and clear non-migratable legacy thread state.
Configure the prompt, temperature and top-p in the AI dashboard; the default
model for new clients is `gpt-4.1-mini`.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A Flask-based multi-client application that interacts with Instagram and Telegram, acting as an intelligent assistant to process messages, comments, and reactions. It can automate responses and actions using integrations like OpenAI.

## ✨ Features

*   **Multi-Platform Integration:** Supports real-time interaction with both Instagram (messages, comments, reactions) and Telegram.
*   **Multi-Client Architecture:** Designed to serve multiple clients, each with their own configurable settings and platform integrations.
*   **AI-Powered Assistant:** Leverages services like OpenAI to generate automated replies and analyze images.
*   **Comprehensive Handling:** Manages text, media (images, reels, posts), and shared content in DMs, comments, and messages.
*   **Web-Based Dashboard:** Includes a dashboard for managing clients, viewing platform-specific data, and interacting with the system.
*   **Scheduled Tasks:** Employs APScheduler for background jobs like processing message queues, cleaning up old data, and fetching recent content.
*   **Data Persistence:** Uses MongoDB for storing messages, users, posts, stories, and client settings.
*   **Modular and Scalable:** Organized into Flask blueprints, services, repositories, and models for maintainability and future expansion.
*   **Memory Reload:** Provides an endpoint to dynamically reload application memory from the database without a full restart.

## 🚀 Getting Started

### Prerequisites

*   Python 3.x
*   MongoDB instance
*   Instagram Business Account & Facebook Developer App (for Instagram integration)
*   Telegram Bot Token (for Telegram integration)

### Installation

1.  **Clone the repository:**
    ```bash
    git clone <your_repository_url>
    cd <repository_folder>
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configure your environment:**
    *   Create a `.env` file based on the `.env.example` (you might need to create this file).
    *   Fill in your database credentials, API keys, and other necessary configurations.

4.  **Run the application:**
    ```bash
    python main.py
    ```

## Architecture

The application follows a modular architecture:

*   **`main.py`**: The entry point of the application.
*   **`app/`**: The main application package.
    *   **`routes/`**: Flask blueprints for handling webhooks and API endpoints.
    *   **`services/`**: Business logic, including platform-specific services, AI integrations, and the core mediator.
    *   **`repositories/`**: Data access layer for interacting with the MongoDB database.
    *   **`models/`**: Data models for clients, users, messages, and other entities.
    *   **`jobs/`**: Scheduled tasks for background processing.
    *   **`dashboards/`**: UI and backend for the management dashboard.
    *   **`config.py`**: Application configuration.

## Configuration

Client-specific configurations, including platform settings, API keys, and assistant behavior, are stored in the database and managed through the client management features of the application.

Copy `.env.example` to `.env` and populate the required values before starting
the Flask application or Streamlit dashboard. `MONGODB_URI` and
`MONGODB_DB_NAME` are both required; an absent database name prevents PyMongo
from initializing the application.

## API Endpoints

*   **`/reload-memory` (POST):** Reloads the main application memory from the database. This is useful for applying configuration changes without restarting the server.
