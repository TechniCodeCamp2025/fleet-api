"""
Fleet Optimization API Server
Main entry point - launches FastAPI server
"""
import sys
import os
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Load environment variables from .notenv file (do this FIRST!)
try:
    from dotenv import load_dotenv
    # Try .notenv first, then fall back to .env
    if not load_dotenv('.notenv', override=True):
        load_dotenv('.env', override=True)
except ImportError:
    pass  # python-dotenv not required, will use system env vars

console = Console()


def check_dependencies():
    """Check if web dependencies are installed"""
    try:
        import fastapi
        import uvicorn
        import pydantic
        return True
    except ImportError as e:
        console.print("[bold red]Missing dependencies![/bold red]")
        console.print(f"[red]Error: {e}[/red]")
        console.print("\n[bold cyan]Install web dependencies with:[/bold cyan]")
        console.print("  [green]pip install fastapi uvicorn pydantic python-multipart[/green]")
        console.print("\n  [yellow]Or using the project extras:[/yellow]")
        console.print("  [green]pip install .[web][/green]")
        return False


def main():
    """Main entry point - launch FastAPI server"""
    console.print(Panel.fit(
        "[bold cyan]PREDICTIVE FLEET SWAP AI - LSP GROUP[/bold cyan]\n"
        "[white]FastAPI Server[/white]",
        border_style="cyan"
    ))
    
    # Check dependencies
    if not check_dependencies():
        return 1
    
    # Import after dependency check
    import uvicorn
    
    # Get host and port from environment or use defaults
    host = os.getenv('API_HOST', '0.0.0.0')
    port = int(os.getenv('API_PORT', '8000'))
    reload = os.getenv('API_RELOAD', 'true').lower() == 'true'
    
    # Create info table
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="white")
    
    table.add_row("Host", host)
    table.add_row("Port", str(port))
    table.add_row("Reload", "enabled" if reload else "disabled")
    
    console.print("\n[bold green]Starting FastAPI server...[/bold green]")
    console.print(table)
    
    console.print("\n[bold magenta]Interactive API docs:[/bold magenta]")
    console.print(f"  [link]http://localhost:{port}/docs[/link] (Swagger UI)")
    console.print(f"  [link]http://localhost:{port}/redoc[/link] (ReDoc)")
    
    console.print("\n[bold yellow]Test interface:[/bold yellow]")
    console.print("  Open [cyan]upload_test.html[/cyan] in your browser")
    
    console.print("\n[bold blue]To run optimization algorithm instead:[/bold blue]")
    console.print("  [green]python src/run_optimizer.py [full|test|quick][/green]\n")
    
    try:
        # Launch server - use import string for reload to work
        uvicorn.run(
            "src.endpoints:app",
            host=host,
            port=port,
            reload=reload,
            log_level="info"
        )
    except KeyboardInterrupt:
        console.print("\n\n[yellow]Server stopped by user[/yellow]")
        return 0
    except Exception as e:
        console.print(f"\n[bold red]Error starting server: {e}[/bold red]")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

