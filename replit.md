# Newstrack Keyword Automation System

**Last Updated:** September 12, 2025

## Overview

The Newstrack Keyword Automation System is an enterprise-grade Flask web application designed to automate keyword processing and categorization for news tracking. The system transforms manual ChatGPT workflows into a robust, scalable platform with audit trails and guardrails.

## Recent Changes
- **2025-09-12:** Successfully migrated from GitHub import to Replit environment
- **2025-09-12:** Configured Flask app to run on port 5000 with proper CORS for Replit proxy/iframe access
- **2025-09-12:** Set up Python 3.11 environment with all required dependencies
- **2025-09-12:** Configured deployment settings for autoscale production deployment
- **2025-09-12:** Added Python .gitignore for proper version control

## Project Architecture

### Core Components
- **Flask Web Server:** Main application running on port 5000
- **Frontend:** Single-page application served from `src/static/index.html`
- **API Endpoints:** RESTful API at `/api/*` for keyword processing
- **Database:** SQLite database for user management and session tracking
- **Batch Processing:** Separate `run.py` script for large-scale keyword processing

### Key Features
- Three-step keyword processing: Categorize → Expand → Drop Outdated
- Guardrails system with quality control and validation
- Comprehensive audit logging
- Web interface for manual processing
- Batch processing capabilities for large datasets

## Technical Configuration

### Runtime Environment
- **Python Version:** 3.11
- **Web Framework:** Flask 3.1.1
- **Port:** 5000 (configured for Replit)
- **Host:** 0.0.0.0 (allows proxy/iframe access)
- **CORS:** Enabled globally for cross-origin requests

### Dependencies
- Flask ecosystem (Flask, Flask-CORS, Flask-SQLAlchemy)
- OpenAI API integration for language model processing
- SQLAlchemy for database operations
- PyYAML for configuration management

### File Structure
```
├── src/
│   ├── main.py          # App definition with middleware
│   ├── routes/          # API route handlers
│   ├── models/          # Database models
│   ├── utils/           # Utilities (LLM client, guardrails, etc.)
│   ├── static/          # Frontend files
│   └── database/        # SQLite database storage
├── guards/              # Guardrails configuration files
├── data/                # Input data for batch processing
├── run_app.py           # Flask application runner
├── run.py               # Batch processing script
└── config.yml           # Application configuration
```

## Deployment

### Development (Current)
- Runs via Replit workflow: `python run_app.py`
- Accessible through Replit's web preview on port 5000
- SQLite database for local storage

### Production
- Configured for autoscale deployment
- Build step installs requirements via pip
- Runs the same Flask application
- Requires OpenAI API key configuration

## Known Issues
- Minor LSP diagnostics in `run.py` (batch processing script) - does not affect web application
- Development server warning - resolved in production via WSGI server

## User Preferences
- None specified yet

## Next Steps (Optional)
- Set up OpenAI API key for keyword processing functionality  
- Consider PostgreSQL migration for production if concurrent access needed
- Add production WSGI server configuration
- Implement tighter CORS restrictions for production deployment