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


class ShareholderApiTestCase(unittest.TestCase):
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

    def test_shareholder_entity_and_structure_flow(self):
        company_payload = {
            "name": "Tencent",
            "stock_code": "00700",
            "incorporation_country": "Cayman Islands",
            "listing_country": "Hong Kong",
            "headquarters": "Shenzhen",
            "description": "互联网企业",
        }
        status_code, company_data = self.request_json(
            "POST",
            "/companies",
            company_payload,
        )
        self.assertEqual(status_code, 201)

        company_entity_payload = {
            "entity_name": company_data["name"],
            "entity_type": "company",
            "country": company_data["incorporation_country"],
            "company_id": company_data["id"],
            "identifier_code": company_data["stock_code"],
            "is_listed": True,
            "notes": "公司映射主体",
        }
        status_code, company_entity = self.request_json(
            "POST",
            "/shareholders/entities",
            company_entity_payload,
        )
        self.assertEqual(status_code, 201)
        self.assertEqual(company_entity["company_id"], company_data["id"])

        investor_entity_payload = {
            "entity_name": "Naspers",
            "entity_type": "institution",
            "country": "South Africa",
            "company_id": None,
            "identifier_code": None,
            "is_listed": True,
            "notes": "示例投资主体",
        }
        status_code, investor_entity = self.request_json(
            "POST",
            "/shareholders/entities",
            investor_entity_payload,
        )
        self.assertEqual(status_code, 201)
        self.assertEqual(investor_entity["entity_name"], "Naspers")

        investor_entity_id = investor_entity["id"]
        company_entity_id = company_entity["id"]

        status_code, entity_list = self.request_json("GET", "/shareholders/entities")
        self.assertEqual(status_code, 200)
        self.assertEqual(len(entity_list), 2)

        update_entity_payload = {
            "notes": "更新后的主体备注",
        }
        status_code, updated_entity = self.request_json(
            "PUT",
            f"/shareholders/entities/{investor_entity_id}",
            update_entity_payload,
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(updated_entity["notes"], "更新后的主体备注")

        structure_payload = {
            "from_entity_id": investor_entity_id,
            "to_entity_id": company_entity_id,
            "holding_ratio": "28.5000",
            "is_direct": True,
            "control_type": "equity",
            "reporting_period": "2025-12-31",
            "effective_date": "2025-01-01",
            "expiry_date": None,
            "is_current": True,
            "source": "annual report",
            "remarks": "示例股权边",
        }
        status_code, structure_data = self.request_json(
            "POST",
            "/shareholders/structures",
            structure_payload,
        )
        self.assertEqual(status_code, 201)
        self.assertEqual(structure_data["from_entity_id"], investor_entity_id)
        self.assertEqual(structure_data["to_entity_id"], company_entity_id)

        structure_id = structure_data["id"]

        status_code, structure_list = self.request_json(
            "GET",
            f"/shareholders/structures?to_entity_id={company_entity_id}",
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(len(structure_list), 1)

        update_structure_payload = {
            "remarks": "更新后的股权边备注",
        }
        status_code, updated_structure = self.request_json(
            "PUT",
            f"/shareholders/structures/{structure_id}",
            update_structure_payload,
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(updated_structure["remarks"], "更新后的股权边备注")

        status_code, _ = self.request_json(
            "DELETE",
            f"/shareholders/structures/{structure_id}",
        )
        self.assertEqual(status_code, 204)

        status_code, structure_not_found = self.request_json(
            "GET",
            f"/shareholders/structures/{structure_id}",
        )
        self.assertEqual(status_code, 404)
        self.assertEqual(
            structure_not_found["detail"],
            "Shareholder structure not found.",
        )

        status_code, _ = self.request_json(
            "DELETE",
            f"/shareholders/entities/{investor_entity_id}",
        )
        self.assertEqual(status_code, 204)

        status_code, _ = self.request_json(
            "DELETE",
            f"/shareholders/entities/{company_entity_id}",
        )
        self.assertEqual(status_code, 204)

    def test_create_structure_with_invalid_references_returns_404(self):
        invalid_structure_payload = {
            "from_entity_id": 9999,
            "to_entity_id": 9998,
            "holding_ratio": "10.0000",
            "is_direct": True,
            "control_type": "equity",
            "reporting_period": "2025-12-31",
            "effective_date": "2025-01-01",
            "expiry_date": None,
            "is_current": True,
            "source": "invalid source",
            "remarks": "无效外键测试",
        }
        status_code, response_data = self.request_json(
            "POST",
            "/shareholders/structures",
            invalid_structure_payload,
        )
        self.assertEqual(status_code, 404)
        self.assertEqual(response_data["detail"], "Shareholder entity not found.")


if __name__ == "__main__":
    unittest.main()
