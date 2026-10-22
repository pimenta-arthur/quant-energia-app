"""Servidor local: páginas, scripts e dados saem com Cache-Control: no-cache, para o navegador nunca misturar uma página
nova com um script antigo em cache. Chama a aplicação ASGI direto (o projeto não depende de um cliente HTTP)."""

import asyncio

from qe_api.app import app


def _get(caminho: str, cabecalhos: list[tuple[bytes, bytes]] | None = None):
    resposta = {"cabecalhos": {}}

    async def rodar():
        escopo = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": caminho,
            "raw_path": caminho.encode(),
            "query_string": b"",
            "headers": cabecalhos or [],
            "server": ("localhost", 8000),
            "client": ("127.0.0.1", 1),
        }

        async def receber():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def enviar(msg):
            if msg["type"] == "http.response.start":
                resposta["status"] = msg["status"]
                resposta["cabecalhos"] = {k.decode().lower(): v.decode() for k, v in msg["headers"]}

        await app(escopo, receber, enviar)

    asyncio.run(rodar())
    return resposta


def test_pagina_e_script_saem_com_no_cache():
    for caminho in ("/pricing_descolamento/app.js", "/pricing_descolamento/", "/saude"):
        r = _get(caminho)
        assert r["status"] == 200, caminho
        assert r["cabecalhos"]["cache-control"] == "no-cache", caminho


def test_sem_mudanca_continua_dando_304():
    """no-cache não desliga a economia de banda: com o ETag igual, a resposta é 304."""
    r = _get("/pricing_descolamento/app.js")
    etag = r["cabecalhos"]["etag"]
    r2 = _get("/pricing_descolamento/app.js", [(b"if-none-match", etag.encode())])
    assert r2["status"] == 304
    assert r2["cabecalhos"]["cache-control"] == "no-cache"
