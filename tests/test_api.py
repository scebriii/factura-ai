"""
Tests for FacturaAI API.

Run: pytest tests/ -v
"""
import io
from unittest.mock import patch

from fastapi.testclient import TestClient

from scripts.main import app, API_KEY_APP

client = TestClient(app)
HEADERS = {"X-API-Key": API_KEY_APP}

MOCK_INVOICE_DATA = {
    "proveedor": "Acme SL",
    "cif_nif": "B12345678",
    "numero_factura": "F-2024-001",
    "fecha": "2024-01-15",
    "importe_total": 121.0,
    "moneda": "EUR",
    "conceptos": ["Consultoría técnica"],
}


class TestHealth:
    def test_server_active(self):
        res = client.get("/salud")
        assert res.status_code == 200
        assert res.json()["estado"] == "activo"


class TestAuth:
    def test_missing_key_returns_401(self):
        assert client.get("/facturas").status_code == 401

    def test_wrong_key_returns_401(self):
        assert client.get("/facturas", headers={"X-API-Key": "bad-key"}).status_code == 401


class TestFacturas:
    def test_list_returns_correct_shape(self):
        res = client.get("/facturas", headers=HEADERS)
        assert res.status_code == 200
        body = res.json()
        assert "facturas" in body
        assert "total" in body
        assert isinstance(body["facturas"], list)
        assert body["total"] == len(body["facturas"])

    def test_delete_nonexistent_returns_404(self):
        res = client.delete("/facturas/99999", headers=HEADERS)
        assert res.status_code == 404

    def test_upload_non_pdf_returns_400(self):
        res = client.post(
            "/extraer-factura",
            headers=HEADERS,
            files={"archivo": ("doc.txt", io.BytesIO(b"not a pdf"), "text/plain")},
        )
        assert res.status_code == 400

    def test_upload_pdf_returns_extracted_data(self):
        with patch("scripts.main.extraer_texto_pdf", return_value="Texto de prueba"), \
             patch("scripts.main.analizar_factura_con_openai", return_value=MOCK_INVOICE_DATA):
            res = client.post(
                "/extraer-factura",
                headers=HEADERS,
                files={"archivo": ("factura.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
            )
        assert res.status_code == 200
        data = res.json()
        assert data["exito"] is True
        assert data["datos"]["proveedor"] == "Acme SL"
        assert data["datos"]["importe_total"] == 121.0
        assert data["id_factura"] is not None

    def test_upload_and_delete_cycle(self):
        with patch("scripts.main.extraer_texto_pdf", return_value="Texto"), \
             patch("scripts.main.analizar_factura_con_openai", return_value=MOCK_INVOICE_DATA):
            upload = client.post(
                "/extraer-factura",
                headers=HEADERS,
                files={"archivo": ("factura.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
            )
        assert upload.status_code == 200
        invoice_id = upload.json()["id_factura"]

        delete = client.delete(f"/facturas/{invoice_id}", headers=HEADERS)
        assert delete.status_code == 200
        assert delete.json()["exito"] is True

        check = client.delete(f"/facturas/{invoice_id}", headers=HEADERS)
        assert check.status_code == 404


class TestEstadisticas:
    def test_returns_all_required_fields(self):
        res = client.get("/estadisticas", headers=HEADERS)
        assert res.status_code == 200
        body = res.json()
        assert "kpis" in body
        assert "gasto_mensual" in body
        assert "top_proveedores" in body

    def test_kpis_have_correct_keys(self):
        res = client.get("/estadisticas", headers=HEADERS)
        kpis = res.json()["kpis"]
        for key in ("total_facturas", "importe_total", "importe_medio", "proveedores_unicos"):
            assert key in kpis

    def test_kpi_types_are_numeric(self):
        res = client.get("/estadisticas", headers=HEADERS)
        kpis = res.json()["kpis"]
        assert isinstance(kpis["total_facturas"], int)
        assert isinstance(kpis["importe_total"], (int, float))
        assert isinstance(kpis["importe_medio"], (int, float))
