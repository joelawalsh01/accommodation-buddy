import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Teacher(Base):
    __tablename__ = "teachers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    classes: Mapped[list["Class"]] = relationship(back_populates="teacher")
    documents: Mapped[list["Document"]] = relationship(back_populates="teacher")


class Class(Base):
    __tablename__ = "classes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    grade_level: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    teacher: Mapped["Teacher"] = relationship(back_populates="classes")
    students: Mapped[list["Student"]] = relationship(back_populates="class_")
    documents: Mapped[list["Document"]] = relationship(back_populates="class_")
    feature_toggles: Mapped[list["FeatureToggle"]] = relationship(
        back_populates="class_"
    )


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"), nullable=False)
    pseudonym: Mapped[str] = mapped_column(String(255), nullable=False)
    heritage_language: Mapped[str | None] = mapped_column(String(100))
    english_proficiency_level: Mapped[int | None] = mapped_column(Integer)
    l1_proficiency_level: Mapped[int | None] = mapped_column(Integer)
    proficiency_notes: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    class_: Mapped["Class"] = relationship(back_populates="students")
    accommodations: Mapped[list["Accommodation"]] = relationship(
        back_populates="target_student"
    )
    assessments: Mapped[list["LanguageAssessment"]] = relationship(
        back_populates="student"
    )
    glossary_entries: Mapped[list["GlossaryEntry"]] = relationship(
        back_populates="student"
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"), nullable=False)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"), nullable=False)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_type: Mapped[str] = mapped_column(
        Enum("pdf", "docx", "pptx", "image", name="file_type_enum"), nullable=False
    )
    extracted_text: Mapped[str | None] = mapped_column(Text)
    ocr_status: Mapped[str] = mapped_column(
        String(50), server_default="pending"
    )
    status_detail: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ocr_progress: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    class_: Mapped["Class"] = relationship(back_populates="documents")
    teacher: Mapped["Teacher"] = relationship(back_populates="documents")
    accommodations: Mapped[list["Accommodation"]] = relationship(
        back_populates="document"
    )
    plugin_states: Mapped[list["PluginState"]] = relationship(
        back_populates="document"
    )


class Accommodation(Base):
    __tablename__ = "accommodations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id"), nullable=False
    )
    plugin_id: Mapped[str] = mapped_column(String(100), nullable=False)
    target_student_id: Mapped[int | None] = mapped_column(
        ForeignKey("students.id"), nullable=True
    )
    input_context: Mapped[dict | None] = mapped_column(JSON)
    generated_output: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(
        Enum(
            "pending",
            "generated",
            "accepted",
            "revised",
            "rejected",
            name="accommodation_status_enum",
        ),
        server_default="pending",
    )
    revised_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    document: Mapped["Document"] = relationship(back_populates="accommodations")
    target_student: Mapped["Student | None"] = relationship(
        back_populates="accommodations"
    )


class LanguageAssessment(Base):
    __tablename__ = "language_assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False)
    conversation_log: Mapped[dict | None] = mapped_column(JSON)
    english_score: Mapped[int | None] = mapped_column(Integer)
    l1_score: Mapped[int | None] = mapped_column(Integer)
    assessed_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    student: Mapped["Student"] = relationship(back_populates="assessments")


class GlossaryEntry(Base):
    __tablename__ = "glossary_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False)
    term: Mapped[str] = mapped_column(String(255), nullable=False)
    definition: Mapped[str | None] = mapped_column(Text)
    l1_translation: Mapped[str | None] = mapped_column(String(500))
    context_sentence: Mapped[str | None] = mapped_column(Text)
    source_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    student: Mapped["Student"] = relationship(back_populates="glossary_entries")
    source_document: Mapped["Document | None"] = relationship()


class FeatureToggle(Base):
    __tablename__ = "feature_toggles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"), nullable=False)
    plugin_id: Mapped[str] = mapped_column(String(100), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    config_overrides: Mapped[dict | None] = mapped_column(JSON)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    class_: Mapped["Class"] = relationship(back_populates="feature_toggles")


class PluginState(Base):
    __tablename__ = "plugin_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id"), nullable=False
    )
    plugin_id: Mapped[str] = mapped_column(String(100), nullable=False)
    panel_order: Mapped[int] = mapped_column(Integer, server_default="50")
    collapsed: Mapped[bool] = mapped_column(Boolean, server_default="false")
    last_run_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    document: Mapped["Document"] = relationship(back_populates="plugin_states")
