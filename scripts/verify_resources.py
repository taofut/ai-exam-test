"""Validate only the bundled public resources; never connect to or reset a database."""
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator, ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app/backend/src"))

from materialops.seed import default_dataset, validate_dataset


def validate_knowledge(knowledge, dataset):
    schema = json.loads((ROOT / "resources/schemas/knowledge-baseline.schema.json").read_text(encoding="utf-8"))
    try:
        Draft202012Validator(schema).validate(knowledge)
    except ValidationError as exc:
        raise ValueError(f"只读知识结构错误：{exc.message}") from exc
    dept_ids = {row["id"] for row in dataset["depts"]}
    item_nos = {row["itemNo"] for row in dataset["items"]}
    seen = set()
    for doc in knowledge["documents"]:
        identifier = doc["docId"]
        if identifier in seen:
            raise ValueError(f"知识 docId 重复：{identifier}")
        seen.add(identifier)
        if not doc["title"].strip() or not doc["content"].strip():
            raise ValueError(f"知识 {identifier} 的标题或正文为空白。")
        if doc["deptId"] is not None and doc["deptId"] not in dept_ids:
            raise ValueError(f"知识 {identifier} 引用了不存在的部门。")
        if not set(doc["itemNos"]) <= item_nos:
            raise ValueError(f"知识 {identifier} 引用了不存在的物资编号。")


def main():
    for name, dataset in (
        ("default", default_dataset()),
        ("sample", json.loads((ROOT / "resources/demo/seed-data.json").read_text(encoding="utf-8"))),
    ):
        validate_dataset(dataset)
        print(f"[ok] {name}: {len(dataset['inventories'])} inventories")
    path = ROOT / "resources/demo/knowledge-baseline.json"
    knowledge = json.loads(path.read_text(encoding="utf-8"))
    validate_knowledge(knowledge, default_dataset())
    print(f"[ok] {path.relative_to(ROOT).as_posix()}: {len(knowledge['documents'])} documents")
    print("Public resource validation passed; no network requests or database writes.")


if __name__ == "__main__":
    main()
