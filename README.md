
cat > README.md <<'EOF'
# TrustLens AI

### Evidence Intelligence Workspace

TrustLens AI is an AI-powered document intelligence and due-diligence workspace designed to help users process documents, retrieve evidence, identify compliance gaps, compare document versions, and maintain traceable human review decisions.

## Core Features

### 1. Document AI
- Document upload and processing.
- OCR and structured data extraction.
- Document indexing for downstream analysis.
- Extraction and validation workflow.

### 2. Ask TrustLens AI
- Conversational document intelligence.
- Questions across indexed documents.
- Evidence-backed answers.
- Document context and intelligence insights.

### 3. Review Dashboard
- Indexed document and page statistics.
- Pending review monitoring.
- Compliance exception tracking.
- Extraction confidence indicators.
- Offline review snapshots.
- Due-diligence PDF report generation.

### 4. Verification & Compliance
- Document completeness checklists.
- Missing evidence detection.
- Custom validation rules.
- Document version comparison.
- Added, removed and modified content detection.
- Human review actions: Accept, Reject, Correct and Further Review.
- Reviewer comments and decision history.

### 5. Audit Trail
- Chronological activity history.
- Document upload and processing events.
- Extraction and validation events.
- Human verification decisions.

## Technology Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 14, React, TypeScript |
| Styling | Tailwind CSS |
| UI Animation | Framer Motion |
| Icons | Lucide React |
| Backend | Python, FastAPI |
| Database | MongoDB |
| Deployment / Local Services | Docker Compose |
| API Documentation | OpenAPI / Swagger |

## Application Architecture

\`\`\`text
                 TRUSTLENS AI
                       |
          +------------+------------+
          |                         |
       FRONTEND                  BACKEND
     Next.js / React             FastAPI
          |                         |
          |              +----------+----------+
          |              |          |          |
          |           Document   Compliance   AI / RAG
          |           Pipeline    Engine      Services
          |              |          |          |
          +--------------+----------+----------+
                                 |
                              MongoDB
                                 |
                       Evidence & Audit Data
\`\`\`

## Document Workflow

\`\`\`text
Document Upload
      |
      v
OCR Processing
      |
      v
Structured Extraction
      |
      v
Validation & Indexing
      |
      v
AI Question Answering
      |
      v
Compliance Checks
      |
      v
Human Verification
      |
      v
Reports & Audit Trail
\`\`\`

## Run Locally

### Prerequisites
- Git
- Docker Desktop
- Docker Compose

### Clone the repository

\`\`\`bash
git clone https://github.com/nikhilkumar200408/Bhoomi_setu.git
cd Bhoomi_setu
\`\`\`

### Start the application

\`\`\`bash
docker compose up --build
\`\`\`

### Application URLs

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| Swagger API Docs | http://localhost:8000/docs |
| MongoDB | localhost:27017 |

### Useful Docker Commands

\`\`\`bash
docker compose ps
docker compose logs -f
docker compose down
docker compose build --no-cache frontend
\`\`\`

## Main Routes

| Module | Route |
|---|---|
| Document AI | `/document-ai` |
| Ask TrustLens AI | `/chat` |
| Verification & Compliance | `/compliance` |
| Review Dashboard | `/review-dashboard` |
| Audit Trail | `/audit` |

## Repository Structure

\`\`\`text
Bhoomi_setu/
├── frontend/
│   └── app/
│       └── (app)/
│           ├── chat/
│           ├── compliance/
│           ├── dashboard/
│           ├── document-ai/
│           ├── review-dashboard/
│           └── audit/
├── backend/
├── docker-compose.yml
└── README.md
\`\`\`

## Important Notes

- AI-generated findings should be checked against the original source documents.
- Extraction confidence is not proof of legal correctness.
- Human verification remains an important part of the review process.
- Never commit API keys, passwords, private documents, or production secrets.
- Configure environment variables according to the backend and Docker configuration.

## Responsible Use

TrustLens AI is a document intelligence and decision-support system. It assists with document analysis, evidence discovery, and compliance review; it does not replace professional legal advice or authorized human approval.

---

**TrustLens AI — From Documents to Evidence. From Evidence to Decisions.**
EOF
