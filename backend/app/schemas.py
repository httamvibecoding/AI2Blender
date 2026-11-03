from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SceneSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    duration_seconds: int = Field(default=6, ge=2, le=30)
    fps: int = Field(default=24, ge=12, le=60)


class CameraSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shot: Literal["wide", "medium", "close"] = "medium"
    movement: Literal["static", "slow_push_in"] = "static"


class AnimationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["wave", "bow", "salute", "nod", "turn", "point", "greet"] = "wave"
    emotion: str = Field(default="warm and dignified", min_length=1, max_length=120)


class OutputSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolution: tuple[int, int] = (1280, 720)
    format: Literal["mp4"] = "mp4"

    @field_validator("resolution")
    @classmethod
    def validate_resolution(cls, value: tuple[int, int]) -> tuple[int, int]:
        width, height = value
        if not (320 <= width <= 3840 and 320 <= height <= 2160):
            raise ValueError("Resolution must be between 320x320 and 3840x2160")
        return value


class ShotSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(default="A shot", min_length=1, max_length=160)
    style: str = Field(default="3D cartoon, soft shapes, warm cinematic lighting", min_length=1, max_length=240)
    scene: SceneSettings = Field(default_factory=SceneSettings)
    camera: CameraSettings = Field(default_factory=CameraSettings)
    animation: AnimationSettings = Field(default_factory=AnimationSettings)
    output: OutputSettings = Field(default_factory=OutputSettings)


class SceneSpec(BaseModel):
    """Allow-listed scene instructions; never accept executable Blender code here."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(default="A fictional Vietnamese king", min_length=1, max_length=160)
    style: str = Field(default="3D cartoon, soft shapes, warm cinematic lighting", min_length=1, max_length=240)
    scene: SceneSettings = Field(default_factory=SceneSettings)
    camera: CameraSettings = Field(default_factory=CameraSettings)
    animation: AnimationSettings = Field(default_factory=AnimationSettings)
    output: OutputSettings = Field(default_factory=OutputSettings)
    transition: Literal["cut", "fade", "cross_dissolve"] = "cut"
    shots: list[ShotSpec] | None = None


class PromptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=3, max_length=2000)


class ProjectCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="New project", min_length=1, max_length=120)


class ProjectUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)


class JobResponse(BaseModel):
    id: str
    project_id: str | None = None
    status: str
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    attempt: int = 1
    spec: dict[str, Any]
    output: str | None = None
    error: str | None = None
