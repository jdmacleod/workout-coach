FOLDER_ROOT = "Exercise Coach"


def safe_slug(text: str) -> str:
    """Convert text to a filesystem-safe slug with no path separators or leading/trailing hyphens."""
    slug = text.lower()
    for ch in (" ", "—", "/", "\\", ":", "*", "?", '"', "<", ">", "|"):
        slug = slug.replace(ch, "-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


FOLDER_WORKOUTS = "Exercise Coach/Workouts"
FOLDER_PLANS = "Exercise Coach/Plans"
FOLDER_ASSESSMENTS = "Exercise Coach/Assessments"


def workout_note_title(date_str: str, workout_type: str, subtitle: str) -> str:
    """Build a workout note title from components.

    date_str: YYYY-MM-DD
    workout_type: e.g. "Strength"
    subtitle: e.g. "Upper Body"
    """
    type_cap = workout_type.capitalize()
    return f"{date_str} {type_cap} — {subtitle}"


def plan_note_title(week: str) -> str:
    """Build a weekly plan note title. week: YYYY-Www"""
    return f"Week {week}"


def assessment_note_title(week: str) -> str:
    """Build an assessment note title. week: YYYY-Www"""
    return f"Assessment {week}"
