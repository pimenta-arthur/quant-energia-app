"""API e servidor local.

- /                      página inicial com as funcionalidades
- /<funcionalidade>/     página da funcionalidade (pasta web/<funcionalidade>)
- /dados/<chave>         arquivos de serving/ (o que as páginas leem)
- /saude                 verificação simples
Na AWS, as páginas e o serving vão para S3 + CloudFront; a API fica para consultas interativas.
Todas as respostas saem com `Cache-Control: no-cache` (revalida sempre; ver `revalidar`).
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from qe_core.config import configuracao

RAIZ = Path(__file__).resolve().parents[3]
WEB = RAIZ / "web"

app = FastAPI(title="quant-energia-app")


@app.middleware("http")
async def revalidar(request, call_next):
    """Páginas, scripts e dados sempre revalidados (ETag/Last-Modified continuam valendo: sem mudança, 304).

    Sem isso o navegador guarda um script antigo por horas e o mistura com uma página nova (por exemplo, o app.js de
    antes com o index.html que ganhou uma coluna: os valores aparecem sob o título errado). Só vale para o servidor
    local; na AWS é a política de cache do CloudFront."""
    resposta = await call_next(request)
    resposta.headers["Cache-Control"] = "no-cache"
    return resposta


@app.get("/saude")
def saude():
    cfg = configuracao()
    return {"status": "ok", "armazenamento": cfg.armazenamento}


@app.get("/dados/{chave:path}")
def dados(chave: str):
    cfg = configuracao()
    if cfg.armazenamento != "local":
        raise HTTPException(501, "na AWS o serving é entregue pelo CloudFront")
    caminho = (Path(cfg.dados) / "serving" / chave).resolve()
    if not caminho.is_relative_to((Path(cfg.dados) / "serving").resolve()) or not caminho.is_file():
        raise HTTPException(404, f"não encontrado: serving/{chave}")
    return FileResponse(caminho)


app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
