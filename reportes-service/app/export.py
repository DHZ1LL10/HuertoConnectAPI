"""Owner-scoped exports from the V6 diagnostic history in MongoDB."""
import csv
import io
from datetime import date, datetime, timedelta, timezone
from xml.sax.saxutils import escape
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from shared.auth.dependencies import get_current_user
from shared.ownership import require_huerto_access

router = APIRouter(prefix="/api/reportes", tags=["Reportes descargables"])


def diagnostic_query(huerto_id, user, desde=None, hasta=None):
    if desde and hasta and desde > hasta:
        raise HTTPException(422, "La fecha desde no puede ser posterior a hasta")
    query = {"huerto_id": huerto_id, "usuario_id": user["id"]}
    period = {}
    if desde:
        period["$gte"] = datetime.combine(desde, datetime.min.time(), tzinfo=timezone.utc)
    if hasta:
        if hasta == date.max:
            raise HTTPException(422, "Fecha hasta fuera de rango")
        period["$lt"] = datetime.combine(hasta + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    if period:
        query["fecha"] = period
    return query


def safe_cell(value):
    text = str(value if value is not None else "")
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")) else text


def render_report(huerto, diagnostics, format, total=None):
    total = len(diagnostics) if total is None else total
    if format == "csv":
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        fields = ["fecha", "tipo", "clase", "confianza", "modelo", "version", "detectado", "nota"]
        writer.writerow(fields)
        for doc in diagnostics:
            writer.writerow([safe_cell(doc.get(key, "")) for key in fields])
        return stream.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8"

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle
    stream = io.BytesIO()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Cell", fontName="Helvetica", fontSize=8, leading=11, wordWrap="CJK"))
    styles["Title"].textColor = colors.HexColor("#166534")
    styles["Normal"].leading = 14
    def paragraph(value, style="Cell"):
        # Bound legacy free text so one malformed record cannot create an unbreakable row.
        text = str(value if value is not None else "")
        if len(text) > 400:
            text = text[:397] + "..."
        return Paragraph(escape(text), styles[style])
    story = [
        Paragraph("HUERTO CONNECT", styles["Title"]),
        Paragraph("Historial de diagnósticos", styles["Heading2"]),
        paragraph(huerto.get("nombre", "Huerto"), "Heading2"),
        paragraph("Municipio: " + str(huerto.get("municipio") or "No registrado"), "Normal"),
        paragraph("Emitido: " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "Normal"),
        paragraph(f"Registros incluidos: {len(diagnostics)} de {total}.", "Normal"),
        Spacer(1, 12),
        paragraph("Las clasificaciones de IA son orientativas, no diagnósticos confirmados. Un resultado no detectado no demuestra ausencia de plagas o enfermedades.", "Normal"),
        Spacer(1, 16),
    ]
    if total > len(diagnostics):
        story.extend([paragraph("EXPORTACIÓN PARCIAL: se muestran los registros más recientes. Reduce el intervalo de fechas para exportar el resto.", "Normal"), Spacer(1, 12)])
    if not diagnostics:
        story.append(paragraph("Sin diagnósticos en el periodo seleccionado.", "Normal"))
    else:
        rows = [[paragraph(v) for v in ("Fecha UTC / Tipo", "Clasificación / Estado", "Confianza / Modelo")]]
        for doc in diagnostics:
            stamp = doc.get("fecha", "")
            if isinstance(stamp, datetime):
                stamp = stamp.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M") if stamp.tzinfo else stamp.strftime("%Y-%m-%d %H:%M")
            confidence = doc.get("confianza")
            confidence = f"{confidence:.1%}" if isinstance(confidence, (int, float)) else "No registrada"
            status = "Compatible según umbral" if doc.get("detectado") is True else "No confirmado"
            rows.append([
                paragraph(f"{stamp} | {doc.get('tipo', '')}"),
                paragraph(f"{doc.get('clase', '')} | {status}. {doc.get('nota', '')}"),
                paragraph(f"{confidence} | {doc.get('modelo', '')} | {doc.get('version', '')}"),
            ])
        table = LongTable(rows, colWidths=[105, 270, 140], repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dcfce7")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ("TOPPADDING", (0, 0), (-1, -1), 9),
            ("LINEBELOW", (0, 0), (-1, 0), 1, colors.HexColor("#166534")),
        ]))
        story.append(table)
    def footer(canvas, document):
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(40, 24, "Huerto Connect | Uso informativo")
        canvas.drawRightString(A4[0] - 40, 24, f"Página {document.page}")
    SimpleDocTemplate(stream, pagesize=A4, leftMargin=40, rightMargin=40, topMargin=36, bottomMargin=40, title="Huerto Connect - Historial de diagnósticos", author="Huerto Connect").build(story, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue(), "application/pdf"


@router.get("/huertos/{huerto_id}/{formato}", responses={401: {}, 404: {}, 422: {}, 503: {}})
async def export(huerto_id: str, formato: Literal["csv", "pdf"], request: Request,
                 desde: date | None = None, hasta: date | None = None,
                 limite: int = Query(1000, ge=1, le=1000), user=Depends(get_current_user)):
    db = request.app.state.mongodb
    huerto = await require_huerto_access(db, huerto_id, user)
    query = diagnostic_query(huerto_id, user, desde, hasta)
    total = await db.diagnosticos.count_documents(query)
    docs = await db.diagnosticos.find(query).sort([("fecha", -1), ("_id", -1)]).limit(limite).to_list(limite)
    content, media = await run_in_threadpool(render_report, huerto, docs, formato, total)
    await db.reporte_exportaciones.insert_one({"huerto_id": huerto_id, "usuario_id": user["id"], "formato": formato, "fecha": datetime.now(timezone.utc), "registros": len(docs), "total": total, "parcial": total > len(docs)})
    return Response(content, media_type=media, headers={
        "Content-Disposition": f'attachment; filename="huerto-{huerto_id}.{formato}"',
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        "X-Report-Total": str(total), "X-Report-Records": str(len(docs)),
        "X-Report-Truncated": str(total > len(docs)).lower(),
    })


@router.get("/huertos/{huerto_id}/estadisticas/resumen")
async def statistics(huerto_id: str, request: Request, desde: date | None = None,
                     hasta: date | None = None, user=Depends(get_current_user)):
    db = request.app.state.mongodb
    await require_huerto_access(db, huerto_id, user)
    query = diagnostic_query(huerto_id, user, desde, hasta)
    total = await db.diagnosticos.count_documents(query)
    detected = await db.diagnosticos.count_documents({**query, "detectado": True})
    return {"huerto_id": huerto_id, "total": total, "detectados": detected,
            "no_detectados": await db.diagnosticos.count_documents({**query, "detectado": False})}
