"""API e servidor local.

- /                      página inicial com as funcionalidades
- /<funcionalidade>/     página da funcionalidade (pasta web/<funcionalidade>)
- /dados/<chave>         arquivos de serving/ (o que as páginas leem)
- /saude                 verificação simples
Na AWS, as páginas e o serving vão para S3 + CloudFront; a API fica para consultas interativas.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from qe_core.config import configuracao

RAIZ = Path(__file__).resolve().parents[3]
WEB = RAIZ / "web"

app = FastAPI(title="quant-energia-app")


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
