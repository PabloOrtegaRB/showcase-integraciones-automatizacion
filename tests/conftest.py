import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Configuracion
from app.main import crear_app
from tests.ayudas import SECRETO, ProveedorGuionado


@pytest.fixture
def configuracion(tmp_path):
    return Configuracion(ruta_bd=str(tmp_path / "prueba.db"), url_proveedor="http://proveedor.prueba",
                         url_webhook_publica="http://api.prueba/webhooks/proveedor", secreto_webhook=SECRETO,
                         max_intentos=3, espera_base=0)


@pytest.fixture
def crear_cliente(configuracion):
    """Crea la API con un proveedor guionado y sin esperas reales entre reintentos."""
    def _crear(guion=()):
        proveedor = ProveedorGuionado(guion)
        app = crear_app(configuracion, transporte=httpx.MockTransport(proveedor), dormir=lambda segundos: None)
        return TestClient(app), proveedor
    return _crear
