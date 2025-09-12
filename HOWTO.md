# Newstrack Keyword Automation System - HOWTO Guide

**Version:** 2.0  
**Author:** Manus AI  
**Date:** September 2025  
**System:** Enterprise Newstrack Keyword Processing Platform

## Table of Contents

1. [Introduction](#introduction)
2. [System Architecture](#system-architecture)
3. [Installation and Setup](#installation-and-setup)
4. [Configuration](#configuration)
5. [API Usage](#api-usage)
6. [Batch Processing](#batch-processing)
7. [Guardrails System](#guardrails-system)
8. [Audit and Monitoring](#audit-and-monitoring)
9. [Troubleshooting](#troubleshooting)
10. [Best Practices](#best-practices)
11. [Advanced Usage](#advanced-usage)
12. [References](#references)

---

## Introduction

The Newstrack Keyword Automation System is an enterprise-grade platform designed to automate the complex process of keyword categorization, expansion, and currency validation for news tracking applications. This system transforms the manual three-step ChatGPT workflow described in the original Newstrack Keyword Prompting Cookbook into a robust, scalable, and auditable automated solution.

### What This System Does

The platform automates three critical keyword processing steps that were previously performed manually through ChatGPT interactions. The first step involves intelligent categorization of keywords into three distinct categories: industry terms (general market segments, products, and services), company terms (specific organizational names and brands), and regulatory terms (laws, compliance requirements, and government bodies). This categorization ensures that news tracking systems can properly organize and filter content based on the nature of the keywords being monitored.

The second step focuses on strategic expansion of each category through the addition of relevant terms that enhance the comprehensiveness of keyword coverage. This expansion process leverages advanced language models to identify semantically related terms, industry-specific jargon, and emerging terminology that might be missed in manual keyword compilation. The system ensures that the expanded keyword sets maintain relevance to the target sector while avoiding over-generalization that could lead to noise in news tracking results.

The third and final step implements currency validation, where the system reviews all keywords against current market conditions and removes terms that have become outdated due to company mergers, regulatory changes, market exits, or other temporal factors. This ensures that keyword lists remain current and effective for ongoing news monitoring activities.

### Key Features and Capabilities

The system incorporates several enterprise-grade features that distinguish it from simple automation scripts. The guardrails system provides multiple layers of quality control, including category isolation to prevent keyword leakage between categories, deduplication to eliminate redundant terms, and completeness checking to ensure that all input keywords are properly processed and accounted for in the output.

Comprehensive audit logging creates a complete trail of all processing activities, enabling organizations to track keyword evolution over time, understand processing decisions, and maintain compliance with internal governance requirements. The audit system generates detailed reports that include processing metadata, timing information, and guardrails application results.

The batch processing capability allows organizations to handle large keyword datasets efficiently through intelligent batching, retry logic, and size control mechanisms. This ensures that even extensive keyword lists can be processed reliably without overwhelming the underlying language model APIs or exceeding token limits.

Error handling and recovery mechanisms provide robust operation in production environments, with standardized error responses, automatic retry logic, and graceful degradation when external services are unavailable. The system maintains operational continuity even when individual processing steps encounter temporary failures.




## System Architecture

The Newstrack Keyword Automation System follows a modular, microservices-inspired architecture that separates concerns while maintaining tight integration between components. This design enables scalability, maintainability, and extensibility while providing the reliability required for enterprise deployments.

### Core Components Overview

The system consists of several interconnected components, each responsible for specific aspects of the keyword processing workflow. The Flask API server serves as the primary interface, exposing RESTful endpoints that handle individual processing requests and provide system status information. This API layer implements comprehensive request validation, error handling, and response formatting to ensure consistent behavior across all client interactions.

The Language Model Client component provides a unified interface to multiple LLM providers, currently supporting OpenAI's GPT models with extensibility for additional providers such as Anthropic Claude, Google Gemini, or local model deployments. This abstraction layer enables the system to adapt to changing LLM landscapes and optimize costs by selecting the most appropriate model for each processing task.

The Guardrails Engine implements quality control mechanisms that validate processing results against predefined criteria. This component operates independently of the core processing logic, allowing for flexible configuration of quality standards and the addition of new validation rules without disrupting existing functionality. The guardrails system maintains separate validation logic for each processing step, ensuring that quality controls are appropriately tailored to the specific requirements of categorization, expansion, and currency validation tasks.

The Batch Processor handles large-scale keyword processing operations through intelligent batching strategies, retry logic, and progress tracking. This component implements sophisticated algorithms for determining optimal batch sizes based on token limits, processing complexity, and system load. The batch processor maintains state across processing sessions, enabling resumption of interrupted operations and providing detailed progress reporting for long-running tasks.

The Audit Logger creates comprehensive records of all system activities, maintaining detailed logs in both human-readable and machine-parseable formats. This component implements a dual-logging strategy that combines real-time operational logs with structured audit trails, enabling both immediate troubleshooting and long-term analysis of system behavior and keyword evolution patterns.

### Data Flow Architecture

The system implements a pipeline-based data flow that ensures consistent processing while maintaining flexibility for different use cases. When a processing request is received through the API, the system first validates the input data against predefined schemas, checking for required fields, data types, and business rule compliance. This validation step prevents invalid data from entering the processing pipeline and provides immediate feedback to clients about data quality issues.

Following successful validation, the system generates a unique batch identifier and initializes audit logging for the processing session. This identifier serves as a correlation key that links all processing activities, log entries, and audit records associated with the specific request. The batch identifier enables comprehensive tracking of processing activities and facilitates troubleshooting when issues arise.

The validated data then enters the core processing pipeline, where it progresses through the three main processing steps in sequence. Each step receives the output from the previous step as input, creating a natural data flow that mirrors the original manual process while adding automated quality controls and error handling. The pipeline implements checkpoint mechanisms that allow for recovery from failures and enable partial processing results to be preserved even when later steps encounter errors.

Throughout the processing pipeline, the guardrails engine continuously monitors data quality and processing integrity. This monitoring occurs at multiple points within each processing step, checking for category isolation, duplicate detection, and completeness validation. The guardrails system operates in parallel with the main processing flow, ensuring that quality controls do not introduce significant latency while maintaining comprehensive coverage of potential quality issues.

Upon completion of the processing pipeline, the system generates comprehensive output that includes the processed keyword categories, metadata about the processing session, guardrails application results, and audit trail information. This output is formatted according to standardized schemas that ensure consistency across different client applications and enable automated processing of results by downstream systems.

### Scalability and Performance Considerations

The system architecture incorporates several design patterns that support horizontal and vertical scaling as processing demands increase. The stateless design of the API layer enables multiple server instances to handle requests concurrently without coordination overhead. Load balancing can be implemented at the API layer to distribute requests across multiple server instances, providing both increased capacity and improved fault tolerance.

The modular component design enables selective scaling of individual system components based on specific performance bottlenecks. For example, if LLM API calls become a limiting factor, additional instances of the Language Model Client can be deployed with appropriate load balancing and rate limiting. Similarly, if audit logging becomes a performance concern, the Audit Logger can be scaled independently or replaced with more performant logging solutions.

The batch processing component implements intelligent queuing and scheduling mechanisms that optimize resource utilization while maintaining processing quality. These mechanisms include dynamic batch size adjustment based on system load, priority-based processing for urgent requests, and resource pooling to minimize overhead from frequent LLM API connections.

Caching strategies are implemented at multiple levels to reduce redundant processing and improve response times. The system maintains caches of frequently used prompts, model responses for identical inputs, and guardrails validation results. These caches are designed with appropriate invalidation strategies to ensure data freshness while maximizing performance benefits.

### Security and Compliance Architecture

The system implements comprehensive security measures that protect sensitive data throughout the processing pipeline while maintaining compliance with relevant data protection regulations. All API communications are secured through HTTPS encryption, and the system supports multiple authentication mechanisms including API keys, OAuth 2.0, and JWT tokens.

Data handling procedures ensure that sensitive keyword information is processed securely and retained only for the minimum time necessary to complete processing and maintain audit requirements. The system implements data classification mechanisms that identify sensitive keywords and apply appropriate handling procedures based on organizational policies.

Access control mechanisms provide fine-grained permissions for different system functions, enabling organizations to implement role-based access controls that align with their security policies. Administrative functions, audit log access, and configuration changes are protected through separate permission levels that prevent unauthorized system modifications.

Audit logging includes security-relevant events such as authentication attempts, authorization failures, and data access patterns. These security logs are maintained separately from operational logs and can be integrated with external security information and event management (SIEM) systems for comprehensive security monitoring.


## Installation and Setup

The Newstrack Keyword Automation System requires a Python 3.11+ environment with specific dependencies and configuration settings. This section provides comprehensive instructions for setting up the system in development, staging, and production environments.

### Prerequisites and System Requirements

Before beginning the installation process, ensure that your system meets the minimum requirements for running the Newstrack automation platform. The system requires Python 3.11 or later, with Python 3.11 being the recommended version for optimal compatibility with all dependencies. The system has been tested extensively on Ubuntu 22.04 LTS, but should function correctly on other Linux distributions, macOS, and Windows environments with appropriate Python installations.

Memory requirements vary based on the expected processing load and batch sizes. For development environments, a minimum of 4GB RAM is recommended, while production deployments should provision at least 8GB RAM to handle concurrent processing requests and maintain adequate performance margins. Storage requirements are modest for the application itself, but audit logging and result storage may require significant disk space over time, particularly in high-volume environments.

Network connectivity is essential for accessing external LLM APIs, with stable internet connections required for reliable operation. The system implements retry logic and error handling for network issues, but consistent connectivity ensures optimal performance and user experience. Firewall configurations should allow outbound HTTPS connections to LLM provider endpoints, typically on port 443.

### Environment Setup and Dependency Installation

Begin the installation process by creating a dedicated Python virtual environment to isolate the system dependencies from other Python applications on the host system. This isolation prevents dependency conflicts and enables easier maintenance and updates. Navigate to your desired installation directory and create a new virtual environment using the following commands:

```bash
python3.11 -m venv newstrack-env
source newstrack-env/bin/activate  # On Windows: newstrack-env\Scripts\activate
```

With the virtual environment activated, install the required Python dependencies using the provided requirements file. The system dependencies include Flask for the web framework, Flask-CORS for cross-origin resource sharing, OpenAI for language model integration, PyYAML for configuration file parsing, and Requests for HTTP client functionality. Additional dependencies support logging, error handling, and data validation functions.

```bash
pip install -r requirements.txt
```

If a requirements file is not available, install the core dependencies manually:

```bash
pip install flask flask-cors openai pyyaml requests
```

### Directory Structure and File Organization

The system follows a standardized directory structure that organizes components logically and supports maintainable deployments. Create the following directory structure in your installation location:

```
newstrack-automation/
├── src/
│   ├── main.py
│   ├── routes/
│   │   └── newstrack.py
│   ├── utils/
│   │   ├── llm_client.py
│   │   ├── guardrails.py
│   │   ├── audit.py
│   │   ├── batch_processor.py
│   │   └── error_handler.py
│   └── static/
│       └── index.html
├── guards/
│   ├── industry.txt
│   ├── company.txt
│   └── regulatory.txt
├── data/
│   └── keywords_sample.csv
├── results/
├── config.yml
├── run.py
└── run_app.py
```

This structure separates application code, configuration files, data files, and output directories to maintain organization and support different deployment scenarios. The `src` directory contains all application code, while `guards` contains guardrails configuration files, `data` holds input files for batch processing, and `results` stores processing outputs and audit logs.

### Configuration File Setup

The system uses a YAML configuration file to manage settings and parameters that may vary between environments. Create a `config.yml` file in the root directory with the following structure:

```yaml
# Newstrack Batch Runner Configuration

# Default batch processing settings
batch_size: 300
max_retries: 3
retry_delay_seconds: 2

# API settings
api_base_url: "http://localhost:3000/api"
timeout_seconds: 300

# Processing settings
default_sector: "general"
default_date: "2025-08"

# Search settings (for future expansion)
search_mode: "off"  # off, fast, deep

# File paths
input_file: "data/keywords.csv"
output_dir: "results"

# Logging
log_level: "INFO"
log_file: "batch_runner.log"
```

Adjust these settings based on your specific requirements and environment constraints. The batch size parameter controls how many keywords are processed in each API call, with larger values improving efficiency but potentially exceeding token limits. The retry settings determine how the system handles temporary failures, while timeout settings control how long the system waits for API responses.

### Environment Variables and API Keys

The system requires access to language model APIs, which necessitates proper configuration of API keys and authentication credentials. Set the following environment variables in your deployment environment:

```bash
export OPENAI_API_KEY="your-openai-api-key-here"
export OPENAI_API_BASE="https://api.openai.com/v1"  # Optional, uses default if not set
export MODEL_NAME="gpt-4.1-mini"  # Optional, uses default if not set
export LLM_PROVIDER="openai"  # Optional, uses default if not set
export FLASK_DEBUG="false"  # Set to "true" for development environments
export APP_SECRET="your-secret-key-for-production"  # Change for production deployments
```

For production deployments, ensure that API keys are stored securely and not exposed in configuration files or version control systems. Consider using environment variable management tools, secret management services, or configuration management systems to handle sensitive credentials appropriately.

### Database Initialization and Setup

The system uses SQLite for local data storage, primarily for user management and session tracking. The database is automatically initialized when the application starts, but you may need to create the database directory structure manually in some environments:

```bash
mkdir -p src/database
```

The application will create the necessary database files and tables automatically during the first startup. For production deployments, consider migrating to more robust database systems such as PostgreSQL or MySQL if concurrent access or advanced database features are required.

### Guardrails Configuration

The guardrails system requires configuration files that define category-specific keywords for validation purposes. Create the following files in the `guards` directory:

**guards/industry.txt:**
```
insurance
banking
healthcare
technology
manufacturing
retail
automotive
energy
telecommunications
financial services
```

**guards/company.txt:**
```
Santam
Old Mutual
Discovery
Standard Bank
FNB
ABSA
Nedbank
Capitec
Investec
African Bank
```

**guards/regulatory.txt:**
```
FSCA
SARB
Prudential Authority
National Credit Regulator
Competition Commission
POPI Act
Basel III
Solvency II
IFRS
King IV
```

These files serve as reference lists for the guardrails system to validate keyword categorization and detect potential category leakage. Customize these lists based on your specific industry focus and regulatory environment.

### Testing the Installation

After completing the installation and configuration steps, test the system to ensure proper functionality. Start the Flask application using the provided runner script:

```bash
python run_app.py
```

The application should start successfully and display startup messages indicating that the server is running on the configured port (default: 3000). Access the web interface by navigating to `http://localhost:3000` in your web browser. The interface should load properly and display the keyword processing form.

Test the API endpoints directly using curl or similar tools:

```bash
curl -X GET http://localhost:3000/api/healthz
curl -X GET http://localhost:3000/api/status
```

These endpoints should return successful responses indicating that the system is operational and ready to process keyword requests.

### Production Deployment Considerations

For production deployments, several additional considerations ensure reliable and secure operation. Configure a production-grade web server such as Nginx or Apache to serve as a reverse proxy for the Flask application. This configuration provides better performance, security, and monitoring capabilities compared to running Flask directly.

Implement process management using tools such as systemd, supervisor, or Docker to ensure that the application restarts automatically after system reboots or application crashes. Configure appropriate logging levels and log rotation to manage disk space usage while maintaining adequate audit trails.

Set up monitoring and alerting systems to track application performance, error rates, and resource utilization. Consider implementing health checks and automated recovery procedures to minimize downtime and ensure consistent service availability.

Configure backup procedures for audit logs, configuration files, and any persistent data to ensure business continuity and compliance with data retention requirements. Test backup and recovery procedures regularly to verify their effectiveness and identify potential issues before they impact production operations.


## Configuration

The Newstrack Keyword Automation System provides extensive configuration options that enable customization for different environments, use cases, and organizational requirements. This section details all available configuration parameters and their effects on system behavior.

### Application Configuration Parameters

The primary application configuration is managed through environment variables and the YAML configuration file. Environment variables take precedence over configuration file settings, enabling flexible deployment scenarios where sensitive information is managed separately from application code.

The `MODEL_NAME` parameter controls which language model is used for processing requests. The default value of "gpt-4.1-mini" provides an optimal balance of processing quality and cost efficiency for most use cases. Alternative models such as "gpt-4" can be specified for scenarios requiring maximum processing quality, while "gpt-3.5-turbo" may be appropriate for cost-sensitive applications with less stringent quality requirements.

The `LLM_PROVIDER` parameter enables selection of different language model providers, with "openai" being the current default and primary supported option. The system architecture supports extension to additional providers such as "anthropic" for Claude models or "google" for Gemini models, though these integrations require additional development work.

Batch processing behavior is controlled through several parameters in the configuration file. The `batch_size` parameter determines how many keywords are processed in each API call, with the default value of 300 providing good performance while staying within typical token limits. Larger batch sizes improve efficiency but may exceed model context windows or API rate limits, while smaller batch sizes provide more granular error handling at the cost of increased API overhead.

The retry mechanism is configured through `max_retries` and `retry_delay_seconds` parameters. The default configuration attempts up to 3 retries with a 2-second delay between attempts, providing resilience against temporary API failures while avoiding excessive delays. The exponential backoff strategy automatically increases delay times for subsequent retries, reducing the likelihood of overwhelming external services during outage conditions.

### Guardrails Configuration Management

The guardrails system uses text files in the `guards` directory to define category-specific keyword lists that validate processing results. These files serve as reference datasets for detecting category leakage, where keywords intended for one category appear in another category's output.

The industry guardrails file (`guards/industry.txt`) should contain general industry terms, market segments, product categories, and service types that are relevant to your organization's monitoring scope. This file helps ensure that industry-specific keywords are properly categorized and prevents them from being misclassified as company or regulatory terms.

The company guardrails file (`guards/company.txt`) should include specific organization names, brand names, subsidiary companies, and other entity-specific identifiers. This file is particularly important for preventing company names from being categorized as industry or regulatory terms, which could lead to incorrect news filtering and monitoring results.

The regulatory guardrails file (`guards/regulatory.txt`) should contain regulatory bodies, legislation names, compliance frameworks, and other governance-related terms. This categorization is crucial for organizations that need to monitor regulatory developments separately from industry news and company-specific information.

These guardrails files should be updated regularly to reflect changes in your monitoring scope, new companies entering your market, regulatory changes, and evolving industry terminology. The system automatically reloads these files for each processing request, so updates take effect immediately without requiring application restarts.

### Logging and Audit Configuration

The system implements comprehensive logging at multiple levels to support both operational monitoring and compliance requirements. The `log_level` parameter controls the verbosity of operational logs, with "INFO" providing a good balance of detail and performance for most environments. "DEBUG" level logging provides extensive detail for troubleshooting but may impact performance and generate large log files in high-volume environments.

Audit logging operates independently of operational logging and cannot be disabled, ensuring that all processing activities are recorded for compliance and analysis purposes. Audit logs are stored in structured JSON format in the `results` directory, with separate files for each processing batch to facilitate analysis and archival.

Log rotation and retention policies should be configured based on your organization's compliance requirements and storage constraints. The system does not implement automatic log rotation, so external tools such as logrotate should be configured to manage log file sizes and retention periods.

### API Rate Limiting and Throttling

The system implements intelligent rate limiting to prevent overwhelming external LLM APIs while maintaining optimal processing throughput. The rate limiting mechanism monitors API response times and error rates to automatically adjust request frequency based on current service conditions.

The `timeout_seconds` parameter controls how long the system waits for API responses before considering a request failed. The default value of 300 seconds (5 minutes) accommodates the processing time required for large keyword batches while preventing indefinite waits for unresponsive services.

Concurrent request limiting prevents the system from overwhelming external APIs with simultaneous requests. The default configuration processes requests sequentially to ensure predictable behavior and avoid rate limiting penalties from API providers. For high-volume environments, this behavior can be modified to allow limited concurrency while respecting API provider guidelines.

### Security Configuration Options

Security configuration encompasses authentication, authorization, data protection, and audit trail management. The `APP_SECRET` environment variable provides the cryptographic key used for session management and security token generation. This value must be changed from the default for production deployments and should be generated using cryptographically secure random number generators.

API authentication can be configured to use various mechanisms including API keys, OAuth 2.0 tokens, or JWT authentication. The default configuration operates without authentication for development environments, but production deployments should implement appropriate authentication mechanisms based on organizational security policies.

Data encryption settings control how sensitive information is protected during processing and storage. While the system does not store keyword data permanently, temporary files and audit logs may contain sensitive information that requires protection according to organizational data classification policies.

## API Usage

The Newstrack Keyword Automation System exposes a comprehensive RESTful API that enables integration with external systems and provides programmatic access to all keyword processing functions. This section provides detailed documentation for all available endpoints, request formats, and response structures.

### Authentication and Authorization

API access requires proper authentication credentials, which vary based on the deployment configuration. For development environments, the API may operate without authentication, while production deployments typically require API keys or OAuth tokens. Include authentication credentials in the request headers using the appropriate format for your deployment:

```bash
# API Key authentication
curl -H "Authorization: Bearer your-api-key" http://localhost:3000/api/status

# OAuth 2.0 authentication
curl -H "Authorization: Bearer your-oauth-token" http://localhost:3000/api/status
```

All API requests must include appropriate Content-Type headers for requests containing JSON data. The system validates request formats strictly and returns detailed error messages for malformed requests.

### Health and Status Endpoints

The system provides several endpoints for monitoring health and operational status. These endpoints are essential for load balancer health checks, monitoring systems, and operational dashboards.

**GET /api/healthz**

The health check endpoint provides a simple binary indication of system availability. This endpoint performs basic system checks including database connectivity, configuration validation, and external service availability. A successful response indicates that the system is operational and ready to process requests.

```bash
curl -X GET http://localhost:3000/api/healthz
```

Response format:
```json
{
  "status": "healthy",
  "timestamp": "2025-09-09T10:30:00Z",
  "version": "2.0",
  "checks": {
    "database": "ok",
    "llm_provider": "ok",
    "guardrails": "ok"
  }
}
```

**GET /api/status**

The status endpoint provides detailed information about system state, processing statistics, and configuration details. This endpoint is useful for monitoring dashboards and operational analysis.

```bash
curl -X GET http://localhost:3000/api/status
```

Response format:
```json
{
  "system_status": "operational",
  "uptime_seconds": 86400,
  "version": "2.0",
  "configuration": {
    "model_name": "gpt-4.1-mini",
    "provider": "openai",
    "batch_size": 300
  },
  "statistics": {
    "total_requests": 1250,
    "successful_requests": 1200,
    "failed_requests": 50,
    "average_processing_time_ms": 15000
  },
  "manifest": {
    "totals": {
      "total_batches": 45,
      "total_keywords_processed": 13500,
      "total_processing_time_ms": 675000
    }
  }
}
```

### Keyword Processing Endpoints

The core functionality of the system is exposed through several processing endpoints that correspond to the three main processing steps and combinations thereof.

**POST /api/categorize**

The categorization endpoint processes a list of keywords and organizes them into industry, company, and regulatory categories. This endpoint implements the first step of the original manual process and provides the foundation for subsequent processing steps.

Request format:
```json
{
  "sector": "short-term insurance",
  "company": "Santam",
  "keywords": "Santam\nOld Mutual Insure\nDiscovery Insure\ninsurance claims\nmotor insurance\nFSCA regulations"
}
```

The `sector` field is required and should contain a descriptive name for the industry or market segment being analyzed. The `company` field is optional and provides context for company-specific keyword categorization. The `keywords` field contains the list of keywords to be processed, with keywords separated by newlines or commas.

Response format:
```json
{
  "batch_id": "batch_20250909_103000_abc123",
  "timing_ms": 12500,
  "processed_count": 6,
  "categories": {
    "industry": ["insurance claims", "motor insurance"],
    "company": ["Santam", "Old Mutual Insure", "Discovery Insure"],
    "regulatory": ["FSCA regulations"]
  },
  "guardrails": {
    "duplicates_dropped": [],
    "leaks_blocked": [],
    "completeness_check": {
      "is_complete": true,
      "missing_keywords": []
    }
  }
}
```

**POST /api/expand**

The expansion endpoint takes categorized keywords and adds relevant terms to each category to improve coverage and monitoring effectiveness. This endpoint implements the second step of the processing workflow and builds upon the categorization results.

Request format:
```json
{
  "sector": "short-term insurance",
  "company": "Santam",
  "keywords": "Santam\nOld Mutual Insure\nDiscovery Insure\ninsurance claims\nmotor insurance\nFSCA regulations"
}
```

The request format is identical to the categorization endpoint, as the expansion process includes categorization as a prerequisite step.

Response format:
```json
{
  "batch_id": "batch_20250909_103100_def456",
  "timing_ms": 18750,
  "processed_count": 6,
  "categories": {
    "industry": [
      "insurance claims", "motor insurance", "vehicle insurance",
      "auto insurance", "car insurance", "third party insurance",
      "comprehensive insurance", "collision coverage"
    ],
    "company": [
      "Santam", "Old Mutual Insure", "Discovery Insure",
      "Santam Limited", "Old Mutual Insurance", "Discovery Insurance"
    ],
    "regulatory": [
      "FSCA regulations", "Financial Sector Conduct Authority",
      "Prudential Authority", "insurance regulation", "compliance requirements"
    ]
  },
  "guardrails": {
    "duplicates_dropped": ["motor insurance", "car insurance"],
    "leaks_blocked": [],
    "completeness_check": {
      "is_complete": true,
      "missing_keywords": []
    }
  }
}
```

**POST /api/drop**

The drop endpoint removes outdated keywords from the provided list based on current market conditions and temporal relevance. This endpoint implements the third step of the processing workflow and requires a date context for currency evaluation.

Request format:
```json
{
  "sector": "short-term insurance",
  "company": "Santam",
  "keywords": "Santam\nOld Mutual Insure\nDiscovery Insure\ninsurance claims\nmotor insurance\nFSCA regulations",
  "date": "2025-08"
}
```

The `date` field is required for this endpoint and should specify the current date context for evaluating keyword currency. The format can be flexible (e.g., "2025-08", "August 2025", "2025-08-15") as the system uses natural language processing to interpret date specifications.

**POST /api/process-all**

The comprehensive processing endpoint executes all three processing steps in sequence, providing a complete keyword processing workflow in a single API call. This endpoint is the most commonly used for complete keyword processing tasks.

Request format:
```json
{
  "sector": "short-term insurance",
  "company": "Santam",
  "keywords": "Santam\nOld Mutual Insure\nDiscovery Insure\ninsurance claims\nmotor insurance\nFSCA regulations",
  "date": "2025-08"
}
```

Response format:
```json
{
  "batch_id": "batch_20250909_103200_ghi789",
  "timing_ms": 35000,
  "processed_count": 6,
  "result": {
    "final_result": {
      "updated": {
        "industry": ["insurance claims", "motor insurance", "vehicle insurance"],
        "company": ["Santam", "Old Mutual Insure", "Discovery Insure"],
        "regulatory": ["FSCA regulations", "Financial Sector Conduct Authority"]
      }
    }
  },
  "guardrails": {
    "duplicates_dropped": ["auto insurance", "comprehensive insurance"],
    "leaks_blocked": [],
    "completeness_check": {
      "is_complete": true,
      "missing_keywords": []
    }
  }
}
```

### Error Handling and Response Codes

The API implements comprehensive error handling with standardized error response formats that provide detailed information about failures and guidance for resolution. All error responses include correlation identifiers that facilitate troubleshooting and support requests.

Common HTTP status codes and their meanings:

- **200 OK**: Request processed successfully
- **400 Bad Request**: Invalid request format or missing required fields
- **401 Unauthorized**: Authentication credentials missing or invalid
- **422 Unprocessable Entity**: Request format valid but processing failed due to business logic constraints
- **429 Too Many Requests**: Rate limiting applied due to excessive request frequency
- **500 Internal Server Error**: Unexpected system error occurred
- **502 Bad Gateway**: External service (LLM API) unavailable or returned error

Error response format:
```json
{
  "error": "Validation failed: Missing required field 'sector'",
  "error_code": "VALIDATION_ERROR",
  "status_code": 400,
  "timestamp": "2025-09-09T10:35:00Z",
  "request_id": "req_abc123def456",
  "details": {
    "missing_fields": ["sector"],
    "provided_fields": ["keywords"]
  }
}
```

### Request Idempotency and Retry Logic

The API supports idempotent requests through the use of idempotency keys, which prevent duplicate processing when requests are retried due to network issues or client-side failures. Include an idempotency key in the request headers to enable this functionality:

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "X-Idempotency-Key: unique-request-identifier-123" \
  -d '{"sector": "insurance", "keywords": "test keywords"}' \
  http://localhost:3000/api/categorize
```

The system maintains idempotency key records for 24 hours, after which duplicate requests with the same key will be processed as new requests. This time window balances duplicate prevention with storage efficiency.

