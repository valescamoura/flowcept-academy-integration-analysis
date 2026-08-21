import os
from pprint import pprint

from flowcept import Flowcept
from flowcept.configs import LMDB_ENABLED, LMDB_SETTINGS, MONGO_DB, MONGO_ENABLED, SETTINGS_PATH


def main() -> None:
    campaign_id = os.environ.get("FLOWCEPT_CAMPAIGN_ID", "academy-openinference-fibonacci")
    print("settings:", SETTINGS_PATH)
    print("mongo enabled:", MONGO_ENABLED, "db:", MONGO_DB)
    print("lmdb enabled:", LMDB_ENABLED, "settings:", LMDB_SETTINGS)
    print("campaign_id:", campaign_id)

    workflows = Flowcept.db.query({"campaign_id": campaign_id}, collection="workflows")
    tasks = Flowcept.db.query({"campaign_id": campaign_id}, collection="tasks")

    print(f"\nworkflows found: {len(workflows)}")
    for workflow in workflows:
        print("\nWORKFLOW")
        pprint(workflow)

    print(f"\ntasks found: {len(tasks)}")
    for task in tasks:
        print("\nTASK")
        pprint(
            {
                "task_id": task.get("task_id"),
                "workflow_id": task.get("workflow_id"),
                "activity_id": task.get("activity_id"),
                "subtype": task.get("subtype"),
                "agent_id": task.get("agent_id"),
                "agent_name": task.get("agent_name"),
                "source_agent_id": task.get("source_agent_id"),
                "source_agent_name": task.get("source_agent_name"),
                "telemetry_at_start": task.get("telemetry_at_start"),
                "telemetry_at_end": task.get("telemetry_at_end"),
                "custom_metadata_keys": sorted((task.get("custom_metadata") or {}).keys()),
            }
        )


if __name__ == "__main__":
    main()
