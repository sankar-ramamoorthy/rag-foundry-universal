# ingestion_service/src/ui/gradio_app.py
import os
import json
import requests
import gradio as gr  # type: ignore


# Base URLs for services (Docker-friendly)
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8001")
RAG_API_BASE_URL = os.getenv("RAG_API_BASE_URL", "http://localhost:8004")

# ----------------------------
# Ingestion functions (unchanged)
# ----------------------------
def submit_ingest(source_type: str, file_obj):
    """Submit an ingestion request to the API."""
    try:
        if source_type == "file":
            if file_obj is None:
                return "No file selected."
            metadata = json.dumps({"filename": os.path.basename(file_obj.name)})
            with open(file_obj.name, "rb") as f:
                response = requests.post(
                    f"{API_BASE_URL}/v1/ingest/file",
                    files={"file": f},
                    data={"metadata": metadata},
                    timeout=500,
                )
        else:
            response = requests.post(
                f"{API_BASE_URL}/v1/ingest",
                json={"source_type": source_type, "metadata": {}},
                timeout=120,
            )

        if response.status_code != 202:
            return f"Error submitting ingestion: {response.text}"

        data = response.json()
        return f"Ingestion accepted.\nID: {data['ingestion_id']}\nStatus: {data.get('status', '-')}"
    except Exception as exc:
        return f"Error submitting ingestion: {exc}"

def check_status(ingestion_id: str):
    """Check the status of an ingestion request."""
    try:
        if not ingestion_id:
            return "Please enter an ingestion ID."

        response = requests.get(
            f"{API_BASE_URL}/v1/ingest/{ingestion_id}",
            timeout=10,
        )

        if response.status_code == 200:
            data = response.json()
            status = data.get("status", "-")
            return f"Status: {status}"

        # Any non-200 → show error cleanly
        try:
            error = response.json()
            message = error.get("message", "Unknown error")
        except Exception:
            message = response.text

        return f"Error checking status: {message}"

    except Exception as exc:
        return f"Error checking status: {exc}"

# ----------------------------
# Codebase Ingestion Functions (unchanged)
# ----------------------------
def submit_codebase_ingest(source_type: str, git_url: str, local_path: str, provider: str):
    """Submit codebase ingestion request."""
    print(f"🔍 Gradio calling: {API_BASE_URL}/v1/ingest-repo")
    try:
        if source_type == "git":
            if not git_url.strip():
                return "Please enter a Git URL."
            response = requests.post(
                f"{API_BASE_URL}/v1/ingest-repo",
                data={"git_url": git_url, "provider": provider or ""},
                timeout=300,
            )
        elif source_type == "local":
            if not local_path.strip():
                return "Please enter a local path."
            response = requests.post(
                f"{API_BASE_URL}/v1/ingest-repo",
                data={"local_path": local_path, "provider": provider or ""},
                timeout=300,
            )
        else:
            return "Please select 'Git URL' or 'Local Path'."

        if response.status_code != 202:
            return f"Error: {response.text}"

        data = response.json()
        return f"✅ **Ingestion Started**\nID: `{data['ingestion_id']}`\nStatus: {data['status']}\n\n*Check status below*"
    
    except Exception as exc:
        return f"❌ Error: {exc}"

def check_codebase_status(ingestion_id: str):
    """Check codebase ingestion status."""
    try:
        if not ingestion_id.strip():
            return "Please enter an Ingestion ID."
        
        response = requests.get(
            f"{API_BASE_URL}/v1/ingest-repo/{ingestion_id}",
            timeout=10,
        )
        
        if response.status_code == 200:
            data = response.json()
            return f"**Status**: {data['status']}"
        else:
            return f"❌ Error: {response.text}"
    
    except Exception as exc:
        return f"❌ Error: {exc}"

# ----------------------------
# REPO-AWARE RAG FUNCTIONS (NEW)
# ----------------------------
def refresh_repos():
    """Fetch repos from ingestion_service API."""
    try:
        response = requests.get(f"{API_BASE_URL}/v1/repos", timeout=10)
        response.raise_for_status()
        repos = response.json()
        
        choices = [
            (repo["display_name"], repo["id"]) 
            for repo in repos 
            if repo["status"] == "completed"
        ]
        
        if choices:
            value = choices[0][1]  # Auto-select first complete repo
            #return gr.update(choices=choices, value=value)
            return gr.Dropdown(choices=choices, value=value)
        
        else:
            gr.Warning("No complete repositories found. Ingest a codebase first.")
            #return gr.update(choices=[], value=None)
            return gr.Dropdown(choices=[], value=None)
    except Exception as e:
        gr.Error(f"Failed to fetch repos: {e}")
        #return gr.update(choices=[], value=None)
        return gr.Dropdown(choices=[], value=None)

