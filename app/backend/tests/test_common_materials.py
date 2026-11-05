import json

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from materialops.config import BACKEND_ROOT, RESOURCES_ROOT, Settings
from materialops.database import Database
from materialops.main import create_app


def common_dataset():
    dataset = json.loads((RESOURCES_ROOT / "demo" / "seed-data.json").read_text(encoding="utf-8"))
    for entity in ("warehouses", "items"):
        for row in dataset[entity]:
            row.pop("industry", None)
    return dataset


def test_shared_part_can_be_stocked_by_warehouses_in_different_departments(tmp_path):
    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'common.db'}"))
    dataset = common_dataset()
    dataset["inventories"].append({"id": 50001, "warehouseId": 201, "itemId": 1001, "onHand": 4, "version": 0})
    with TestClient(app) as client:
        response = client.post("/api/dev/reset", json={"dataset": dataset})
        assert response.status_code == 200, response.text
        rows = client.get("/api/inventories?itemId=1001", headers={"X-User": "SYS-001"}).json()["items"]
        assert {row["warehouseId"] for row in rows} == {101, 102, 201}
        assert {row["onHand"] for row in rows} == {4, 8, 12}
        for endpoint in ("warehouses", "items"):
            entries = client.get(f"/api/{endpoint}", headers={"X-User": "SYS-001"}).json()["items"]
            assert entries and all("industry" not in row for row in entries)
        with app.state.database.engine.connect() as connection:
            assert connection.execute(text("PRAGMA foreign_key_check")).fetchall() == []


def test_existing_database_upgrade_removes_only_classification_columns(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'existing.db'}")
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    with database.engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0001_baseline")
    with database.engine.begin() as connection:
        connection.execute(text("INSERT INTO t_dept (id,name) VALUES (1,'自定义设备维护部')"))
        connection.execute(text("INSERT INTO t_warehouse (id,name,dept_id,industry) VALUES (1,'自定义中心仓',1,'LEGACY')"))
        connection.execute(text("INSERT INTO t_item (id,item_no,name,unit,reorder_point,target_stock,industry) VALUES (1,'PART-1','自定义电源','个',2,10,'LEGACY')"))
        connection.execute(text("INSERT INTO t_inventory (id,warehouse_id,item_id,on_hand,version) VALUES (1,1,1,7,3)"))
    database.migrate()
    with database.engine.connect() as connection:
        inspector = inspect(connection)
        for table in ("t_warehouse", "t_item"):
            assert "industry" not in {column["name"] for column in inspector.get_columns(table)}
        assert connection.execute(text("SELECT on_hand,version FROM t_inventory WHERE id=1")).one() == (7, 3)
        assert connection.execute(text("SELECT name FROM t_warehouse WHERE id=1")).scalar() == "自定义中心仓"
        assert connection.execute(text("SELECT name FROM t_item WHERE id=1")).scalar() == "自定义电源"
        assert connection.execute(text("PRAGMA foreign_key_check")).fetchall() == []
    database.engine.dispose()
