import os
import json
import asyncio
from datetime import datetime
from typing import List, Optional, Literal

import httpx
import pandas as pd
from fastapi import FastAPI, Depends, Header, HTTPException, Response, Path
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey
from sse_starlette.sse import EventSourceResponse
from docx import Document
from io import BytesIO
from dotenv import load_dotenv
# PDF
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/finance_helper")
FLEXPRICE_API_KEY = os.getenv("FLEXPRICE_API_KEY", "")
FLEXPRICE_ACCOUNT_ID = os.getenv("FLEXPRICE_ACCOUNT_ID", "")
PATHWAY_API_KEY = os.getenv("PATHWAY_API_KEY", "")

origins = os.getenv("CORS_ORIGINS", "*").split(",")

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(unique=True, index=True)
    scenarios: Mapped[List["Scenario"]] = relationship(back_populates="user")
    usage: Mapped[Optional["Usage"]] = relationship(back_populates="user", uselist=False)
    reports: Mapped[List["Report"]] = relationship(back_populates="user")

class Scenario(Base):
    __tablename__ = "scenarios"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    inputs: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    user: Mapped[User] = relationship(back_populates="scenarios")

class Report(Base):
    __tablename__ = "reports"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    scenario_id: Mapped[Optional[int]] = mapped_column(ForeignKey("scenarios.id", ondelete="SET NULL"), nullable=True)
    format: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    user: Mapped[User] = relationship(back_populates="reports")

class Usage(Base):
    __tablename__ = "usage"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    scenarios_count: Mapped[int] = mapped_column(default=0)
    reports_count: Mapped[int] = mapped_column(default=0)
    user: Mapped[User] = relationship(back_populates="usage")

engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