def submit_rag_query(query: str, repo_id: str | None, top_k: int, provider: str | None, model: str | None):
    """Submit RAG query with repo_id."""
    try:
        if not query.strip():
            return "Please enter a query."
        
        if not repo_id:
            return "❌ Please select a repository (click Refresh Repos first)."
        
        payload = {
            "query": query,
            "repo_id": repo_id,
            "top_k": top_k,
        }
        
        if provider:
            payload["provider"] = provider
        if model:
            payload["model"] = model
        
        response = requests.post(
            f"{RAG_API_BASE_URL}/v1/rag",
            json=payload,
            timeout=300,
        )
        response.raise_for_status()
        data = response.json()
        
        answer = data.get("answer", "")
        sources = data.get("sources", [])
        formatted_sources = "\n".join(f"• {s}" for s in sources)
        
        return f"""🎯 **Repository:** {repo_id[:8]}...
        
**Answer:**
{answer}

**Sources:**
{formatted_sources if formatted_sources else 'None found.'}"""
    
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return "❌ Repository not found. Refresh repos and select a complete repository."
        try:
            return f"❌ RAG Error: {e.response.json().get('detail', e.response.text)}"
        except:
            return f"❌ RAG Error: {e.response.text}"
    except Exception as exc:
        return f"❌ Error querying RAG: {exc}"

def submit_simple_rag_query(query: str, top_k: int, provider: str | None, model: str | None):
    """Submit a simple (non-graph) RAG query for regular documents."""
    try:
        if not query.strip():
            return "Please enter a query."
        payload = {"query": query, "top_k": top_k}
        if provider:
            payload["provider"] = provider
        if model:
            payload["model"] = model

        response = requests.post(
            f"{RAG_API_BASE_URL}/v1/rag/simple",
            json=payload,
            timeout=300,
        )
        response.raise_for_status()
        data = response.json()
        answer = data.get("answer", "")
        sources = data.get("sources", [])
        formatted_sources = "\n".join(f"• {s}" for s in sources)
        return f"**Answer:**\n{answer}\n\n**Sources:**\n{formatted_sources or 'None found.'}"

    except Exception as exc:
        return f"❌ Error: {exc}"
    
