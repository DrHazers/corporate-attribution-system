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


class CompanyApiTestCase(unittest.TestCase):
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

    def test_company_crud_flow(self):
        create_payload = {
            "name": "BYD",
            "stock_code": "002594",
            "incorporation_country": "China",
            "listing_country": "China",
            "headquarters": "Shenzhen",
            "description": "新能源与汽车制造企业",
        }

        status_code, created_company = self.request_json(
            "POST",
            "/companies",
            create_payload,
        )
        self.assertEqual(status_code, 201)
        self.assertEqual(created_company["name"], "BYD")

        company_id = created_company["id"]

        status_code, company_list = self.request_json("GET", "/companies")
        self.assertEqual(status_code, 200)
        self.assertEqual(len(company_list), 1)

        status_code, company_detail = self.request_json(
            "GET",
            f"/companies/{company_id}",
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(company_detail["stock_code"], "002594")

        update_payload = {
            "name": "BYD Auto",
            "stock_code": "002594",
            "incorporation_country": "China",
            "listing_country": "China",
            "headquarters": "Shenzhen",
            "description": "更新后的企业描述",
        }

        status_code, updated_company = self.request_json(
            "PUT",
            f"/companies/{company_id}",
            update_payload,
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(updated_company["name"], "BYD Auto")

        status_code, _ = self.request_json("DELETE", f"/companies/{company_id}")
        self.assertEqual(status_code, 204)

        status_code, not_found_detail = self.request_json(
            "GET",
            f"/companies/{company_id}",
        )
        self.assertEqual(status_code, 404)
        self.assertEqual(not_found_detail["detail"], "Company not found.")

    def test_update_missing_company_returns_404(self):
        update_payload = {
            "name": "Missing Company",
            "stock_code": "MISSING-001",
            "incorporation_country": "China",
            "listing_country": "China",
            "headquarters": "Beijing",
            "description": "不存在的企业",
        }

        status_code, response_data = self.request_json(
            "PUT",
            "/companies/9999",
            update_payload,
        )
        self.assertEqual(status_code, 404)
        self.assertEqual(response_data["detail"], "Company not found.")

    def test_delete_missing_company_returns_404(self):
        status_code, response_data = self.request_json("DELETE", "/companies/9999")
        self.assertEqual(status_code, 404)
        self.assertEqual(response_data["detail"], "Company not found.")

    def test_relationship_graph_empty_state_is_frontend_friendly(self):
        create_payload = {
            "name": "Demo Graph Company",
            "stock_code": "GRAPH-001",
            "incorporation_country": "China",
            "listing_country": "China",
            "headquarters": "Shanghai",
            "description": "用于关系图空状态验证",
        }

        status_code, created_company = self.request_json(
            "POST",
            "/companies",
            create_payload,
        )
        self.assertEqual(status_code, 201)

        graph_status, graph_payload = self.request_json(
            "GET",
            f"/companies/{created_company['id']}/relationship-graph",
        )
        self.assertEqual(graph_status, 200)
        self.assertEqual(
            graph_payload["message"],
            "Mapped shareholder entity not found for company.",
        )
        self.assertEqual(graph_payload["target_company"]["id"], created_company["id"])
        self.assertEqual(graph_payload["target_company"]["stock_code"], "GRAPH-001")
        self.assertIsNone(graph_payload["target_entity_id"])
        self.assertEqual(graph_payload["node_count"], 0)
        self.assertEqual(graph_payload["edge_count"], 0)
        self.assertEqual(graph_payload["nodes"], [])
        self.assertEqual(graph_payload["edges"], [])

    def test_company_scoped_validation_errors_return_400(self):
        status_code, response_data = self.request_json(
            "GET",
            "/companies/not-an-int/relationship-graph",
        )
        self.assertEqual(status_code, 400)
        self.assertIn("path.company_id", response_data["detail"])


if __name__ == "__main__":
    unittest.main()