app = FastAPI(title="Finance Helper Backend", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def get_db():
    async with SessionLocal() as session:
        yield session


class Inputs(BaseModel):
    employees: int
    salary: int
    marketing: int
    price: int
    cash: int

class ForecastPoint(BaseModel):
    month: str
    revenue: float
    expenses: float
    profit: float
    runway: float
    customers: int

class ForecastResponse(BaseModel):
    forecast: List[ForecastPoint]
    usage: dict

class UsageResponse(BaseModel):
    scenarios: int
    reports: int

class RegisterPayload(BaseModel):
    external_id: str

class ReportExportRequest(BaseModel):
    scenario_id: Optional[int] = None
    inputs: Optional[Inputs] = None
    format: Literal["pdf", "docx"] = "docx"


async def get_or_create_user(session: AsyncSession, external_id: str) -> User:
    q = await session.execute(select(User).where(User.external_id == external_id))
    user = q.scalar_one_or_none()
    if not user:
        user = User(external_id=external_id)
        session.add(user)
        await session.flush()
        usage = Usage(user_id=user.id, scenarios_count=0, reports_count=0)
        session.add(usage)
        await session.commit()
        await session.refresh(user)
    return user


def calculate_forecast(inputs: Inputs, months: int = 12, base_customers: int = 500) -> List[ForecastPoint]:
    # Pandas-based calculation
    cust_growth_from_marketing = min(max(inputs.marketing / 200_000, 0), 0.5)
    monthly_growth = cust_growth_from_marketing / 12

    customers = [base_customers]
    for _ in range(1, months):
        customers.append(int(round(customers[-1] * (1 + monthly_growth))))

    df = pd.DataFrame({
        "month": [f"M{i+1}" for i in range(months)],
        "customers": customers,
    })
    df["revenue"] = df["customers"] * inputs.price
    payroll = inputs.employees * inputs.salary
    ops = round(0.15 * payroll)
    df["expenses"] = payroll + inputs.marketing + ops
    df["profit"] = df["revenue"] - df["expenses"]

    cash_balance = inputs.cash
    runway = []
    for _, row in df.iterrows():
        cash_balance += row["profit"]
        monthly_burn = max(row["expenses"] - row["revenue"], 0)
        runway.append( (cash_balance / monthly_burn) if monthly_burn > 0 else 120.0 )
    df["runway"] = runway

    return [ForecastPoint(**row) for row in df.to_dict("records")]  # type: ignore


async def flexprice_charge(action: str, amount: int):
    if not FLEXPRICE_API_KEY or not FLEXPRICE_ACCOUNT_ID:
        return {"mock": True}
    url = "https://api.flexprice.dev/v1/charges"
    headers = {"Authorization": f"Bearer {FLEXPRICE_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "account_id": FLEXPRICE_ACCOUNT_ID,
        "amount": amount,
        "currency": "INR",
        "description": f"FinanceHelper {action}"
    }
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(url, headers=headers, json=payload)
        if r.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Flexprice error: {r.text}")
        return r.json()


@app.on_event("startup")
async def on_startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@app.get("/health")
async def health():
    return {"ok": True, "time": datetime.utcnow().isoformat()}


# --- User & Usage Management ---
@app.post("/user")
async def create_user(payload: RegisterPayload, db: AsyncSession = Depends(get_db)):
    user = await get_or_create_user(db, payload.external_id)
    return {"id": user.id, "external_id": user.external_id}


@app.get("/user/{identifier}/usage", response_model=UsageResponse)
async def user_usage(identifier: str = Path(...), db: AsyncSession = Depends(get_db)):
    # identifier can be internal numeric id or external_id
    user: Optional[User] = None
    if identifier.isdigit():
        q = await db.execute(select(User).where(User.id == int(identifier)))
        user = q.scalar_one_or_none()
    if not user:
        q = await db.execute(select(User).where(User.external_id == identifier))
        user = q.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    uq = await db.execute(select(Usage).where(Usage.user_id == user.id))
    u = uq.scalar_one_or_none()
    if not u:
        u = Usage(user_id=user.id, scenarios_count=0, reports_count=0)
        db.add(u)
        await db.commit()
    return {"scenarios": u.scenarios_count, "reports": u.reports_count}


# Back-compat simple usage fetch via Authorization header
@app.get("/usage", response_model=UsageResponse)
async def get_usage(db: AsyncSession = Depends(get_db), authorization: str | None = Header(default=None)):
    ext_id = authorization or "anonymous"
    user = await get_or_create_user(db, ext_id)
    q = await db.execute(select(Usage).where(Usage.user_id == user.id))
    u = q.scalar_one()
    return {"scenarios": u.scenarios_count, "reports": u.reports_count}


# --- Scenario Simulation ---
@app.post("/scenario/simulate", response_model=ForecastResponse)
async def scenario_simulate(inputs: Inputs, db: AsyncSession = Depends(get_db), authorization: str | None = Header(default=None)):
    ext_id = authorization or "anonymous"
    user = await get_or_create_user(db, ext_id)

    # store scenario
    scenario = Scenario(user_id=user.id, inputs=json.dumps(inputs.dict()))
    db.add(scenario)

    # increment usage
    q = await db.execute(select(Usage).where(Usage.user_id == user.id))
    usage = q.scalar_one()
    usage.scenarios_count += 1

    await db.commit()

    # charge via Flexprice (async, fire-and-forget)
    asyncio.create_task(flexprice_charge("scenario", 15))

    forecast = calculate_forecast(inputs)
    return {"forecast": [f.model_dump() for f in forecast], "usage": {"scenarios": usage.scenarios_count, "reports": usage.reports_count}}


# Back-compat alias
@app.post("/simulate", response_model=ForecastResponse)
async def simulate(inputs: Inputs, db: AsyncSession = Depends(get_db), authorization: str | None = Header(default=None)):
    return await scenario_simulate(inputs, db, authorization)


# --- Report Export ---
async def _build_docx(inputs: Inputs) -> bytes:
    forecast = calculate_forecast(inputs)
    first, last = forecast[0], forecast[-1]
    doc = Document()
    doc.add_heading("Finance Helper Report", 0)

    doc.add_heading("Key Inputs", level=1)
    tbl = doc.add_table(rows=0, cols=2)
    for k, v in {
        "Employees": inputs.employees,
        "Salary (₹/mo)": inputs.salary,
        "Marketing (₹/mo)": inputs.marketing,
        "Price (₹)": inputs.price,
        "Starting Cash (₹)": inputs.cash,
    }.items():
        row = tbl.add_row().cells
        row[0].text = str(k)
        row[1].text = str(v)

    doc.add_heading("Forecast Metrics", level=1)
    p = doc.add_paragraph()
    p.add_run(f"Month 1: Rev {first.revenue:.0f}, Exp {first.expenses:.0f}, Profit {first.profit:.0f}, Runway {first.runway:.1f}m\n")
    p.add_run(f"Month 12: Rev {last.revenue:.0f}, Exp {last.expenses:.0f}, Profit {last.profit:.0f}, Runway {last.runway:.1f}m")

    doc.add_heading("Forecast Table", level=1)
    ft = doc.add_table(rows=1, cols=5)
    hdr = ft.rows[0].cells
    hdr[0].text = "Month"
    hdr[1].text = "Revenue"
    hdr[2].text = "Expenses"
    hdr[3].text = "Profit"
    hdr[4].text = "Runway (m)"
    for f in forecast:
        r = ft.add_row().cells
        r[0].text = f.month
        r[1].text = f"{f.revenue:.0f}"
        r[2].text = f"{f.expenses:.0f}"
        r[3].text = f"{f.profit:.0f}"
        r[4].text = f"{f.runway:.1f}"

    bio = BytesIO()
    doc.save(bio)
    bio.seek(0)
    return bio.getvalue()


async def _build_pdf(inputs: Inputs) -> bytes:
    forecast = calculate_forecast(inputs)
    first, last = forecast[0], forecast[-1]
    bio = BytesIO()
    c = canvas.Canvas(bio, pagesize=A4)
    width, height = A4
    y = height - 40
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, y, "Finance Helper Report")
    y -= 30

    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Key Inputs")
    y -= 18
    c.setFont("Helvetica", 11)
    for k, v in [
        ("Employees", inputs.employees),
        ("Salary (₹/mo)", inputs.salary),
        ("Marketing (₹/mo)", inputs.marketing),
        ("Price (₹)", inputs.price),
        ("Starting Cash (₹)", inputs.cash),
    ]:
        c.drawString(50, y, f"{k}: {v}")
        y -= 16

    y -= 8
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Forecast Metrics")
    y -= 18
    c.setFont("Helvetica", 11)
    c.drawString(50, y, f"Month 1 -> Rev {first.revenue:.0f}, Exp {first.expenses:.0f}, Profit {first.profit:.0f}, Runway {first.runway:.1f}m")
    y -= 16
    c.drawString(50, y, f"Month 12 -> Rev {last.revenue:.0f}, Exp {last.expenses:.0f}, Profit {last.profit:.0f}, Runway {last.runway:.1f}m")

    c.showPage()
    c.save()
    bio.seek(0)
    return bio.getvalue()