# ----------------------------
# Build Gradio UI (COMPLETE)
# ----------------------------
def build_ui():
    """Build the Gradio UI with ingestion + REPO-AWARE RAG."""
    with gr.Blocks(title="Agentic RAG - Graph Aware", theme=gr.themes.Soft()) as demo:  # type: ignore
        gr.Markdown("# 🚀 Agentic RAG - Graph-Aware Codebase Intelligence")
        gr.Markdown("*Vector search + Graph traversal for code & documents*")

        # ----------------------------
        # 1. DOCUMENT INGESTION
        # ----------------------------
        gr.Markdown("## 📄 Document Ingestion")
        with gr.Row():  # type: ignore
            source_type = gr.Dropdown(  # type: ignore
                choices=["file", "bytes", "uri"],
                value="file",
                label="Source Type",
            )
            file_input = gr.File(label="Upload File")  # type: ignore
            submit_btn = gr.Button("📤 Submit Ingestion", variant="secondary")  # type: ignore

        submission_output = gr.Textbox(label="Submission Result", lines=2)  # type: ignore

        submit_btn.click(
            fn=submit_ingest,
            inputs=[source_type, file_input],
            outputs=submission_output,
        )

        gr.Markdown("## 🔍 Check Status")
        ingestion_id_input = gr.Textbox(label="Ingestion ID")  # type: ignore
        status_btn = gr.Button("Check Status", variant="secondary")  # type: ignore
        status_output = gr.Textbox(label="Status")  # type: ignore

        status_btn.click(
            fn=check_status,
            inputs=ingestion_id_input,
            outputs=status_output,
        )

        # ----------------------------
        # 2. CODEBASE INGESTION
        # ----------------------------
        gr.Markdown("## 💻 Codebase Ingestion")
        with gr.Row():  # type: ignore
            codebase_source_type = gr.Dropdown(  # type: ignore
                choices=["git", "local"],
                value="git",
                label="Source Type",
            )
            git_url_input = gr.Textbox(  # type: ignore
                label="Git URL", 
                placeholder="https://github.com/sankar-ramamoorthy/rag-foundry-coderag.git"
            )
            local_path_input = gr.Textbox(  # type: ignore
                label="Local Path", 
                placeholder="/path/to/project"
            )
            provider_input = gr.Textbox(  # type: ignore
                label="Embedding Provider", 
                placeholder="ollama"
            )
            codebase_submit_btn = gr.Button("💾 Ingest Codebase", variant="secondary")  # type: ignore

        codebase_submission_output = gr.Textbox(label="Codebase Submission Result", lines=2)  # type: ignore

        codebase_submit_btn.click(
            fn=submit_codebase_ingest,
            inputs=[codebase_source_type, git_url_input, local_path_input, provider_input],
            outputs=codebase_submission_output,
        )

        gr.Markdown("## 💾 Check Codebase Status")
        codebase_ingestion_id_input = gr.Textbox(label="Codebase Ingestion ID")  # type: ignore
        codebase_status_btn = gr.Button("Check Status", variant="secondary")  # type: ignore
        codebase_status_output = gr.Textbox(label="Codebase Status")  # type: ignore

        codebase_status_btn.click(
            fn=check_codebase_status,
            inputs=codebase_ingestion_id_input,
            outputs=codebase_status_output,
        )

        # ----------------------------
        # 3. REPO-AWARE RAG (NEW SECTION)
        # ----------------------------
        gr.Markdown("## 🎯 Graph-Aware RAG Query")
        gr.Markdown("*Ask about code structure: 'methods in math_utils.py', 'what calls add()', etc.*")
        
        with gr.Row():  # type: ignore
            repo_dropdown = gr.Dropdown(
                choices=[], 
                label="📂 Repository",
                value=None,
                info="Graph traversal only works on complete repos"
            )
            refresh_repos_btn = gr.Button("🔄 Refresh Repos", variant="stop")  # type: ignore

        rag_query = gr.Textbox(  # type: ignore
            label="❓ Question",
            placeholder="e.g. 'methods in math_utils.py', 'what calls add()', or general questions...",
            lines=3,
        )

        with gr.Row():  # type: ignore
            top_k = gr.Number(  # type: ignore
                label="📊 Top K Chunks",
                value=5,
                precision=0,
                minimum=1,
                maximum=50
            )
            provider = gr.Textbox(  # type: ignore
                label="🤖 LLM Provider",
                placeholder="ollama",
                scale=2
            )
            model = gr.Textbox(  # type: ignore
                label="🧠 Model", 
                placeholder="Qwen3:1.7b",
                scale=2
            )

        rag_btn = gr.Button("🚀 Ask Graph RAG", variant="primary", size="lg")  # type: ignore
        rag_output = gr.Textbox(  # type: ignore
            label="🧠 Graph-Aware Response",
            lines=15,
            max_lines=20
        )
        # In build_ui(), add a new section after the existing repo RAG section:

        gr.Markdown("## 📄 Document Query (Non-Repo)")
        gr.Markdown("*Query regular documents: PDFs, text files, etc.*")

        doc_query = gr.Textbox(
            label="❓ Question",
            placeholder="Ask about your uploaded documents...",
            lines=3,
        )

        with gr.Row():
            doc_top_k = gr.Number(label="📊 Top K", value=5, precision=0, minimum=1, maximum=50)
            doc_provider = gr.Textbox(label="🤖 LLM Provider", placeholder="ollama")
            doc_model = gr.Textbox(label="🧠 Model", placeholder="Qwen3:1.7b")

        doc_btn = gr.Button("🔍 Ask Document RAG", variant="secondary", size="lg")
        doc_output = gr.Textbox(label="📄 Response", lines=15, max_lines=20)

        doc_btn.click(
            fn=submit_simple_rag_query,
            inputs=[doc_query, doc_top_k, doc_provider, doc_model],
            outputs=doc_output,
        )

        # ----------------------------
        # Event Handlers
        # ----------------------------
        refresh_repos_btn.click(
            fn=refresh_repos,
            outputs=repo_dropdown,
        )

        rag_btn.click(
            fn=submit_rag_query,
            inputs=[rag_query, repo_dropdown, top_k, provider, model],
            outputs=rag_output,
        )

        # Auto-refresh repos when UI loads
        demo.load(refresh_repos, outputs=repo_dropdown)

    return demo

# ----------------------------
# Launch the app
# ----------------------------
if __name__ == "__main__":
    ui = build_ui()
    ui.launch(server_port=7860, server_name="0.0.0.0", share=False, show_error=True)
