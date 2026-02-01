"""Main entry point for Skuper Intelligence"""

import logging
import sys

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src import StockoutOrchestrator

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Disable httpx logging to reduce noise
logging.getLogger("httpx").setLevel(logging.WARNING)

# Create rich console
console = Console()


def main():
    """
    Run the Emergency Stockout Resolver system
    """
    try:
        criticality_filter = None
        if len(sys.argv) > 1:
            criticality_filter = sys.argv[1]

        # Display header
        console.print()
        title = Text("SKUPER INTELLIGENCE", style="bold cyan")
        subtitle = Text("Agentic Inventory Rebalancing System", style="italic")
        agent_type = Text(
            "Emergency Stockout Resolver (Type A Agent)", style="bold yellow"
        )

        header_text = Text.assemble(title, "\n", subtitle, "\n", agent_type)

        console.print(Panel(header_text, box=box.DOUBLE, padding=(1, 2), style="cyan"))
        console.print()

        if criticality_filter:
            console.print(
                f"[yellow]Filtering for:[/yellow] [bold]{criticality_filter}[/bold] products"
            )
            console.print()

        # Create and run orchestrator
        orchestrator = StockoutOrchestrator()
        results = orchestrator.run(criticality_filter=criticality_filter)

        # Display results header
        console.print()
        console.print(
            Panel.fit("[bold white]RESULTS[/bold white]", box=box.DOUBLE, style="green")
        )
        console.print()

        transfers = results.get("transfers", [])
        priority_analyses = results.get("priority_analyses", [])

        transfers = results.get("transfers", [])
        priority_analyses = results.get("priority_analyses", [])

        # Display transfer recommendations
        if transfers:
            console.print(
                f"[bold green]✓[/bold green] Generated {len(transfers)} transfer recommendation(s)"
            )
            console.print()

            for idx, rec in enumerate(transfers, 1):
                transfer_table = Table(
                    show_header=False,
                    box=box.ROUNDED,
                    border_style="blue",
                    title=f"[bold cyan]Transfer #{idx}[/bold cyan]",
                    title_style="bold cyan",
                )

                transfer_table.add_column("Field", style="cyan", width=20)
                transfer_table.add_column("Value", style="white")

                transfer_table.add_row("SKU", f"[bold]{rec['sku_id']}[/bold]")
                transfer_table.add_row(
                    "Quantity", f"[yellow]{rec['quantity']} units[/yellow]"
                )
                transfer_table.add_row("From", f"[red]{rec['from_location']}[/red]")
                transfer_table.add_row("To", f"[green]{rec['to_location']}[/green]")
                transfer_table.add_row(
                    "Cost", f"[yellow]${rec['estimated_cost']:.2f}[/yellow]"
                )
                transfer_table.add_row("Reasoning", rec["reasoning"])

                console.print(transfer_table)
                console.print()

        # Display priority analyses
        if priority_analyses:
            console.print(
                f"[bold yellow]⚠[/bold yellow]  Priority Analyses for {len(priority_analyses)} SKU(s) without surplus:"
            )
            console.print()

            for idx, analysis in enumerate(priority_analyses, 1):
                # Determine color based on urgency
                urgency = analysis["urgency_level"]
                if urgency == "CRITICAL":
                    urgency_color = "red"
                    icon = "🔴"
                elif urgency == "HIGH":
                    urgency_color = "orange1"
                    icon = "🟠"
                elif urgency == "MEDIUM":
                    urgency_color = "yellow"
                    icon = "🟡"
                else:
                    urgency_color = "green"
                    icon = "🟢"

                analysis_table = Table(
                    show_header=False,
                    box=box.ROUNDED,
                    border_style=urgency_color,
                    title=f"{icon} [bold]{analysis['sku_id']}[/bold] - [italic]{analysis['product_family']}[/italic]",
                    title_style=f"bold {urgency_color}",
                )

                analysis_table.add_column("Field", style="cyan", width=22)
                analysis_table.add_column("Value", style="white")

                analysis_table.add_row(
                    "Urgency Level",
                    f"[bold {urgency_color}]{urgency}[/bold {urgency_color}]",
                )
                analysis_table.add_row(
                    "Priority Location",
                    f"[yellow]{analysis['highest_priority_location']}[/yellow]",
                )
                analysis_table.add_row(
                    "Recommended Action", analysis["recommended_action"]
                )
                analysis_table.add_row("Summary", analysis["summary"])

                console.print(analysis_table)
                console.print()

        if not transfers and not priority_analyses:
            console.print(
                "[green]✓[/green] No stockouts detected or agent did not generate recommendations."
            )

        console.print()
        console.print("[bold green]" + "=" * 80 + "[/bold green]")
        console.print("[bold green]System execution complete.[/bold green]")
        console.print("[bold green]" + "=" * 80 + "[/bold green]")

    except Exception as e:
        logging.exception("System execution failed")
        console.print()
        console.print(f"[bold red]ERROR:[/bold red] {str(e)}")
        console.print()
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