@app.post("/report/export")
async def report_export(req: ReportExportRequest, db: AsyncSession = Depends(get_db), authorization: str | None = Header(default=None)):
    ext_id = authorization or "anonymous"
    user = await get_or_create_user(db, ext_id)

    # derive inputs from scenario if provided
    inputs: Optional[Inputs] = req.inputs
    scenario_id: Optional[int] = None
    if req.scenario_id is not None:
        sq = await db.execute(select(Scenario).where(Scenario.id == req.scenario_id, Scenario.user_id == user.id))
        scenario = sq.scalar_one_or_none()
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")
        scenario_id = scenario.id
        inputs = Inputs(**json.loads(scenario.inputs))
    if inputs is None:
        raise HTTPException(status_code=400, detail="Provide either scenario_id or inputs")

    # build file
    if req.format == "pdf":
        content = await _build_pdf(inputs)
        media_type = "application/pdf"
        filename = "finance-helper-report.pdf"
    else:
        content = await _build_docx(inputs)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        filename = "finance-helper-report.docx"

    # store report record
    rpt = Report(user_id=user.id, scenario_id=scenario_id, format=req.format)
    db.add(rpt)

    # increment usage and charge
    uq = await db.execute(select(Usage).where(Usage.user_id == user.id))
    usage = uq.scalar_one()
    usage.reports_count += 1
    await db.commit()

    asyncio.create_task(flexprice_charge("report", 35))

    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return Response(content=content, media_type=media_type, headers=headers)


# Back-compat existing docx endpoint
@app.post("/export/docx")
async def export_docx(inputs: Inputs, db: AsyncSession = Depends(get_db), authorization: str | None = Header(default=None)):
    content = await _build_docx(inputs)
    # increment report usage and charge
    # ... keep existing logic by reusing /report/export behavior would double count; so just bill once here
    ext_id = authorization or "anonymous"
    user = await get_or_create_user(db, ext_id)
    db.add(Report(user_id=user.id, scenario_id=None, format="docx"))
    uq = await db.execute(select(Usage).where(Usage.user_id == user.id))
    usage = uq.scalar_one()
    usage.reports_count += 1
    await db.commit()
    asyncio.create_task(flexprice_charge("report", 35))

    headers = {"Content-Disposition": "attachment; filename=finance-helper-report.docx"}
    return Response(content=content, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", headers=headers)


# --- Pathway Integration (SSE mock/live) ---
@app.get("/pathway/stream")
async def pathway_stream():
    async def event_generator():
        while True:
            # Placeholder for real Pathway integration
            # Emit small random pct between -2% and +2%
            import random
            delta = random.uniform(-0.02, 0.02)
            yield {
                "event": "update",
                "data": json.dumps({"revenueDeltaPct": delta})
            }
            await asyncio.sleep(10)

    return EventSourceResponse(event_generator())


# Spec-compliant alias
@app.get("/pathway/live")
async def pathway_live():
    return await pathway_stream()