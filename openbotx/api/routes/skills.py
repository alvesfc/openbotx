"""Skills API routes for OpenBotX."""

from fastapi import APIRouter, HTTPException

from openbotx.api.schemas import (
    SkillCreate,
    SkillListResponse,
    SkillResponse,
    SuccessResponse,
)
from openbotx.core.skills_registry import get_skills_registry

router = APIRouter()


@router.get("", response_model=SkillListResponse)
async def list_skills() -> SkillListResponse:
    """List all registered skills.

    Returns:
        List of skills
    """
    registry = get_skills_registry()
    skills = registry.list_skills()

    return SkillListResponse(
        skills=[
            SkillResponse(
                id=s.id,
                name=s.name,
                description=s.description,
                version=s.version,
                triggers=s.triggers.keywords,
                tools=s.tools,
                file_path=s.file_path,
            )
            for s in skills
        ],
        total=len(skills),
    )


@router.get("/{skill_id}", response_model=SkillResponse)
async def get_skill(skill_id: str) -> SkillResponse:
    """Get a skill by ID.

    Args:
        skill_id: Skill ID

    Returns:
        Skill details
    """
    registry = get_skills_registry()
    skill = registry.get(skill_id)

    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

    return SkillResponse(
        id=skill.id,
        name=skill.name,
        description=skill.description,
        version=skill.version,
        triggers=skill.triggers.keywords,
        tools=skill.tools,
        file_path=skill.file_path,
    )


@router.post("", response_model=SkillResponse)
async def create_skill(request: SkillCreate) -> SkillResponse:
    """Create a new skill.

    Args:
        request: Skill creation request

    Returns:
        Created skill
    """
    registry = get_skills_registry()

    # Generate ID from name
    skill_id = request.name.lower().replace(" ", "-")

    # Check if skill already exists
    if registry.get(skill_id):
        raise HTTPException(
            status_code=400,
            detail=f"Skill already exists: {skill_id}",
        )

    skill = await registry.create_skill(
        skill_id=skill_id,
        name=request.name,
        description=request.description,
        triggers=request.triggers,
        tools=request.tools,
        steps=request.steps,
        guidelines=request.guidelines,
    )

    return SkillResponse(
        id=skill.id,
        name=skill.name,
        description=skill.description,
        version=skill.version,
        triggers=skill.triggers.keywords,
        tools=skill.tools,
        file_path=skill.file_path,
    )


@router.post("/reload", response_model=SuccessResponse)
async def reload_skills() -> SuccessResponse:
    """Reload all skills from disk.

    Returns:
        Success response
    """
    registry = get_skills_registry()
    count = await registry.load_skills()

    return SuccessResponse(message=f"Reloaded {count} skills")
