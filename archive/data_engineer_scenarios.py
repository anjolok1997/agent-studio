"""
Data Engineer Scenarios
=======================
Pre-built goals for data engineers to run against the multi-agent system.
Each scenario maps to realistic day-to-day data engineering work.

Run:
    python3 data_engineer_scenarios.py

Then pick a scenario number. The agent will assign the right specialists
(data-engineer, data-quality, backend-architect, project-manager) and
validate their outputs through the QA gate.
"""

import os
import sys

# Import the agent runner from multi_agent_v2
from multi_agent_v2 import run_manager, artifacts

SCENARIOS = [
    {
        "name": "Design a new ingestion pipeline",
        "tags": ["pipeline", "ingestion", "airflow"],
        "goal": (
            "Design a batch ingestion pipeline that pulls data from a Postgres transactional "
            "database into a Snowflake data warehouse every hour. "
            "Cover: the Airflow DAG structure with task dependencies, the incremental load "
            "strategy (how to detect new/updated rows), error handling and retry logic, "
            "and the monitoring/alerting setup so we know immediately if a run fails or "
            "data is stale."
        ),
    },
    {
        "name": "Build a dbt project structure for e-commerce",
        "tags": ["dbt", "modeling", "warehouse"],
        "goal": (
            "Design a dbt project structure for an e-commerce company. "
            "We have raw data in BigQuery from three sources: Shopify (orders, customers, products), "
            "Google Ads (campaigns, spend, clicks), and Zendesk (tickets, resolutions). "
            "Define the staging → intermediate → mart layer structure, name the key models in each "
            "layer, write the dbt test definitions (schema.yml) for the most critical fields, "
            "and explain the grain of each mart table."
        ),
    },
    {
        "name": "Debug a failing pipeline",
        "tags": ["debugging", "incident", "runbook"],
        "goal": (
            "Create a debugging runbook for a common data pipeline failure scenario: "
            "our daily Airflow DAG that loads sales data into Redshift ran successfully "
            "(green in the UI) but the downstream dashboard is showing yesterday's numbers. "
            "The pipeline appears healthy but the data is stale. "
            "Produce a step-by-step investigation checklist, the SQL queries to run at each step "
            "to diagnose the issue, a list of the most likely root causes ranked by probability, "
            "and the fix for each cause."
        ),
    },
    {
        "name": "Design a data quality framework",
        "tags": ["data quality", "dbt tests", "great expectations"],
        "goal": (
            "Design a data quality framework for a fintech company's core tables: "
            "transactions, accounts, and users in a Snowflake warehouse. "
            "Define the critical quality dimensions to check (completeness, freshness, "
            "referential integrity, business rule validation), write the actual dbt test "
            "YAML and SQL for the most important checks, specify alert thresholds and "
            "who gets notified when checks fail, and outline a data contract template "
            "that source teams must sign off on."
        ),
    },
    {
        "name": "Plan a data warehouse migration",
        "tags": ["migration", "planning", "redshift", "snowflake"],
        "goal": (
            "Create a migration plan for moving our data warehouse from Redshift to Snowflake. "
            "We have ~200 tables, 50 Airflow DAGs, and 30 dbt models. "
            "Produce: a phased migration plan (which tables/pipelines move in each phase and why), "
            "a risk register with the top 5 risks and mitigation strategies, "
            "the technical steps to validate data parity between Redshift and Snowflake "
            "after each phase, and a rollback strategy if something goes wrong in production."
        ),
    },
    {
        "name": "Design a real-time streaming pipeline",
        "tags": ["streaming", "kafka", "flink", "real-time"],
        "goal": (
            "Design a real-time event streaming pipeline for a ride-sharing app. "
            "Events (ride_started, ride_ended, payment_processed) are published to Kafka. "
            "We need: a running count of active rides updated every 30 seconds, "
            "fraud detection alerts within 5 seconds of a suspicious payment, "
            "and an hourly rollup of revenue by city that lands in BigQuery. "
            "Specify the Kafka topic structure, the stream processing jobs (Flink or Spark Streaming), "
            "the output sinks for each use case, and how we handle late-arriving events."
        ),
    },
    {
        "name": "Set up data observability",
        "tags": ["observability", "monitoring", "lineage"],
        "goal": (
            "Design a data observability setup for a team that currently has zero monitoring "
            "on their pipelines. They use Airflow for orchestration, dbt for transformation, "
            "and Snowflake as the warehouse. "
            "Prioritize and implement: pipeline health monitoring (what metrics to track, "
            "where to send alerts), data freshness checks (how to detect stale tables), "
            "volume anomaly detection (how to catch unexpected drops or spikes in row counts), "
            "and a lightweight lineage tracking approach. "
            "Give concrete implementation steps, not a list of tools to evaluate."
        ),
    },
    {
        "name": "Optimize a slow dbt model",
        "tags": ["performance", "sql", "optimization", "dbt"],
        "goal": (
            "A dbt model that aggregates daily revenue by customer segment is taking 45 minutes "
            "to run in BigQuery. It joins four large tables (orders: 500M rows, "
            "customers: 10M rows, products: 1M rows, segments: 50k rows) and runs every hour. "
            "Produce: a diagnostic checklist to find the bottleneck, the top 5 optimization "
            "strategies with SQL examples for each, how to use incremental materialization "
            "to avoid full table scans, and the BigQuery-specific settings "
            "(partitioning, clustering) that would have the most impact."
        ),
    },
]


def print_menu():
    print("\n" + "=" * 60)
    print("DATA ENGINEER SCENARIOS")
    print("=" * 60)
    for i, s in enumerate(SCENARIOS, 1):
        tags = ", ".join(s["tags"])
        print(f"\n  {i}. {s['name']}")
        print(f"     [{tags}]")
    print("\n  0. Enter a custom goal")
    print("=" * 60)


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: Set ANTHROPIC_API_KEY first.")
        print("  export ANTHROPIC_API_KEY='sk-ant-...'")
        sys.exit(1)

    print_menu()

    choice = input("\nPick a scenario (0-8): ").strip()
    try:
        idx = int(choice)
    except ValueError:
        print("Invalid choice.")
        sys.exit(1)

    if idx == 0:
        goal = input("Enter your custom goal:\n> ").strip()
    elif 1 <= idx <= len(SCENARIOS):
        scenario = SCENARIOS[idx - 1]
        print(f"\nRunning: {scenario['name']}")
        goal = scenario["goal"]
    else:
        print("Invalid choice.")
        sys.exit(1)

    summary = run_manager(goal)

    print("\n" + "=" * 60)
    print("FINAL SUMMARY")
    print("=" * 60)
    print(summary)

    if artifacts:
        print(f"\n{'='*60}")
        print(f"ARTIFACTS ({len(artifacts)} produced)")
        print("=" * 60)
        for i, a in enumerate(artifacts, 1):
            print(f"\n--- [{i}] From {a['agent']} ---")
            print(a["content"])


if __name__ == "__main__":
    main()
