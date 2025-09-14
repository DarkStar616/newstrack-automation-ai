# Newstrack Keyword Automation System

**Last Updated:** September 12, 2025

## Overview

The Newstrack Keyword Automation System is an enterprise-grade Flask web application designed to automate keyword processing and categorization for news tracking. The system transforms manual ChatGPT workflows into a robust, scalable platform with audit trails and guardrails.

## Recent Changes
- **2025-09-14:** **MAJOR OVERHAUL:** Removed all implicit test-mode behavior and made LIVE mode the default across the entire application
- **2025-09-14:** Updated default configuration: search_mode="shallow", provider="google", LLM_TEST_MODE=false, SEARCH_TEST_MODE=false
- **2025-09-14:** Enhanced LLM client to support Google Gemini 1.5 Flash as the default provider (was OpenAI)
- **2025-09-14:** Added comprehensive runtime configuration transparency with debug endpoints and mode badges
- **2025-09-14:** Implemented security hardening with XSS prevention, HTML escaping, and input sanitization
- **2025-09-14:** Fixed json import bug in search client that was causing 500 errors in live mode
- **2025-09-14:** Added cache management with TTL controls and bypass functionality for evidence gathering
- **2025-09-12:** Successfully migrated from GitHub import to Replit environment
- **2025-09-12:** Configured Flask app to run on port 5000 with proper CORS for Replit proxy/iframe access
- **2025-09-12:** Set up Python 3.11 environment with all required dependencies
- **2025-09-12:** Configured deployment settings for autoscale production deployment
- **2025-09-12:** Added Python .gitignore for proper version control
- **2025-09-12:** **MAJOR FEATURE:** Implemented Evidence Mode for Step 3 with Perplexity Sonar API integration
- **2025-09-12:** Extended audit system with comprehensive evidence tracking and manifest totals
- **2025-09-12:** Added configurable search modes (off/test/shallow) with test mode support

## Project Architecture

### Core Components
- **Flask Web Server:** Main application running on port 5000
- **Frontend:** Single-page application served from `src/static/index.html`
- **API Endpoints:** RESTful API at `/api/*` for keyword processing
- **Database:** SQLite database for user management and session tracking
- **Batch Processing:** Separate `run.py` script for large-scale keyword processing

### Key Features
- Three-step keyword processing: Categorize → Expand → Drop Outdated
- **Evidence Mode**: Step 3 uses Perplexity Sonar API to validate keyword relevance with real news articles
- Guardrails system with quality control and validation
- Comprehensive audit logging with evidence tracking
- Web interface for manual processing
- Batch processing capabilities for large datasets
- Configurable search modes: off (disabled), test (mock evidence), shallow (recent news only)

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
- **Perplexity Sonar API** for Evidence Mode news article search
- httpx for HTTP client operations
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

## Evidence Mode Configuration

### Search Modes
- **shallow**: Searches recent news articles via Google Gemini 1.5 Flash with search grounding (default)
- **test**: Uses mock evidence for testing (only when explicitly requested)
- **off**: Evidence gathering disabled

### Environment Variables
- `LLM_TEST_MODE=false`: Disabled by default, uses Google Gemini 1.5 Flash for live processing
- `SEARCH_TEST_MODE=false`: Disabled by default, uses Google search grounding for live evidence
- `SEARCH_MODE=shallow`: Default live mode with 3-month recency window
- `SEARCH_PROVIDER=google`: Default provider using Google Gemini with search capabilities
- `GOOGLE_API_KEY`: Required for live evidence gathering and LLM processing
- `PERPLEXITY_API_KEY`: Optional alternative provider for evidence gathering

### Evidence Tracking
- Audit logs include complete evidence metrics per batch
- Manifest tracks evidence totals across all batches
- API responses include evidence_refs with news article citations

## Known Issues
- Minor LSP diagnostics in `run.py` (batch processing script) - does not affect web application
- Development server warning - resolved in production via WSGI server

## User Preferences
- None specified yet

## Next Steps (Optional)
- Set up OpenAI API key for keyword processing functionality
- **Set up Perplexity API key for Evidence Mode in production**
- Consider PostgreSQL migration for production if concurrent access needed
- Add production WSGI server configuration
- Implement tighter CORS restrictions for production deployment