"""Que el contrato, la guía y la versión no se desactualicen respecto al código."""

import json
import re
import tomllib
from pathlib import Path
from urllib.parse import unquote

from app.main import app

DOCS = Path("docs")


def _guia() -> str:
    return (DOCS / "integracion.md").read_text(encoding="utf-8")


def test_el_contrato_openapi_esta_al_dia():
    publicado = json.loads((DOCS / "openapi.json").read_text(encoding="utf-8"))
    assert publicado == json.loads(json.dumps(app.openapi())), "docs/openapi.json está desactualizado: ejecuta `make openapi`"


def test_la_version_coincide_en_pyproject_la_aplicacion_y_el_contrato():
    en_pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    assert app.version == en_pyproject == app.openapi()["info"]["version"]


def test_el_contrato_produce_nombres_limpios_para_los_generadores_de_clientes():
    contrato = app.openapi()
    assert contrato["info"]["title"].isascii()
    ids = []
    for ruta, operaciones in contrato["paths"].items():
        for metodo, op in operaciones.items():
            assert re.fullmatch(r"[a-z][A-Za-z0-9]*", op["operationId"]), f"{metodo} {ruta}: {op['operationId']}"
            assert all(t.isascii() and t.isalnum() for t in op["tags"]), f"{metodo} {ruta}: {op['tags']}"
            ids.append(op["operationId"])
    assert len(ids) == len(set(ids))


def test_el_contrato_declara_alcances_y_errores_en_cada_endpoint_protegido():
    for ruta, operaciones in app.openapi()["paths"].items():
        for op in operaciones.values():
            if ruta == "/health":
                continue
            esquemas = {k for req in op["security"] for k in req}
            assert esquemas == {"GatewaySecret", "OAuth2Gateway"}, ruta
            assert {"401", "500"} <= set(op["responses"]), ruta


def test_cada_endpoint_del_contrato_esta_en_la_guia_de_integracion():
    guia = _guia()
    for ruta in app.openapi()["paths"]:
        publica = ruta if ruta == "/flota/alertas" else f"/flota{ruta}"  # el gateway antepone /flota
        assert f"GET {publica}" in guia, f"falta en integracion.md: GET {publica}"


def test_el_catalogo_de_errores_coincide_con_los_codigos_del_codigo_fuente():
    en_codigo = set()
    for f in Path("app").rglob("*.py"):
        t = f.read_text(encoding="utf-8")
        en_codigo |= set(re.findall(r'_respuesta\(\s*\d+,\s*"([a-z_]+)"', t))
        en_codigo |= set(re.findall(r'cuerpo_error\(\s*"([a-z_]+)"', t))
        en_codigo |= set(re.findall(r'\d+: "([a-z_]+)"', t))
    en_codigo |= {"error_http"}  # el predeterminado de los demás errores HTTP
    guia = _guia()
    catalogo = guia[guia.index("## 7. Catálogo de errores") : guia.index("## 8.")]
    en_catalogo = {c for c in re.findall(r"`([a-z_]+)`", catalogo) if "_" in c and c not in {"detalle_servicio"}}
    en_catalogo -= {"viajes_zonas", "flota_crud", "gateway_token"}  # nombres de servicio, no códigos
    assert en_codigo - en_catalogo == set(), f"códigos sin documentar: {en_codigo - en_catalogo}"
    assert en_catalogo - en_codigo == set(), f"documentados pero inexistentes: {en_catalogo - en_codigo}"


def _ancla(titulo: str) -> str:
    t = re.sub(r"[^\w\s-]", "", titulo.strip().lower())
    return re.sub(r"\s", "-", t)


def test_los_enlaces_entre_documentos_existen_y_sus_anclas_tambien():
    fallos = []
    for md in sorted(DOCS.glob("*.md")):
        for destino in re.findall(r"\]\(([^)\s]+)\)", md.read_text(encoding="utf-8")):
            if destino.startswith(("http://", "https://", "mailto:")):
                continue
            ruta, _, ancla = destino.partition("#")
            objetivo = (md.parent / unquote(ruta)).resolve() if ruta else md.resolve()
            if not objetivo.exists():
                fallos.append(f"{md.name}: no existe {destino}")
            elif ancla and objetivo.suffix == ".md":
                titulos = re.findall(r"^#+\s+(.*)$", objetivo.read_text(encoding="utf-8"), flags=re.M)
                if ancla not in {_ancla(t) for t in titulos}:
                    fallos.append(f"{md.name}: la ancla #{ancla} no existe en {objetivo.name}")
    assert not fallos, "\n".join(fallos)


def test_la_guia_no_manda_a_clonar_ni_levantar_el_servicio():
    """Las APIs son servicios independientes en la nube: quien consume no clona ni levanta nada."""
    guia = _guia().lower()
    for prohibido in ("git clone", "docker compose up", "make up", "app/dominio"):
        assert prohibido not in guia, f"la guía menciona «{prohibido}»"
