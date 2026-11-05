"""Migration and fixture entry point used by the repository exam commands."""
import argparse
import json

from materialops.config import settings
from materialops.database import Database
from materialops.errors import AppError
from materialops.models import ExamClock
from materialops.seed import default_dataset, reset_dataset


def main():
    parser = argparse.ArgumentParser(description="MaterialOps independent examination database")
    parser.add_argument("command", choices=["migrate", "seed", "reset"])
    parser.add_argument("--dataset", help="Optional public dataset JSON file")
    args = parser.parse_args()
    database = Database(settings.database_url)
    try:
        database.migrate()
        if args.command != "migrate":
            if args.command == "seed":
                with database.sessions() as session:
                    if session.get(ExamClock, 1) is not None:
                        print(json.dumps({"status": "ok", "seeded": False, "message": "考试库已初始化，保留现有数据。"}, ensure_ascii=False))
                        return
            if not settings.allow_exam_reset:
                raise AppError("NO_PERMISSION", "在独立考试库配置 ALLOW_EXAM_RESET=true 后才能加载或重置。")
            if args.dataset:
                with open(args.dataset, encoding="utf-8") as file:
                    dataset = json.load(file)
            else:
                dataset = default_dataset()
            result = reset_dataset(database, dataset)
            print(json.dumps(result, ensure_ascii=False))
    except AppError as exc:
        parser.exit(1, f"{exc.code}: {exc.message}\n")
    finally:
        database.engine.dispose()


if __name__ == "__main__":
    main()
