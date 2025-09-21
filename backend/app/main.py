from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Optional, Literal

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from dotenv import load_dotenv

# Import SQLAlchemy models (UUID-based)
from models import Base, User, Scenario, Report, Usage

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@db:5432/finance_helper",
)
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

engine = create_async_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

app = FastAPI(title="Finance Helper Backend", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def get_db() -> AsyncSession:
    async with SessionLocal() as session:
        yield session


# ----- Schemas -----
class UserCreate(BaseModel):
    email: str

class UserRead(BaseModel):
    id: uuid.UUID
    email: str
    created_at: datetime

    class Config:
        from_attributes = True

class UsageRead(BaseModel):
    scenarios_run: int
    reports_exported: int

class ScenarioInputs(BaseModel):
    employees: int = Field(..., ge=0)
    salary_per_employee: int = Field(..., ge=0)
    marketing_spend: int = Field(..., ge=0)
    product_price: int = Field(..., ge=0)

class ScenarioSimulateRequest(ScenarioInputs):
    user_id: uuid.UUID

class ScenarioRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    employees: int
    salary_per_employee: int
    marketing_spend: int
    product_price: int
    forecast_summary: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class ScenarioSimulateResponse(BaseModel):
    scenario: ScenarioRead
    usage: UsageRead

class ReportExportRequest(BaseModel):
    user_id: uuid.UUID
    report_type: Literal["pdf", "docx"]
    scenario_id: Optional[uuid.UUID] = None

class ReportRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    scenario_id: Optional[uuid.UUID] = None
    report_type: Literal["pdf", "docx"]
    created_at: datetime

    class Config:
        from_attributes = True


# ----- Health -----
@app.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(select(func.now()))
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {str(e)}")


# ----- Users -----
@app.post("/users", response_model=UserRead)
async def create_user(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    user = User(email=payload.email)
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Email already exists")

    # Ensure Usage row exists (unique per user)
    usage = Usage(user_id=user.id, scenarios_run=0, reports_exported=0)
    db.add(usage)
    await db.commit()
    await db.refresh(user)
    return user


@app.get("/users/{user_id}", response_model=UserRead)
async def get_user(user_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.get("/users/{user_id}/usage", response_model=UsageRead)
async def get_user_usage(user_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    # Validate user exists
    ures = await db.execute(select(User.id).where(User.id == user_id))
    if not ures.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="User not found")

    res = await db.execute(select(Usage).where(Usage.user_id == user_id))
    usage = res.scalar_one_or_none()
    if not usage:
        # Initialize usage if missing
        usage = Usage(user_id=user_id, scenarios_run=0, reports_exported=0)
        db.add(usage)
        await db.commit()
        await db.refresh(usage)
    return UsageRead(scenarios_run=usage.scenarios_run, reports_exported=usage.reports_exported)


# ----- Scenarios -----
@app.post("/scenarios/simulate", response_model=ScenarioSimulateResponse)
async def simulate_scenario(payload: ScenarioSimulateRequest, db: AsyncSession = Depends(get_db)):
    # Validate user
    ures = await db.execute(select(User).where(User.id == payload.user_id))
    user = ures.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Placeholder forecast summary logic
    annual_payroll = payload.employees * payload.salary_per_employee * 12
    annual_marketing = payload.marketing_spend * 12
    revenue_hint = payload.product_price * max(payload.employees * 30, 100)
    summary = (
        f"Hiring {payload.employees} @ {payload.salary_per_employee}/mo, marketing {payload.marketing_spend}/mo, "
        f"price {payload.product_price}. Est. annual payroll {annual_payroll}, marketing {annual_marketing}, "
        f"indicative revenue {revenue_hint}."
    )

    scenario = Scenario(
        user_id=user.id,
        employees=payload.employees,
        salary_per_employee=payload.salary_per_employee,
        marketing_spend=payload.marketing_spend,
        product_price=payload.product_price,
        forecast_summary=summary,
    )
    db.add(scenario)
    await db.flush()  # obtain scenario.id

    # Increment usage
    res = await db.execute(select(Usage).where(Usage.user_id == user.id))
    usage = res.scalar_one_or_none()
    if not usage:
        usage = Usage(user_id=user.id, scenarios_run=0, reports_exported=0)
        db.add(usage)
    usage.scenarios_run = (usage.scenarios_run or 0) + 1

    await db.commit()
    await db.refresh(scenario)

    return ScenarioSimulateResponse(
        scenario=scenario,
        usage=UsageRead(scenarios_run=usage.scenarios_run, reports_exported=usage.reports_exported),
    )


@app.get("/scenarios/{scenario_id}", response_model=ScenarioRead)
async def get_scenario(scenario_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Scenario).where(Scenario.id == scenario_id))
    scenario = res.scalar_one_or_none()
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return scenario


# ----- Reports -----
async def _build_dummy_pdf() -> bytes:
    # Minimal valid PDF header/footer; placeholder
    return (b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Count 0/Kids[]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF")

async def _build_dummy_docx() -> bytes:
    # A minimal docx requires packaging; instead return simple bytes placeholder
    return b"DOCX PLACEHOLDER: Generate real file server-side later."


@app.post("/reports/export")
async def export_report(payload: ReportExportRequest, db: AsyncSession = Depends(get_db)):
    # Validate user
    ures = await db.execute(select(User).where(User.id == payload.user_id))
    user = ures.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    scenario_id: Optional[uuid.UUID] = None
    if payload.scenario_id is not None:
        sres = await db.execute(
            select(Scenario).where(Scenario.id == payload.scenario_id, Scenario.user_id == user.id)
        )
        scenario = sres.scalar_one_or_none()
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")
        scenario_id = scenario.id

    # Create report row
    report = Report(user_id=user.id, scenario_id=scenario_id, report_type=payload.report_type)
    db.add(report)

    # Increment usage
    ures2 = await db.execute(select(Usage).where(Usage.user_id == user.id))
    usage = ures2.scalar_one_or_none()
    if not usage:
        usage = Usage(user_id=user.id, scenarios_run=0, reports_exported=0)
        db.add(usage)
    usage.reports_exported = (usage.reports_exported or 0) + 1

    await db.commit()
    await db.refresh(report)

    # Dummy file content
    if payload.report_type == "pdf":
        content = await _build_dummy_pdf()
        media_type = "application/pdf"
        filename = f"report-{report.id}.pdf"
    else:
        content = await _build_dummy_docx()
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        filename = f"report-{report.id}.docx"

    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return Response(content=content, media_type=media_type, headers=headers)


@app.get("/reports/{report_id}", response_model=ReportRead)
async def get_report(report_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Report).where(Report.id == report_id))
    report = res.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report