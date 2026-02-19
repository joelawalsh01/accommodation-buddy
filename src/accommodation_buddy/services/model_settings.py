from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from accommodation_buddy.config import settings
from accommodation_buddy.db.models import TeacherModelSettings


@dataclass
class ResolvedModelSettings:
    scaffolding_model: str
    ocr_model: str
    translation_model: str
    keep_alive: str

    def model_for_role(self, role: str) -> str:
        return getattr(self, f"{role}_model", self.scaffolding_model)


def _system_defaults() -> ResolvedModelSettings:
    return ResolvedModelSettings(
        scaffolding_model=settings.scaffolding_model,
        ocr_model=settings.ocr_model,
        translation_model=settings.translation_model,
        keep_alive="5m",
    )


async def get_teacher_model_settings(
    teacher_id: int, db: AsyncSession
) -> ResolvedModelSettings:
    result = await db.execute(
        select(TeacherModelSettings).where(
            TeacherModelSettings.teacher_id == teacher_id
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return _system_defaults()

    defaults = _system_defaults()
    return ResolvedModelSettings(
        scaffolding_model=row.scaffolding_model or defaults.scaffolding_model,
        ocr_model=row.ocr_model or defaults.ocr_model,
        translation_model=row.translation_model or defaults.translation_model,
        keep_alive=row.keep_alive or defaults.keep_alive,
    )


async def save_teacher_model_settings(
    teacher_id: int,
    db: AsyncSession,
    scaffolding_model: str | None = None,
    ocr_model: str | None = None,
    translation_model: str | None = None,
    keep_alive: str = "5m",
) -> TeacherModelSettings:
    result = await db.execute(
        select(TeacherModelSettings).where(
            TeacherModelSettings.teacher_id == teacher_id
        )
    )
    row = result.scalar_one_or_none()

    if row is None:
        row = TeacherModelSettings(teacher_id=teacher_id)
        db.add(row)

    row.scaffolding_model = scaffolding_model or None
    row.ocr_model = ocr_model or None
    row.translation_model = translation_model or None
    row.keep_alive = keep_alive

    await db.commit()
    await db.refresh(row)
    return row
