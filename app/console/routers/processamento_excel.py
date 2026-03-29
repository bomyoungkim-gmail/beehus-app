from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from core.services.positions_excel_processor import process_positions_excel

router = APIRouter(prefix="/processamento-excel", tags=["Processamento Excel"])


def _cleanup_files(paths: list[Path]) -> None:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass


@router.post("/process")
async def process_excel_files(
    depara_file: UploadFile = File(...),
    holdings_file: UploadFile = File(...),
):
    if not depara_file.filename or not holdings_file.filename:
        raise HTTPException(status_code=400, detail="Arquivos invalidos.")

    tmp_dir = Path(tempfile.gettempdir())
    depara_path = tmp_dir / f"depara_{uuid4().hex}.xlsx"
    holdings_path = tmp_dir / f"holdings_{uuid4().hex}.xlsx"

    depara_path.write_bytes(await depara_file.read())
    holdings_path.write_bytes(await holdings_file.read())

    try:
        output_path = process_positions_excel(holdings_path=holdings_path, depara_path=depara_path, output_dir=tmp_dir)
    except Exception as exc:
        _cleanup_files([depara_path, holdings_path])
        raise HTTPException(status_code=500, detail=f"Falha ao processar arquivo: {exc}") from exc

    background = BackgroundTask(_cleanup_files, [depara_path, holdings_path, output_path])
    return FileResponse(
        path=output_path,
        filename=output_path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        background=background,
    )
