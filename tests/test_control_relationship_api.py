import json
import os
import socket
import subprocess
import time
import unittest
from pathlib import Path
from urllib import error, request


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON_PATH = PROJECT_ROOT / "venv" / "Scripts" / "python.exe"
DATABASE_PATH = PROJECT_ROOT / "test.db"


class ControlRelationshipApiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = cls.get_free_port()
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        if DATABASE_PATH.exists():
            try:
                DATABASE_PATH.unlink()
            except PermissionError:
                pass

        cls.server_process = subprocess.Popen(
            [
                str(PYTHON_PATH),
                "-m",
                "uvicorn",
                "backend.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(cls.port),
            ],
            cwd=PROJECT_ROOT,
            env={
                **os.environ,
                "DATABASE_URL": f"sqlite:///{DATABASE_PATH}",
                "PYTHONPATH": str(PROJECT_ROOT),
            },
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        cls._wait_for_server()

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "server_process", None) is not None:
            cls.server_process.terminate()
            try:
                cls.server_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                cls.server_process.kill()

        if DATABASE_PATH.exists():
            try:
                DATABASE_PATH.unlink()
            except PermissionError:
                pass

    @staticmethod
    def get_free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return sock.getsockname()[1]

    @classmethod
    def _wait_for_server(cls):
        for _ in range(40):
            if cls.server_process.poll() is not None:
                output = cls.server_process.stdout.read()
                raise RuntimeError(f"测试服务器启动失败。\n{output}")

            try:
                response = request.urlopen(f"{cls.base_url}/", timeout=1)
                if response.status == 200:
                    return
            except Exception:
                time.sleep(0.5)

        output = cls.server_process.stdout.read()
        raise RuntimeError(f"测试服务器启动超时。\n{output}")

    def request_json(self, method: str, path: str, payload: dict | None = None):
        data = None
        headers = {}

        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = request.Request(
            url=f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )

        try:
            with request.urlopen(req, timeout=5) as response:
                body = response.read().decode("utf-8")
                return response.status, json.loads(body) if body else None
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8")
            return exc.code, json.loads(body) if body else None

    def test_control_relationship_crud_flow(self):
        company_payload = {
            "name": "Alibaba",
            "stock_code": "BABA",
            "incorporation_country": "Cayman Islands",
            "listing_country": "United States",
            "headquarters": "Hangzhou",
            "description": "电商企业",
        }
        status_code, company_data = self.request_json(
            "POST",
            "/companies",
            company_payload,
        )
        self.assertEqual(status_code, 201)

        controller_entity_payload = {
            "entity_name": "Jack Ma",
            "entity_type": "person",
            "country": "China",
            "company_id": None,
            "identifier_code": None,
            "is_listed": None,
            "notes": "控制人主体",
        }
        status_code, controller_entity = self.request_json(
            "POST",
            "/shareholders/entities",
            controller_entity_payload,
        )
        self.assertEqual(status_code, 201)

        control_payload = {
            "company_id": company_data["id"],
            "controller_entity_id": controller_entity["id"],
            "controller_name": "Jack Ma",
            "controller_type": "person",
            "control_type": "direct",
            "control_ratio": "12.5000",
            "control_path": "Jack Ma -> Alibaba",
            "is_actual_controller": True,
            "basis": "根据公开披露信息记录",
            "notes": "初始控制关系",
        }
        status_code, created_record = self.request_json(
            "POST",
            "/control-relationships",
            control_payload,
        )
        self.assertEqual(status_code, 201)
        self.assertEqual(created_record["company_id"], company_data["id"])
        self.assertEqual(created_record["controller_entity_id"], controller_entity["id"])
        self.assertEqual(created_record["controller_name"], "Jack Ma")

        record_id = created_record["id"]

        status_code, detail_record = self.request_json(
            "GET",
            f"/control-relationships/{record_id}",
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(detail_record["control_type"], "direct")
        self.assertEqual(detail_record["controller_entity_id"], controller_entity["id"])

        status_code, company_records = self.request_json(
            "GET",
            f"/control-relationships/company/{company_data['id']}",
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(len(company_records), 1)
        self.assertEqual(company_records[0]["id"], record_id)

        update_payload = {
            "control_type": "agreement",
            "notes": "更新后的控制关系",
        }
        status_code, updated_record = self.request_json(
            "PUT",
            f"/control-relationships/{record_id}",
            update_payload,
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(updated_record["control_type"], "agreement")
        self.assertEqual(updated_record["notes"], "更新后的控制关系")

        status_code, _ = self.request_json(
            "DELETE",
            f"/control-relationships/{record_id}",
        )
        self.assertEqual(status_code, 204)

        status_code, not_found_detail = self.request_json(
            "GET",
            f"/control-relationships/{record_id}",
        )
        self.assertEqual(status_code, 404)
        self.assertEqual(not_found_detail["detail"], "Control relationship not found.")

    def test_control_relationship_invalid_id_returns_404(self):
        status_code, response_data = self.request_json(
            "GET",
            "/control-relationships/9999",
        )
        self.assertEqual(status_code, 404)
        self.assertEqual(response_data["detail"], "Control relationship not found.")


if __name__ == "__main__":
    unittest.main()
