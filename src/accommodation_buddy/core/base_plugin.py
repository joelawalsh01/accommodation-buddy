from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import APIRouter
    from sqlalchemy.ext.asyncio import AsyncSession


class PluginCategory(Enum):
    DOCUMENT_ACCOMMODATION = "document_accommodation"
    STUDENT_TOOL = "student_tool"
    TEACHER_TOOL = "teacher_tool"
    LIVE_MODE = "live_mode"


@dataclass
class PluginManifest:
    id: str
    name: str
    description: str
    category: PluginCategory
    icon: str
    default_enabled: bool = True
    always_on: bool = False
    requires_student_profile: bool = True
    requires_document: bool = True
    panel_template: str | None = None
    config_schema: dict | None = None
    order_hint: int = 50


@dataclass
class StudentProfile:
    id: int
    pseudonym: str
    heritage_language: str | None
    english_proficiency_level: int | None
    l1_proficiency_level: int | None
    proficiency_notes: dict | None = None


@dataclass
class ClassProfile:
    id: int
    name: str
    grade_level: str | None
    students: list[StudentProfile] = field(default_factory=list)


@dataclass
class AccommodationResult:
    plugin_id: str
    generated_output: dict[str, Any]
    status: str = "generated"


class BasePlugin(ABC):
    @abstractmethod
    def manifest(self) -> PluginManifest:
        ...

    @abstractmethod
    async def generate(
        self,
        document_text: str,
        student_profile: StudentProfile | None,
        class_profile: ClassProfile | None,
        options: dict,
    ) -> AccommodationResult:
        ...

    def get_panel_context(
        self, document_id: int, student_id: int | None
    ) -> dict:
        return {}

    def register_routes(self, router: "APIRouter") -> None:
        pass

    def register_tasks(self) -> list:
        return []
