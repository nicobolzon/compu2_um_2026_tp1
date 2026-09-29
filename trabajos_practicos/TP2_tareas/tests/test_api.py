import unittest

from fastapi.testclient import TestClient

from app import crear_app


class TestTareasAPI(unittest.TestCase):
    def setUp(self):
        self.cliente = TestClient(crear_app())

    def tearDown(self):
        self.cliente.close()

    def test_ciclo_de_tarea(self):
        creada = self.cliente.post("/tareas", json={"tipo": "esperar", "prioridad": 3})
        self.assertEqual(creada.status_code, 201)
        self.assertEqual(creada.json(), {
            "id": 1, "tipo": "esperar", "prioridad": 3, "estado": "pendiente"
        })
        self.assertEqual(self.cliente.get("/tareas/1").json(), creada.json())
        self.assertEqual(self.cliente.get("/tareas?estado=pendiente").json(), [creada.json()])
        self.assertEqual(self.cliente.get("/estadisticas").json(), {
            "total": 1, "pendientes": 1
        })
        self.assertEqual(self.cliente.delete("/tareas/1").status_code, 204)
        self.assertEqual(self.cliente.get("/tareas/1").status_code, 404)

    def test_validacion_y_ausentes(self):
        self.assertEqual(self.cliente.post("/tareas", json={"tipo": "volar"}).status_code, 422)
        self.assertEqual(self.cliente.post("/tareas", json={
            "tipo": "esperar", "prioridad": 99
        }).status_code, 422)
        self.assertEqual(self.cliente.get("/tareas/abc").status_code, 422)
        self.assertEqual(self.cliente.delete("/tareas/999").status_code, 404)
        self.assertEqual(self.cliente.get("/estadisticas").json()["total"], 0)


if __name__ == "__main__":
    unittest.main()
