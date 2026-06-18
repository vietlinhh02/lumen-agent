# Architecture Diagrams

## System Components & Data Flow

This diagram illustrates the high-level architecture of Lumen, showcasing the interaction between the frontend, backend, database, and AI providers.

```mermaid
graph TD
    %% Frontend Components
    subgraph Frontend [Frontend - Next.js]
        UI[User Interface]
        Auth_UI[Auth Pages]
        Dash_UI[Dashboard & Projects]
        Search_UI[Search & Paper List]
        Graph_UI[Knowledge Map]
    end

    %% Backend Components
    subgraph Backend [Backend - FastAPI]
        API[API Router]
        Auth_SVC[Auth Service]
        Search_SVC[Search & AI Screening Service]
        Doc_SVC[PDF Extraction Service]
        Graph_SVC[LangGraph Workflow]
    end

    %% External Systems
    subgraph External [External Services]
        LLM[AI Providers: OpenAI, Anthropic, DeepSeek]
        Arxiv[arXiv API / Semantic Scholar]
    end

    %% Database
    subgraph DB [Database]
        Postgres[(PostgreSQL + pgvector)]
    end

    %% Data Flow
    UI -->|HTTP Requests| API
    Auth_UI --> API
    Dash_UI --> API
    Search_UI --> API
    Graph_UI --> API

    API --> Auth_SVC
    API --> Search_SVC
    API --> Doc_SVC
    API --> Graph_SVC

    Auth_SVC --> Postgres
    Search_SVC --> Postgres
    Doc_SVC --> Postgres
    Graph_SVC --> Postgres

    Search_SVC -->|Fetch Papers| Arxiv
    Search_SVC -->|AI Suggestions| LLM
    Doc_SVC -->|Text Chunking| Postgres
    Graph_SVC -->|Workflow States| LLM
```

## Detailed Data Flow: Paper Search & Save

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant API
    participant SearchService
    participant LLM
    participant ExternalAPI
    participant DB

    User->>Frontend: Enter query
    Frontend->>API: POST /api/search
    API->>SearchService: Suggest query refinements
    SearchService->>LLM: Generate refined queries
    LLM-->>SearchService: Return suggestions
    SearchService->>ExternalAPI: Fetch papers (e.g. arXiv)
    ExternalAPI-->>SearchService: Return paper metadata
    SearchService->>LLM: AI Screening (relevance scoring)
    LLM-->>SearchService: Return scores
    SearchService-->>API: Search Results
    API-->>Frontend: Display papers
    User->>Frontend: Click "Save Paper"
    Frontend->>API: POST /api/projects/{id}/papers
    API->>DB: Save paper & vector embeddings
    DB-->>API: Success
    API-->>Frontend: Paper Saved Status
```
