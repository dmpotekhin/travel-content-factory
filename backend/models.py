"""SQLAlchemy ORM models."""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Text, DateTime, ForeignKey, JSON, Enum as SAEnum,
)
from sqlalchemy.orm import DeclarativeBase, relationship
import enum


class Base(DeclarativeBase):
    pass


class MediaType(str, enum.Enum):
    photo = "photo"
    video = "video"


class ProjectMode(str, enum.Enum):
    auto = "auto"
    manual = "manual"
    script = "script"


class ProjectStatus(str, enum.Enum):
    draft = "draft"
    processing = "processing"
    ready = "ready"
    error = "error"


class MediaFile(Base):
    __tablename__ = "media_files"

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(512), nullable=False)
    original_path = Column(String(1024), nullable=False)
    stored_path = Column(String(1024), nullable=False)
    media_type = Column(SAEnum(MediaType), nullable=False)
    duration = Column(Float, nullable=True)     # seconds, video only
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    size_bytes = Column(Integer, nullable=False)
    date_taken = Column(DateTime, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    country = Column(String(128), nullable=True)
    city = Column(String(128), nullable=True)
    hashtags = Column(JSON, nullable=True, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)

    project_clips = relationship("ProjectClip", back_populates="media", cascade="all, delete-orphan")


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(256), nullable=False)
    mode = Column(SAEnum(ProjectMode), nullable=False, default=ProjectMode.manual)
    platform = Column(String(32), nullable=True)   # tiktok, reels, facebook
    status = Column(SAEnum(ProjectStatus), nullable=False, default=ProjectStatus.draft)
    script_text = Column(Text, nullable=True)
    duration_target = Column(Float, nullable=True)   # target duration in seconds
    country_filter = Column(String(128), nullable=True)
    year_filter = Column(Integer, nullable=True)
    export_path = Column(String(1024), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    clips = relationship("ProjectClip", back_populates="project", cascade="all, delete-orphan",
                         order_by="ProjectClip.order_index")


class ProjectClip(Base):
    __tablename__ = "project_clips"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    media_id = Column(Integer, ForeignKey("media_files.id", ondelete="SET NULL"), nullable=True)
    start_time = Column(Float, nullable=False, default=0.0)   # start offset in source video
    duration = Column(Float, nullable=False, default=5.0)      # clip duration
    order_index = Column(Integer, nullable=False, default=0)
    transition = Column(String(32), nullable=True, default="cut")  # cut, fade, dissolve
    scene_description = Column(Text, nullable=True)

    project = relationship("Project", back_populates="clips")
    media = relationship("MediaFile", back_populates="project_clips")


class Generation(Base):
    __tablename__ = "generations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    platform = Column(String(32), nullable=False)
    topic = Column(Text, nullable=False)
    generated_script = Column(Text, nullable=True)
    generated_caption = Column(Text, nullable=True)
    generated_hashtags = Column(JSON, nullable=True, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
