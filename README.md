# Graphix - Vulnerability Detection & Patch Generation Framework

This repository contains a comprehensive framework for automated software vulnerability detection and patch generation. It leverages Large Language Models (LLMs), Graph Databases (Neo4j), and Vector Databases (Weaviate) to analyze codebases, identify vulnerabilities, and suggest fixes.

## Features

*   **Knowledge Base Construction**: Parses source code into a graph structure (Neo4j) and vector embeddings (Weaviate) for deep semantic understanding.
*   **Vulnerability Detection**: Uses advanced query analysis to find potential security flaws.
*   **Automated Patch Generation**: Integrates with LLMs to generate code patches for identified vulnerabilities.
*   **Patch Scoring**: Evaluates generated patches based on various metrics.
*   **Workflow Automation**: End-to-end pipeline from dataset loading to patch generation.

## Prerequisites

Before you begin, ensure you have the following installed:

*   **Operating System**: Windows, macOS, or Linux.
*   **Python**: Version 3.10 or 3.11.
*   **Docker Desktop**: Required for running Neo4j and Weaviate databases.
*   **Git**: For version control.

## Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd Graphix_
```

### 2. Set Up Virtual Environment

It is recommended to use a virtual environment to manage dependencies.

**Windows:**
```powershell
python -m venv venv
.\venv\Scripts\activate
```

**macOS/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

Install the required Python packages using `pip`:

```bash
pip install -r requirements.txt
```

## Database Setup

This project requires two database services running via Docker: **Neo4j** (Graph DB) and **Weaviate** (Vector DB).

### 1. Start Neo4j (Graph Database)

Run the following command to start the Neo4j container. This command sets up persistence and authentication.

**Windows (PowerShell):**
```powershell
docker run `
    --name neo4j_graph_db `
    -p 7474:7474 -p 7687:7687 `
    -v ${PWD}/data/neo4j_data:/data `
    -v ${PWD}/data/neo4j_conf:/conf `
    -v ${PWD}/data/neo4j_logs:/logs `
    --env NEO4J_AUTH=neo4j/your_strong_password `
    --env NEO4J_ACCEPT_LICENSE_AGREEMENT=yes `
    -d neo4j:5.21.0-community
```

*   **Note**: Replace `your_strong_password` with a secure password. You will need this for configuration.
*   **Access**: Neo4j Browser is available at `http://localhost:7474`.

### 2. Start Weaviate (Vector Database)

Weaviate is configured via `docker-compose.yml`.

```bash
docker-compose up -d
```

*   **Access**: Weaviate API is available at `http://localhost:8080`.

## Configuration

1.  **Environment Variables**: Create a `.env` file in the root directory to store your API keys and database credentials.

    ```env
    # Sample LLM API Keys
    OPENAI_API_KEY=your_openai_api_key
    GOOGLE_API_KEY=your_google_api_key
    ...

    # Neo4j Configuration
    NEO4J_URI=bolt://localhost:7687
    NEO4J_USER=neo4j
    NEO4J_PASSWORD=your_strong_password

    # Weaviate Configuration
    WEAVIATE_URL=http://localhost:8080
    ```

2.  **Create Configuration File (Required)**

    **Important**: The `knowledge_base/config.py` file is needed to run this project but is not included in the repository (it contains sensitive credentials and is git-ignored for security).

**You need to create this file manually before running the project.**

#### Steps:

1.  Create a new file at `knowledge_base/config.py`
2.  Copy and paste the following template:

    ```python
    import os

    # --- Database Configuration ---

    # Weaviate Configuration
    WEAVIATE_URL = "http://localhost:8080"  # for local Docker setup
    WEAVIATE_API_KEY = None # Set to your Weaviate Cloud API Key if using WCS, otherwise None for local
    WEAVIATE_COLLECTION_NAME = "CodeKnowledge" # Weaviate collection name

    # Neo4j Configuration
    NEO4J_URI = "bolt://localhost:7687" # connection to the Neo4j database
    NEO4J_USER = "neo4j"
    NEO4J_PASSWORD = "your_strong_password" # REPLACE with your actual Neo4j password

    # --- Embedding Model Configuration ---
    # Path to local model or HuggingFace model name
    # Example: "e:/models/codebert-base" or "microsoft/codebert-base"
    EMBEDDING_MODEL_NAME = "microsoft/codebert-base"  # UPDATE this path/name as needed

    # --- Ingestion Batch Sizes ---
    # For efficient processing of embeddings/database insertions
    BATCH_SIZE = ...
    ```

3.  **Update the following values**:
    *   `NEO4J_PASSWORD`: Use the same password you set in the Neo4j Docker command (see Database Setup section)
    *   `EMBEDDING_MODEL_NAME`: Set to your local model path or a HuggingFace model identifier

## Usage

### Running the Workflow

The main entry point for the vulnerability detection and patch generation pipeline is `workflow/workflow.py`.

1.  Ensure your virtual environment is activated.
2.  Ensure Docker containers for Neo4j and Weaviate are running.
3.  Run the workflow script:

```bash
python workflow/workflow.py
```

This script will:
1.  Load the dataset (configured in `workflow.py`).
2.  Process the target repositories.
3.  Query the knowledge base.
4.  Generate patches using the configured LLM provider.
5.  Save results to `llm_response/`.

## Project Structure

```
Graphix_/
├── data/               # Database storage (Neo4j, Weaviate)
├── dataset/            # Input datasets (e.g., SWE-bench)
├── knowledge_base/     # Core logic for code parsing and DB management
├── llm_response/       # Generated patches and results
├── patch_generation/   # Modules for LLM interaction and patch creation
├── query_kb/           # Logic for querying the knowledge base
├── repos/              # Cloned target repositories
├── workflow/           # Main execution scripts
├── docker-compose.yml  # Weaviate Docker configuration
├── requirements.txt    # Python dependencies
└── README.md           # Project documentation
```

## Troubleshooting

*   **Docker Issues**: If databases fail to start, ensure Docker Desktop is running and you have sufficient system resources.
*   **Neo4j Connection**: Verify the password in your `.env` file matches the one used in the `docker run` command.
*   **Weaviate Issues**: If you need to reset Weaviate, run `docker-compose down`, delete the `data/weaviate_data` directory, and run `docker-compose up -d` again.
